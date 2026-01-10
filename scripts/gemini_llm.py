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

    prompt = (
        "System:\n"
        f"{system}\n\n"
        "User:\n"
        f"{user}\n\n"
        "Return only valid JSON. Do not add any extra text."
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

    try:
        response_obj = json.loads(response_text)
    except json.JSONDecodeError:
        start = response_text.find('{')
        end = response_text.rfind('}')
        if start == -1 or end == -1 or end <= start:
            if stderr:
                sys.stderr.write(stderr + "\n")
            sys.stderr.write("Gemini CLI response was not JSON.\n")
            with open("gemini_llm_error.txt", "w", encoding="utf-8") as f:
                f.write(response_text + "\n")
            return 1
        response_candidate = response_text[start:end + 1]
        try:
            response_obj = json.loads(response_candidate)
            response_text = response_candidate
        except json.JSONDecodeError:
            if stderr:
                sys.stderr.write(stderr + "\n")
            sys.stderr.write("Gemini CLI response contained invalid JSON.\n")
            with open("gemini_llm_error.txt", "w", encoding="utf-8") as f:
                f.write(response_text + "\n")
            return 1

    if not isinstance(response_obj, dict) or 'updates' not in response_obj:
        if stderr:
            sys.stderr.write(stderr + "\n")
        sys.stderr.write("Gemini CLI JSON missing required 'updates' field.\n")
        with open("gemini_llm_error.txt", "w", encoding="utf-8") as f:
            f.write(response_text + "\n")
        return 1

    sys.stdout.write(response_text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
