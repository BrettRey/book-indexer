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

## End-to-End Workflow (LLM → PDF)

LLM assist only updates the lexicon. To affect the index in the PDF you must:

1) Apply LLM suggestions to the lexicon:
```
python -m book_indexer.cli assist chapters/ \
  --lexicon lexicon.yaml \
  --report llm_report.json \
  --provider command \
  --llm-command "scripts/gemini_llm.py" \
  --apply
```

2) Re-tag the LaTeX sources using the updated lexicon:
```
python -m book_indexer.cli tag chapters/ \
  --lexicon lexicon.yaml \
  --mode auto \
  --strip
```

3) (Optional) Ask an LLM to drop tags that are only mentioned in passing:
```
python -m book_indexer.cli judge chapters/ --report llm_judgment.json
python -m book_indexer.cli apply-judgment llm_judgment.json
```

4) Rebuild the LaTeX book (e.g., `latexmk`) to refresh the index and PDF.

If you already have a saved LLM report, you can apply it without rerunning the LLM:
```
python -m book_indexer.cli apply-report llm_report.json --lexicon lexicon.yaml
```

## LLM Tag Judgment (Optional)

Use an LLM to prune tags that are only mentioned in passing:
```
python -m book_indexer.cli judge chapters/ --report llm_judgment.json
```

Resume a partial run (skips already-decided tags and checkpoints each batch):
```
python -m book_indexer.cli judge chapters/ \
  --report llm_judgment.json \
  --resume
```

Apply removals from a saved judgment report:
```
python -m book_indexer.cli apply-judgment llm_judgment.json
```

Use the Gemini CLI as a provider:
```
python -m book_indexer.cli judge .gemini/tmp/langsci-81/chapters \
  --report llm_judgment.json \
  --provider command \
  --llm-command "scripts/gemini_llm.py"
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

Add `--progress` (or `-v`) to see batch-level status while the LLM runs.

If Gemini returns invalid JSON, check `gemini_llm_error.txt` in your current working directory for the raw response.

Apply suggestions directly to the lexicon:
```
python -m book_indexer.cli assist chapters/ --lexicon lexicon.yaml --report llm_report.json --apply
```

## Indexes-Only Preview (Optional)

Generate a lightweight PDF of the indexes without building the full book:
```
python scripts/build_indexes_only.py chapters/ --output-dir .
makeindex -o main.lnd main.ldx
makeindex -o main.snd main.sdx
xelatex -interaction=nonstopmode -halt-on-error indexes_only.tex
```

## Examples

- `examples/langsci-81/` contains a lexicon snapshot and LLM update sample for reference.
