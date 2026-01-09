# Book Indexer

Tool for creating indexes for LaTeX academic books.

- **Primary use:** HPC book ("Words That Won't Hold Still")
- **Secondary use:** Share with LangSci Press

## Status

Core tagging + lexicon pipeline implemented with optional LLM assist.

## Quick Start

Scan existing tags:
```
book-indexer scan chapters/ --output lexicon.yaml
```

Tag with canonical lexicon entries:
```
book-indexer tag chapters/ --lexicon lexicon.yaml --mode auto --strip
```

## LLM Assist (Optional)

Generate lexicon normalization suggestions with an LLM:
```
book-indexer assist chapters/ --lexicon lexicon.yaml --report llm_report.json
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
book-indexer assist chapters/ --lexicon lexicon.yaml --report llm_report.json --apply
```
