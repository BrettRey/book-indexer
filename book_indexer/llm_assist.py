"""LLM-assisted lexicon normalization and cross-reference suggestions."""

from __future__ import annotations

import json
import os
import re
import subprocess
import textwrap
from typing import Optional
from urllib import request

from book_indexer.lexicon import Lexicon


class LLMError(RuntimeError):
    """Raised when the LLM provider fails or returns invalid output."""


def _iter_tex_files(root: str, include_hidden: bool = False) -> list[str]:
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        if not include_hidden:
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]
        for name in filenames:
            if name.endswith('.tex'):
                files.append(os.path.join(dirpath, name))
    return files


def _find_contexts(content: str, term: str, window: int, limit: int) -> list[str]:
    contexts: list[str] = []
    if len(term) < 3:
        return contexts
    pattern = re.compile(re.escape(term), re.IGNORECASE)
    for match in pattern.finditer(content):
        start = max(0, match.start() - window)
        end = min(len(content), match.end() + window)
        snippet = content[start:end].replace('\n', ' ')
        snippet = re.sub(r'\s+', ' ', snippet).strip()
        contexts.append(snippet)
        if len(contexts) >= limit:
            break
    return contexts


def _build_contexts(
    files: list[str],
    entries: list[dict],
    max_contexts: int,
    context_window: int,
) -> dict[int, list[str]]:
    contexts: dict[int, list[str]] = {i: [] for i in range(len(entries))}
    if not files:
        return contexts

    for file_path in files:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        for idx, entry in enumerate(entries):
            if len(contexts[idx]) >= max_contexts:
                continue
            term = entry.get('term', '')
            if not term:
                continue
            needed = max_contexts - len(contexts[idx])
            found = _find_contexts(content, term, context_window, needed)
            contexts[idx].extend(found)
            if len(contexts[idx]) >= max_contexts:
                continue
            for syn in entry.get('synonyms', []):
                if len(contexts[idx]) >= max_contexts:
                    break
                needed = max_contexts - len(contexts[idx])
                found = _find_contexts(content, syn, context_window, needed)
                contexts[idx].extend(found)
    return contexts


