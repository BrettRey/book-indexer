# Tagging Rules (v0)

## Index Macros
- Use typed macros: `\\sindex`, `\\nindex`, `\\lindex`.
- Insert tags immediately after the phrase (do not replace the phrase).
- Prefer canonical forms from the lexicon; keep visible text unchanged.

## Placement
- Insert tag immediately after the phrase.
- Place tag before trailing punctuation.
- Avoid inserting inside macro arguments or math environments.

## Skip Environments (Default, Configurable)
- `verbatim`, `Verbatim`, `lstlisting`, `minted`, `tikzpicture`
- math-like: `equation`, `equation*`, `align`, `align*`, `alignat`, `alignat*`,
  `gather`, `gather*`, `multline`, `multline*`, `displaymath`, `math`,
  `eqnarray`, `eqnarray*`

## Examples

**Subject term**
```tex
finite difference method\sindex{finite difference method}
```

**Name**
```tex
von Neumann\nindex{von Neumann, John}
```

**Lexical item**
```tex
ablaut\lindex{ablaut}
```

## Sorting vs. Display
- If the displayed index form includes formatting, provide a sort key:
```tex
n-grams\sindex{n-grams@\textit{n-grams}}
```

## Hierarchy
- Use `!` for subentries:
```tex
primary modeling system\sindex{modeling system!primary}
```

## Ranges
- Use range markers when a concept is discussed contiguously.
```tex
finite difference method\sindex{finite difference method|(}
... (discussion)
\sindex{finite difference method|)}
```

## Cross-References
```tex
FDM\sindex{FDM|see{finite difference method}}
finite difference method\sindex{finite difference method}\sindex{finite difference method|seealso{finite element method}}
```

### Cross-Ref Targets with Hierarchy
- If the canonical target is hierarchical (e.g., `English!British`), the tagger
  will render the target as a readable display string (e.g., `English, British`)
  in `see`/`seealso` output.

Lexicon rule:
```yaml
rules:
  synonym_mode: see
```

## LLM Judgment (Optional)

Use the LLM to drop tags that are merely mentioned in passing:
```
python -m book_indexer.cli judge chapters/ --report llm_judgment.json
python -m book_indexer.cli apply-judgment llm_judgment.json
```

## Suggestions (when existing tags differ)
Plain text:
```
SUGGESTION: Replace \sindex{FDM} with \sindex{finite difference method}
Reason: canonical term in lexicon, synonym match
Location: chapter2.tex:134
```

JSON:
```json
{
  "file": "chapter2.tex",
  "line": 134,
  "existing": "\\sindex{FDM}",
  "suggested": "\\sindex{finite difference method}",
  "reason": "lexicon synonym -> canonical",
  "confidence": 0.86
}
```
