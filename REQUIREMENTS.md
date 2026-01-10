# Book Indexer Requirements

## Overview
The tool targets LaTeX academic books and produces three indexes: language/lexical, subject, and name. The default input is a LaTeX book with no indexing tags. The tool inserts tags into the LaTeX sources and emits index files compatible with `makeindex` and `xindy`.

## Inputs
- LaTeX source tree using standard book structure (chapters/sections).
- Optional lexicon file (YAML/JSON) with canonical entries, synonyms, cross-refs, and hierarchy hints.

## Outputs
- Updated LaTeX sources with after-phrase tags (e.g., `\\index{...}` or index-type macros).
- `.idx` files for each index type, compatible with `makeindex`/`xindy`.
- Change report summarizing insertions, edits, and suggested improvements.
- Optional LLM suggestion report for lexicon normalization and cross-refs.

## Functional Requirements
- Parse standard LaTeX structure and preserve formatting and non-index macros.
- Generate tags for three index types (language/lexical, subject, name).
- Respect existing tags by default; propose improvements rather than overwriting.
- Produce expert-level indexes:
  - Decide ranges vs stand-alone entries.
  - Provide context-aware `see`/`see also`.
  - Build hierarchical structures where appropriate.
  - Maintain consistent entry form while favoring ease of use.
- Support optional lexicon-guided normalization and disambiguation.
- Provide an optional LLM-assisted workflow to propose lexicon updates.

## Author Participation Modes
- `guide`: proposals only; no source edits without confirmation.
- `assist`: apply safe, high-confidence insertions; leave existing tags intact.
- `auto`: full tagging and normalization with detailed audit trail.

## Compatibility
- `makeindex` and `xindy` compatible `.idx` output.
- Default after-phrase tagging uses typed macros; optional inline mode.

## Non-Functional Requirements
- Deterministic runs where possible; log all changes.
- Clear diff/report for author review.
- CLI-first UX; core logic reusable for a future standalone app.
