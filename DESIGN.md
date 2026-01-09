# Book Indexer Design

## Architecture
- CLI front-end with a reusable core library.
- Deterministic heuristics as baseline; optional agent assistance.

## Pipeline
1. **Parse** LaTeX into a structural model (chapters/sections/paragraphs).
2. **Detect candidates** for terms, names, and lexical items.
3. **Classify** candidates into index types (language/lexical, subject, name).
4. **Normalize** entry forms using lexicon + heuristics.
5. **Structure** entries into hierarchy (term!subterm).
6. **Range reasoning** to choose ranges vs single pages.
7. **Cross-refs** (`see`, `see also`) from synonym and related-term signals.
8. **Write tags** back into LaTeX sources.
9. **Emit** `.idx` files and an audit report.

## Data Model (conceptual)
- **Entry**: canonical label, index type, synonyms, hierarchy hints.
- **Occurrence**: source location + context span + confidence.
- **CrossRef**: `see`/`see also` edges between entries.

## Tagging Strategy
- Preserve existing `\\index{}` and custom index macros.
- Insert new tags adjacent to relevant phrases with minimal formatting disruption.
- Idempotent behavior: re-running should not duplicate tags.

## Range Decisions
- Prefer ranges when occurrences are contiguous in structure and sustained in context.
- Avoid ranges that include unrelated content.
- Allow author override via inline directives or lexicon hints.

## Lexicon File (YAML/JSON)
- Canonical entry name
- Index type
- Synonyms and preferred display form
- Hierarchy hints
- `see` / `see also` mappings

## CLI Commands (initial)
- `scan`: analyze sources, report candidate entries.
- `tag`: insert tags according to mode (`guide`/`assist`/`auto`).
- `build`: emit `.idx` for `makeindex`/`xindy`.
- `lexicon init`: create a starter lexicon from detected candidates.

## Author Participation
- `guide`: preview-only; produce a review report.
- `assist`: apply safe insertions and request confirmation for ambiguous items.
- `auto`: full tagging with full audit trail.

## Chosen Approach (v0)
- **Lexicon format:** YAML with an optional `rules` block.
- **Parsing:** Hybrid (AST for structure + regex/token scanning for tagging).
- **Tagging:** Inline typed macros (`\\sindex`, `\\nindex`, `\\lindex`) plus a report of suggested improvements.

## Index Macros (Chosen)
- Use `imakeidx` (or equivalent) to define three named indexes and wrap them in typed macros.
- Example preamble snippet (tool auto-adds unless definitions already exist):
  - `\\makeindex[name=subject,title=Subject Index]`
  - `\\makeindex[name=name,title=Name Index]`
  - `\\makeindex[name=lex,title=Language/lexical Index]`
  - `\\newcommand{\\sindex}[1]{\\index[subject]{#1}}`
  - `\\newcommand{\\nindex}[1]{\\index[name]{#1}}`
  - `\\newcommand{\\lindex}[1]{\\index[lex]{#1}}`

## Preamble Insertion (by Mode)
- If definitions are missing:
  - `guide`: report proposed additions only.
  - `assist`: insert definitions by default.
  - `auto`: insert definitions by default.
- If definitions already exist:
  - `guide`: report and request author input.
  - `assist`: report and require explicit confirmation/flag to change.
  - `auto`: keep existing definitions; warn if conflicts are detected.

## Parsing (Hybrid)
- Build a structural outline from a LaTeX AST to determine safe insertion regions.
- Scan only text nodes for candidate phrases; avoid macro arguments and code-like blocks.
- Maintain stable source offsets to preserve formatting and minimize diffs.

## Tag Insertion Rules (Default)
- Insert immediately after the tagged phrase and before trailing punctuation.
- Do not insert inside macro arguments or within math environments.
- Idempotent: never duplicate an existing tag.
- Preserve author tags; record any suggested improvements separately.

## Skip Environments (Default, Configurable)
- `verbatim`, `Verbatim`, `lstlisting`, `minted`, `tikzpicture`
- math-like: `equation`, `equation*`, `align`, `align*`, `alignat`, `alignat*`,
  `gather`, `gather*`, `multline`, `multline*`, `displaymath`, `math`,
  `eqnarray`, `eqnarray*`

## Suggestion Report (Default)
- Emit a human-readable report plus JSON for automation.
- Example fields: `file`, `line`, `existing`, `suggested`, `reason`, `confidence`.
