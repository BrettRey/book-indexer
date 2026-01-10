# LangSci 81 Example

This folder captures a **snapshot** of the lexicon and LLM suggestions used during index tooling work for LangSci book 81. The goal is to provide a reusable example for future books, not to reindex book 81.

## Files

- `lexicon.yaml`: Snapshot of the lexicon after LLM-assisted updates were applied.
- `llm_updates.json`: LLM-proposed updates produced via the Gemini CLI wrapper.

## Commands Used (example)

```
python -m book_indexer.cli assist .gemini/tmp/langsci-81/chapters \
  --lexicon lexicon.yaml \
  --report llm_report.json \
  --provider command \
  --llm-command "scripts/gemini_llm.py"
```

## Build Artifacts (not tracked)

The full LaTeX build (including `main.pdf` and index files) lives under:

```
.gemini/tmp/langsci-81/
```

That directory is intentionally ignored in git. If you need the compiled PDF or `.idx` outputs, pull them from that location.
