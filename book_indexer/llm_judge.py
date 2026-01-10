"""LLM-assisted tag judgement for index relevance."""

from __future__ import annotations

import json
import os
import re
from typing import Optional

from book_indexer.llm_assist import LLMClient, LLMError, _chunk, _iter_tex_files
from book_indexer.tagger import INDEX_TAG_PATTERN, infer_type_from_command


def _build_tag_context(content: str, start: int, end: int, window: int) -> str:
    left = max(0, start - window)
    right = min(len(content), end + window)
    snippet = content[left:start] + content[end:right]
    snippet = snippet.replace('\n', ' ')
    snippet = re.sub(r'\s+', ' ', snippet).strip()
    return snippet


def _collect_tags(files: list[str], context_window: int) -> list[dict]:
    items: list[dict] = []
    for path in files:
        with open(path, 'r', encoding='utf-8') as handle:
            content = handle.read()
        for match in INDEX_TAG_PATTERN.finditer(content):
            cmd = match.group(1)
            term = match.group(3) or ""
            start = match.start()
            end = match.end()
            line = content.count('\n', 0, start) + 1
            items.append({
                "id": len(items),
                "file": path,
                "line": line,
                "cmd": cmd,
                "type": infer_type_from_command(cmd),
                "term": term.strip(),
                "tag": match.group(0),
                "start": start,
                "end": end,
                "context": _build_tag_context(content, start, end, context_window),
            })
    return items


def _build_prompt(items: list[dict]) -> tuple[str, str]:
    system = (
        "You are an expert academic book indexer. "
        "Decide whether each index tag should be kept. "
        "Keep tags only when the surrounding text discusses the concept "
        "or when the term is meaningfully relevant. "
        "Drop tags for mere mentions, lists of examples, bibliographic mentions, "
        "or passing references that do not add index-worthy discussion. "
        "When unsure, prefer dropping."
    )
    payload = []
    for item in items:
        payload.append({
            "id": item["id"],
            "term": item.get("term"),
            "type": item.get("type"),
            "context": item.get("context"),
        })
    user = (
        "Return strict JSON only.\n"
        "Schema:\n"
        "{\n"
        '  "decisions": [\n'
        '    {"id": <int>, "keep": <bool>, "reason": <string>}\n'
        "  ],\n"
        '  "notes": [<string>]\n'
        "}\n"
        f"Items:\n{json.dumps(payload, ensure_ascii=True)}\n"
    )
    return system, user