def _chunk(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _json_from_text(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find('{')
        end = text.rfind('}')
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(text[start:end + 1])


class LLMClient:
    def __init__(
        self,
        provider: str,
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        command: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1200,
    ):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.command = command
        self.temperature = temperature
        self.max_tokens = max_tokens

    def complete_json(self, system: str, user: str) -> dict:
        if self.provider == 'command':
            if not self.command:
                raise LLMError("LLM command provider requires --llm-command")
            payload = json.dumps({
                'system': system,
                'user': user,
                'model': self.model,
                'temperature': self.temperature,
                'max_tokens': self.max_tokens,
            })
            result = subprocess.run(
                self.command,
                input=payload,
                text=True,
                capture_output=True,
                shell=True,
            )
            if result.returncode != 0:
                raise LLMError(result.stderr.strip() or "LLM command failed")
            return _json_from_text(result.stdout)

        if self.provider == 'openai':
            return self._openai_request(system, user)
        if self.provider == 'anthropic':
            return self._anthropic_request(system, user)
        raise LLMError(f"Unknown provider: {self.provider}")

    def _openai_request(self, system: str, user: str) -> dict:
        api_key = self.api_key or os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise LLMError("OPENAI_API_KEY is not set")
        url = self.base_url or "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature,
        }
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
        response = json.loads(body)
        content = response["choices"][0]["message"]["content"]
        return _json_from_text(content)

    def _anthropic_request(self, system: str, user: str) -> dict:
        api_key = self.api_key or os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set")
        url = self.base_url or "https://api.anthropic.com/v1/messages"
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
        response = json.loads(body)
        content = response["content"][0]["text"]
        return _json_from_text(content)


def _build_prompt(entries: list[dict], contexts: dict[int, list[str]]) -> tuple[str, str]:
    system = textwrap.dedent(
        """\
        You are an expert academic book indexer.
        Propose improvements to lexicon entries:
        - Normalize canonical terms (consistent case).
        - Add display forms (LaTeX formatting) when needed.
        - Introduce hierarchy (head!sub) where appropriate.
        - Add see/see_also cross-refs for synonyms and related terms.
        - Prefer see refs when an alternative term should redirect rather than co-index.
        Return strict JSON only."""
    )
    items = []
    for idx, entry in enumerate(entries):
        items.append({
            "id": entry["_id"],
            "term": entry.get("term"),
            "type": entry.get("type"),
            "synonyms": entry.get("synonyms", []),
            "contexts": contexts.get(entry["_id"], []),
        })
    user = textwrap.dedent(
        f"""\
        For each entry, return updates only when changes are needed.
        JSON schema:
        {{
          "updates": [
            {{
              "id": <int>,
              "canonical": <string?>,
              "display": <string?>,
              "hierarchy": <array of strings?>,
              "synonyms": <array of strings?>,
              "see": <array of strings?>,
              "see_also": <array of strings?>,
              "type": <string?>
            }}
          ],
          "notes": [<string>]
        }}
        Entries:
        {json.dumps(items, ensure_ascii=True)}
        """
    )
    return system, user


def _apply_updates(lexicon: Lexicon, updates: list[dict]) -> list[dict]:
    results: list[dict] = []
    for update in updates:
        idx = update.get('id')
        if idx is None or idx < 0 or idx >= len(lexicon.entries):
            continue
        entry = lexicon.entries[idx]
        before = json.loads(json.dumps(entry))

        canonical = update.get('canonical')
        if canonical and canonical != entry.get('term'):
            old = entry.get('term')
            entry['term'] = canonical
            if old:
                synonyms = set(entry.get('synonyms', []))
                synonyms.add(old)
                entry['synonyms'] = sorted(synonyms)

        display = update.get('display')
        if display:
            entry['display'] = display

        hierarchy = update.get('hierarchy')
        if hierarchy:
            entry['hierarchy'] = hierarchy

        synonyms = update.get('synonyms')
        if synonyms:
            merged = set(entry.get('synonyms', []))
            merged.update(synonyms)
            entry['synonyms'] = sorted(merged)

        see = update.get('see')
        if see:
            entry['see'] = see

        see_also = update.get('see_also')
        if see_also:
            entry['see_also'] = see_also

        entry_type = update.get('type')
        if entry_type:
            entry['type'] = entry_type

        after = json.loads(json.dumps(entry))
        if before != after:
            results.append({
                'id': idx,
                'before': before,
                'after': after,
            })
    return results


def apply_report(report_path: str, lexicon_path: str,
                 applied_path: Optional[str] = None) -> int:
    """Apply a previously generated LLM report to a lexicon."""
    with open(report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)

    updates = report.get('updates', [])
    if not isinstance(updates, list):
        raise LLMError("Report is missing a valid 'updates' list")

    lexicon = Lexicon(lexicon_path)
    applied = _apply_updates(lexicon, updates)
    lexicon.save(lexicon_path)

    if applied_path:
        with open(applied_path, 'w', encoding='utf-8') as f:
            json.dump(applied, f, indent=2)

    return len(applied)


def run_assist(
    dir_path: str,
    lexicon_path: str,
    report_path: str,
    apply: bool = False,
    provider: str = "openai",
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    command: Optional[str] = None,
    include_hidden: bool = False,
    chunk_size: int = 20,
    max_contexts: int = 2,
    context_window: int = 80,
    temperature: float = 0.2,
    max_tokens: int = 1200,
    progress: bool = False,
) -> None:
    lexicon = Lexicon(lexicon_path)
    if len(lexicon) == 0:
        raise LLMError(f"No entries in lexicon {lexicon_path}")

    files = _iter_tex_files(dir_path, include_hidden=include_hidden)
    if progress:
        print(f"Loaded {len(lexicon.entries)} lexicon entries.", flush=True)
        print(f"Scanning {len(files)} .tex files for context...", flush=True)
    entries = []
    for idx, entry in enumerate(lexicon.entries):
        entry_copy = json.loads(json.dumps(entry))
        entry_copy['_id'] = idx
        entries.append(entry_copy)

    contexts = _build_contexts(files, entries, max_contexts, context_window)
    if progress:
        print("Context extraction complete.", flush=True)
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
        temperature=temperature,
        max_tokens=max_tokens,
    )

    updates: list[dict] = []
    notes: list[str] = []

    batches = _chunk(entries, chunk_size)
    total_batches = len(batches)

    for idx, batch in enumerate(batches, start=1):
        if progress:
            print(f"LLM batch {idx}/{total_batches} ({len(batch)} entries)...", flush=True)
        system, user = _build_prompt(batch, contexts)
        result = client.complete_json(system, user)
        updates.extend(result.get('updates', []))
        notes.extend(result.get('notes', []))
        if progress:
            print(f"LLM batch {idx}/{total_batches} complete.", flush=True)

    report = {
        'updates': updates,
        'notes': notes,
    }
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    if progress:
        print(f"Report written to {report_path}.", flush=True)

    if apply:
        applied = _apply_updates(lexicon, updates)
        lexicon.save(lexicon_path)
        applied_path = os.path.splitext(report_path)[0] + ".applied.json"
        with open(applied_path, 'w', encoding='utf-8') as f:
            json.dump(applied, f, indent=2)
        if progress:
            print(f"Applied updates written to {applied_path}.", flush=True)
