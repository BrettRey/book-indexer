# Book Indexer

Tool for creating indexes for LaTeX academic books.

- **Primary use:** HPC book ("Words That Won't Hold Still")
- **Secondary use:** Share with LangSci Press

## Status

Core tagging + lexicon pipeline implemented with optional LLM assist.
CLI is currently run via `python -m book_indexer.cli` (no packaged entry point yet).

## Quick Start

Scan existing tags:
```
python -m book_indexer.cli scan chapters/ --output lexicon.yaml
```

Tag with canonical lexicon entries:
```
python -m book_indexer.cli tag chapters/ --lexicon lexicon.yaml --mode auto --strip
```

## LLM Assist (Optional)

Generate lexicon normalization suggestions with an LLM:
```
python -m book_indexer.cli assist chapters/ --lexicon lexicon.yaml --report llm_report.json
```

Use the Gemini CLI as a provider:
```
python -m book_indexer.cli assist .gemini/tmp/langsci-81/chapters \
  --lexicon lexicon.yaml \
  --report llm_report.json \
  --provider command \
  --llm-command "scripts/gemini_llm.py"
```

Apply suggestions directly to the lexicon:
```
python -m book_indexer.cli assist chapters/ --lexicon lexicon.yaml --report llm_report.json --apply
```
