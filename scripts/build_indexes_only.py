#!/usr/bin/env python3
"""Generate lightweight index inputs and an indexes-only TeX file.

This avoids a full book build. Page numbers are derived from line numbers in
the chapter sources and are only meant for previewing index structure.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
sys.path.insert(0, ROOT_DIR)

from book_indexer.tagger import INDEX_TAG_PATTERN, infer_type_from_command


def _iter_entries(chapters_dir: str):
    pattern = os.path.join(chapters_dir, "*.tex")
    for path in sorted(glob.glob(pattern)):
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()
        for match in INDEX_TAG_PATTERN.finditer(content):
            cmd = match.group(1)
            term = (match.group(3) or "").strip()
            if not term:
                continue
            entry_type = infer_type_from_command(cmd)
            line_no = content.count("\n", 0, match.start()) + 1
            yield entry_type, term, line_no


def _write_index(path: str, entries: list[tuple[str, int]]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for term, page in entries:
            term = _escape_makeindex_crossrefs(term)
            handle.write(f"\\indexentry {{{term}}}{{{page}}}\n")


def _write_tex(path: str, prefix: str, has_name: bool, has_language: bool, has_subject: bool) -> None:
    lines = [
        r"\documentclass{article}",
        r"\providecommand{\indexspace}{\par\bigskip}",
        r"\providecommand{\see}[2]{\emph{see} #1}",
        r"\providecommand{\seealso}[2]{\emph{see also} #1}",
        r"\providecommand{\infn}[1]{#1}",
        r"\begin{document}",
    ]
    if has_name:
        lines.extend(
            [
                r"\renewcommand{\indexname}{Name index}",
                rf"\input{{{prefix}.and}}",
                r"\clearpage",
            ]
        )
    if has_language:
        lines.extend(
            [
                r"\renewcommand{\indexname}{Language index}",
                rf"\input{{{prefix}.lnd}}",
                r"\clearpage",
            ]
        )
    if has_subject:
        lines.extend(
            [
                r"\renewcommand{\indexname}{Subject index}",
                rf"\input{{{prefix}.snd}}",
            ]
        )
    lines.append(r"\end{document}")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
        handle.write("\n")


def _escape_makeindex_crossrefs(term: str) -> str:
    """Escape ! inside see/seealso targets for makeindex."""
    def repl(match: re.Match) -> str:
        kind = match.group(1)
        target = match.group(2)
        if "@" in target:
            target = target.split("@", 1)[1]
        target = target.replace("!", '"!').replace("@", '"@')
        return f"|{kind}{{{target}}}"

    return re.sub(r"\|(see|seealso)\{([^{}]*)\}", repl, term)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate lightweight index inputs and an indexes-only TeX file."
    )
    parser.add_argument("chapters_dir", help="Directory containing chapter .tex files.")
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Output directory for index files and TeX (default: current dir).",
    )
    parser.add_argument(
        "--prefix",
        default="main",
        help="Base filename prefix for index files (default: main).",
    )
    parser.add_argument(
        "--tex",
        default="indexes_only.tex",
        help="TeX filename to generate (default: indexes_only.tex).",
    )
    args = parser.parse_args()

    buckets = {"subject": [], "language": [], "name": []}
    for entry_type, term, page in _iter_entries(args.chapters_dir):
        bucket = buckets.get(entry_type, buckets["subject"])
        bucket.append((term, page))

    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)
    prefix_base = os.path.basename(args.prefix)

    if buckets["name"]:
        _write_index(os.path.join(output_dir, f"{prefix_base}.adx"), buckets["name"])
    if buckets["language"]:
        _write_index(os.path.join(output_dir, f"{prefix_base}.ldx"), buckets["language"])
    if buckets["subject"]:
        _write_index(os.path.join(output_dir, f"{prefix_base}.sdx"), buckets["subject"])

    tex_path = os.path.join(output_dir, args.tex)
    _write_tex(
        tex_path,
        prefix_base,
        has_name=bool(buckets["name"]),
        has_language=bool(buckets["language"]),
        has_subject=bool(buckets["subject"]),
    )
    print(f"Wrote index inputs and {tex_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