def run_judge(
    dir_path: str,
    report_path: str,
    provider: str = "openai",
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    command: Optional[str] = None,
    include_hidden: bool = False,
    chunk_size: int = 25,
    context_window: int = 160,
    temperature: float = 0.2,
    max_tokens: int = 1200,
    progress: bool = False,
    resume: bool = False,
    checkpoint: bool = False,
) -> None:
    files = _iter_tex_files(dir_path, include_hidden=include_hidden)
    if progress:
        print(f"Scanning {len(files)} .tex files for tags...", flush=True)
    items = _collect_tags(files, context_window)
    if not items:
        raise LLMError("No index tags found to judge")
    if progress:
        print(f"Collected {len(items)} tags for judgement.", flush=True)

    existing_decisions: dict[int, dict] = {}
    notes: list[str] = []
    if resume and os.path.exists(report_path):
        try:
            with open(report_path, "r", encoding="utf-8") as handle:
                existing_report = json.load(handle)
            for decision in existing_report.get("decisions", []) or []:
                if isinstance(decision, dict) and "id" in decision:
                    existing_decisions[int(decision["id"])] = decision
            existing_notes = existing_report.get("notes", [])
            if isinstance(existing_notes, list):
                notes.extend(existing_notes)
            if progress and existing_decisions:
                print(
                    f"Resuming: {len(existing_decisions)} decisions already recorded.",
                    flush=True,
                )
        except (json.JSONDecodeError, OSError) as exc:
            raise LLMError(f"Failed to load existing report for resume: {exc}")

    decisions: list[dict] = list(existing_decisions.values())
    pending_items = [item for item in items if item["id"] not in existing_decisions]
    if not pending_items:
        report = {
            "items": items,
            "decisions": decisions,
            "notes": notes,
        }
        with open(report_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
        if progress:
            print(f"Report written to {report_path}.", flush=True)
        return

    resolved_model = model
    if not resolved_model:
        if provider == 'openai':
            resolved_model = "gpt-4o-mini"
        elif provider == 'anthropic':
            resolved_model = "claude-3-5-sonnet-latest"
        else:
            resolved_model = ""

    client = LLMClient(
        provider=provider,
        model=resolved_model,
        api_key=api_key,
        base_url=base_url,
        command=command,
        response_keys=["decisions", "notes"],
        temperature=temperature,
        max_tokens=max_tokens,
    )

    batches = _chunk(pending_items, chunk_size)
    total_batches = len(batches)
    for idx, batch in enumerate(batches, start=1):
        if progress:
            print(f"LLM batch {idx}/{total_batches} ({len(batch)} tags)...", flush=True)
        system, user = _build_prompt(batch)
        result = client.complete_json(system, user)
        new_decisions = result.get("decisions", [])
        if isinstance(new_decisions, list):
            for decision in new_decisions:
                if not isinstance(decision, dict) or "id" not in decision:
                    continue
                decision_id = int(decision["id"])
                if decision_id in existing_decisions:
                    continue
                existing_decisions[decision_id] = decision
                decisions.append(decision)
        notes.extend(result.get("notes", []))
        if progress:
            print(f"LLM batch {idx}/{total_batches} complete.", flush=True)
        if checkpoint or resume:
            report = {
                "items": items,
                "decisions": decisions,
                "notes": notes,
            }
            with open(report_path, "w", encoding="utf-8") as handle:
                json.dump(report, handle, indent=2)
            if progress:
                print(f"Checkpoint saved to {report_path}.", flush=True)

    report = {
        "items": items,
        "decisions": decisions,
        "notes": notes,
    }
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    if progress:
        print(f"Report written to {report_path}.", flush=True)


def apply_judgment(report_path: str) -> int:
    if not os.path.exists(report_path):
        raise LLMError(f"Judgment report not found: {report_path}")
    with open(report_path, "r", encoding="utf-8") as handle:
        report = json.load(handle)

    items = report.get("items", [])
    decisions = report.get("decisions", [])
    if not isinstance(items, list) or not isinstance(decisions, list):
        raise LLMError("Report is missing 'items' or 'decisions' lists")

    decision_map = {d.get("id"): d for d in decisions if "id" in d}
    removals: dict[str, list[dict]] = {}
    for item in items:
        decision = decision_map.get(item.get("id"))
        if not decision:
            continue
        if decision.get("keep") is False:
            removals.setdefault(item["file"], []).append(item)

    total_removed = 0
    for path, entries in removals.items():
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()

        spans = []
        fallback = []
        for entry in entries:
            start = entry.get("start")
            end = entry.get("end")
            tag = entry.get("tag", "")
            if (
                isinstance(start, int)
                and isinstance(end, int)
                and 0 <= start < end <= len(content)
                and content[start:end] == tag
            ):
                spans.append((start, end))
            else:
                fallback.append(entry)

        spans.sort(reverse=True)
        for start, end in spans:
            content = content[:start] + content[end:]
            total_removed += 1

        if fallback:
            lines = content.splitlines(keepends=True)
            for entry in fallback:
                tag = entry.get("tag", "")
                if not tag:
                    continue
                line_no = entry.get("line")
                removed = False
                if isinstance(line_no, int) and 1 <= line_no <= len(lines):
                    idx = line_no - 1
                    if tag in lines[idx]:
                        lines[idx] = lines[idx].replace(tag, "", 1)
                        removed = True
                if removed:
                    total_removed += 1
                else:
                    if tag in content:
                        content = content.replace(tag, "", 1)
                        total_removed += 1
            content = ''.join(lines)

        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)

    return total_removed
