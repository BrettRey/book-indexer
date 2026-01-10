#!/usr/bin/env python3
"""Bridge for book_indexer LLM assist using the Gemini CLI."""

import json
import os
import re
import subprocess
import sys


def main() -> int:
    payload = json.load(sys.stdin)
    system = payload.get("system", "")
    user = payload.get("user", "")
    model = payload.get("model", "")
    response_keys = payload.get("response_keys")
    if not isinstance(response_keys, list) or not response_keys:
        response_keys = ["updates", "notes"]
    primary_key = response_keys[0]

    prompt = (
        "System:\n"
        f"{system}\n\n"
        "User:\n"
        f"{user}\n\n"
        "IMPORTANT:\n"
        "- Return only valid JSON (no markdown, no prose).\n"
        "- Do not create, write, or mention files.\n"
        "- Do not call tools.\n"
        f"- Always wrap the response in a top-level object with keys {json.dumps(response_keys)}.\n"
        f"- If unsure, return {{\"{primary_key}\":[],\"notes\":[\"no_changes\"]}}.\n"
    )

    cmd = ["gemini", "--yolo", "--output-format", "json"]
    if model:
        cmd.extend(["--model", model])

    result = subprocess.run(
        cmd + [prompt],
        text=True,
        capture_output=True,
        env=os.environ.copy(),
    )

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()

    if result.returncode != 0:
        if stdout:
            sys.stderr.write(stdout + "\n")
        if stderr:
            sys.stderr.write(stderr + "\n")
        return result.returncode or 1

    if not stdout:
        if stderr:
            sys.stderr.write(stderr + "\n")
        sys.stderr.write("Gemini CLI returned empty output.\n")
        return 1

    # Validate/normalize JSON output for the assist pipeline.
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        start = stdout.find('{')
        end = stdout.rfind('}')
        if start == -1 or end == -1 or end <= start:
            if stderr:
                sys.stderr.write(stderr + "\n")
            sys.stderr.write("Gemini CLI did not return JSON output.\n")
            return 1
        candidate = stdout[start:end + 1]
        try:
            data = json.loads(candidate)
            stdout = candidate
        except json.JSONDecodeError:
            if stderr:
                sys.stderr.write(stderr + "\n")
            sys.stderr.write("Gemini CLI returned invalid JSON output.\n")
            return 1

    response_text = None
    if isinstance(data, dict) and 'response' in data:
        response_text = data['response']
    else:
        response_text = stdout

    if isinstance(response_text, dict):
        response_obj = response_text
        response_text = json.dumps(response_obj)
    else:
        response_text = str(response_text).strip()

    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", response_text, re.DOTALL)
    if fence_match:
        response_text = fence_match.group(1).strip()

    def write_error(message: str) -> int:
        if stderr:
            sys.stderr.write(stderr + "\n")
        sys.stderr.write(message + "\n")
        with open("gemini_llm_error.txt", "w", encoding="utf-8") as f:
            f.write(response_text + "\n")
        sys.stderr.write("Wrote invalid output to gemini_llm_error.txt\n")
        return 1

    def coerce_json(text: str):
        # Try direct parse
        try:
            return json.loads(text), text
        except json.JSONDecodeError:
            pass

        # If we have notes but no primary key, wrap list into the primary key.
        if '"notes"' in text and f'"{primary_key}"' not in text:
            notes_idx = text.find('"notes"')
            prefix = text[:notes_idx].strip().rstrip(',')
            notes_part = text[notes_idx:]

            # Extract notes array
            notes_start = notes_part.find('[')
            if notes_start == -1:
                return None, text
            depth = 0
            notes_end = -1
            for i, ch in enumerate(notes_part[notes_start:], start=notes_start):
                if ch == '[':
                    depth += 1
                elif ch == ']':
                    depth -= 1
                    if depth == 0:
                        notes_end = i + 1
                        break
            if notes_end == -1:
                return None, text
            notes_array = notes_part[notes_start:notes_end]

            primary_raw = prefix
            if not primary_raw.startswith('['):
                primary_raw = f"[{primary_raw}]"
            candidate = f'{{"{primary_key}": {primary_raw}, "notes": {notes_array}}}'
            try:
                return json.loads(candidate), candidate
            except json.JSONDecodeError:
                return None, text

        # If looks like list of objects, wrap as updates list.
        if text.lstrip().startswith('{') and text.rstrip().endswith('}'):
            candidate = f'{{"{primary_key}": [{text.strip()}], "notes": []}}'
            try:
                return json.loads(candidate), candidate
            except json.JSONDecodeError:
                return None, text
        if text.lstrip().startswith('[') and text.rstrip().endswith(']'):
            candidate = f'{{"{primary_key}": {text.strip()}, "notes": []}}'
            try:
                return json.loads(candidate), candidate
            except json.JSONDecodeError:
                return None, text

        return None, text

    response_obj, normalized_text = coerce_json(response_text)
    if response_obj is None:
        # Try to salvage with first { ... }
        start = response_text.find('{')
        end = response_text.rfind('}')
        if start != -1 and end != -1 and end > start:
            candidate = response_text[start:end + 1]
            response_obj, normalized_text = coerce_json(candidate)
            if response_obj is None:
                return write_error("Gemini CLI response contained invalid JSON.")
        else:
            return write_error("Gemini CLI response was not JSON.")

    if not isinstance(response_obj, dict) or primary_key not in response_obj:
        return write_error(f"Gemini CLI JSON missing required '{primary_key}' field.")

    sys.stdout.write(normalized_text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
