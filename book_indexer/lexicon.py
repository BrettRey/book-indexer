"""Lexicon management for book indexer.

Handles loading, saving, and querying of index terms stored in YAML format.
"""

import os
import yaml
from typing import Optional


class Lexicon:
    """Manages a collection of index entries with terms, types, and synonyms."""

    def __init__(self, lexicon_path: Optional[str] = None):
        self.entries: list[dict] = []
        self.rules: dict = {}
        self._term_index: dict[str, dict] = {}  # term -> entry (for fast lookup)
        self._synonym_index: dict[str, dict] = {}  # synonym -> entry

        if lexicon_path and os.path.exists(lexicon_path):
            self.load(lexicon_path)
        elif lexicon_path:
            print(f"Warning: Lexicon file {lexicon_path} not found. Starting empty.")

    def load(self, path: str) -> None:
        """Load lexicon from YAML file."""
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        if data and 'entries' in data:
            self.rules = data.get('rules', {}) or {}
            self.entries = data['entries']
            self._build_indices()

    def save(self, path: str) -> None:
        """Save lexicon to YAML file."""
        data = {'entries': self.entries}
        if self.rules:
            data['rules'] = self.rules
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

    def _build_indices(self) -> None:
        """Build lookup indices for fast term matching."""
        self._term_index.clear()
        self._synonym_index.clear()

        for entry in self.entries:
            term = entry.get('term', '')
            if term:
                self._term_index[term.lower()] = entry

            # Index synonyms
            for syn in entry.get('synonyms', []):
                if syn:
                    self._synonym_index[syn.lower()] = entry

    def add_entry(self, term: str, entry_type: str = 'subject',
                  synonyms: Optional[list[str]] = None) -> None:
        """Add a new entry to the lexicon."""
        entry = {
            'term': term,
            'type': entry_type,
        }
        if synonyms:
            entry['synonyms'] = synonyms

        self.entries.append(entry)
        self._term_index[term.lower()] = entry
        for syn in (synonyms or []):
            self._synonym_index[syn.lower()] = entry

    def get_entry(self, term: str) -> Optional[dict]:
        """Look up entry by term or synonym (case-insensitive)."""
        term_lower = term.lower()
        return self._term_index.get(term_lower) or self._synonym_index.get(term_lower)

    def get_terms(self) -> list[str]:
        """Return list of all indexable terms (including synonyms)."""
        terms = list(self._term_index.keys())
        terms.extend(self._synonym_index.keys())
        return terms

    def get_canonical_term(self, term: str) -> Optional[str]:
        """Get the canonical form of a term (for synonyms)."""
        entry = self.get_entry(term)
        return entry['term'] if entry else None

    def get_rule(self, key: str, default=None):
        """Return a rule value from the lexicon rules block."""
        return self.rules.get(key, default)

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self):
        return iter(self.entries)
