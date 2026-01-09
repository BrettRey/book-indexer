# Tagging Rules (v0)

## Inline Macros
- Use typed macros: `\\sindex`, `\\nindex`, `\\lindex`.

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

## Ranges
- Use range markers when a concept is discussed contiguously.
```tex
finite difference method\sindex{finite difference method|(}
... (discussion)
\sindex{finite difference method|)}
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
