"""LaTeX index tagger for book indexer.

Handles extraction, stripping, and insertion of index tags in LaTeX files.
"""

import os
import re
import glob
from typing import Optional
from book_indexer.lexicon import Lexicon


# Index command patterns
# Group 1: command name (is, isi, il, ili, in, ini, index, sindex, nindex, lindex)
# Group 2: optional bracketed argument [...]
# Group 3: content inside braces
INDEX_TAG_PATTERN = re.compile(
    r'\\(isi?|ili?|ini?|index|sindex|nindex|lindex)'  # command name
    r'(\[[^\]]*\])?'  # optional [...] argument
    r'\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}'  # content with possible nested braces (one level)
)

# Environments to skip (no tagging inside these)
SKIP_ENVIRONMENTS = {
    'verbatim', 'Verbatim', 'lstlisting', 'minted', 'tikzpicture',
    'equation', 'equation*', 'align', 'align*', 'alignat', 'alignat*',
    'gather', 'gather*', 'multline', 'multline*', 'displaymath', 'math',
    'eqnarray', 'eqnarray*', 'tabular', 'tabular*', 'array',
}

# Commands whose arguments should not be tagged
SKIP_COMMANDS = {
    'cite', 'citep', 'citet', 'citealt', 'citealp', 'citeauthor', 'citeyear',
    'ref', 'label', 'eqref', 'pageref', 'autoref', 'nameref',
    'url', 'href', 'includegraphics', 'input', 'include',
    'bibliographystyle', 'bibliography', 'addbibresource',
    'usepackage', 'documentclass', 'newcommand', 'renewcommand',
    'caption', 'footnote',  # these could be tagged but often cause issues
}


def infer_type_from_command(cmd: str) -> str:
    """Infer index entry type from command name."""
    if cmd in ('il', 'ili', 'lindex'):
        return 'language'
    elif cmd in ('in', 'ini', 'nindex'):
        return 'name'
    else:
        return 'subject'


def extract_visible_text(content: str) -> str:
    """Extract visible text from index tag content.

    Handles formatting codes:
    - @ separates sort key from display: "sortkey@display" -> "display"
    - | introduces formatting: "term|textbf" -> "term"
    - ! separates hierarchy levels: "main!sub" -> "sub"
    - (| and |) are range markers, not content
    """
    # Handle range markers first
    if content.endswith('|(') or content.endswith('|)'):
        content = content[:-2]

    # Handle sort key (take display part after @)
    if '@' in content:
        content = content.split('@', 1)[1]

    # Handle formatting command (take term before |)
    if '|' in content:
        content = content.split('|', 1)[0]

    # Handle hierarchy (take last level)
    if '!' in content:
        content = content.split('!')[-1]

    return content.strip()


def is_inline_command(cmd: str) -> bool:
    """Check if command is inline (ends with 'i' except 'in')."""
    return cmd.endswith('i') and cmd != 'in'


class Tagger:
    """Handles index tag operations on LaTeX files."""

    def __init__(self, lexicon: Optional[Lexicon] = None):
        self.lexicon = lexicon

    def extract_from_file(self, file_path: str) -> list[dict]:
        """Extract all index entries from a single file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return self._extract_from_content(content, file_path)

    def _extract_from_content(self, content: str, source: str = '') -> list[dict]:
        """Extract index entries from LaTeX content."""
        entries = []

        for match in INDEX_TAG_PATTERN.finditer(content):
            cmd = match.group(1)
            tag_content = match.group(3)

            # Get canonical term (handling @, |, !)
            term = extract_visible_text(tag_content)
            if not term:
                continue

            entry_type = infer_type_from_command(cmd)

            entries.append({
                'term': term,
                'type': entry_type,
                'command': cmd,
                'raw': tag_content,
                'source': source,
                'position': match.start(),
            })

        return entries

    def extract_lexicon_from_directory(self, dir_path: str) -> list[dict]:
        """Scan directory for .tex files and extract unique terms."""
        seen = {}  # term_lower -> entry dict

        files = glob.glob(os.path.join(dir_path, '**', '*.tex'), recursive=True)
        for file_path in files:
            entries = self.extract_from_file(file_path)
            for entry in entries:
                key = entry['term'].lower()
                if key not in seen:
                    seen[key] = {
                        'term': entry['term'],
                        'type': entry['type'],
                    }

        return list(seen.values())

    def strip_tags(self, dir_path: str) -> dict[str, int]:
        """Remove all index tags from .tex files in directory.

        Returns dict of {filename: count_stripped}.
        """
        results = {}
        files = glob.glob(os.path.join(dir_path, '**', '*.tex'), recursive=True)

        for file_path in files:
            count = self._strip_file(file_path)
            if count > 0:
                results[file_path] = count

        return results

    def _strip_file(self, file_path: str) -> int:
        """Strip index tags from a single file. Returns count stripped."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        count = 0

        def replace_func(match):
            nonlocal count
            count += 1
            cmd = match.group(1)
            tag_content = match.group(3)

            # Inline commands: replace with visible text
            if is_inline_command(cmd):
                return extract_visible_text(tag_content)
            # Non-inline: remove entirely
            return ''

        new_content = INDEX_TAG_PATTERN.sub(replace_func, content)

        if count > 0:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

        return count

    def tag_directory(self, dir_path: str, mode: str = 'assist') -> dict[str, list]:
        """Apply index tags to .tex files in directory.

        Modes:
        - 'guide': report only, no changes
        - 'assist': safe insertions, report ambiguous
        - 'auto': full tagging

        Returns dict of {filename: list of actions taken/suggested}.
        """
        if not self.lexicon:
            raise ValueError("Lexicon required for tagging")

        results = {}
        files = glob.glob(os.path.join(dir_path, '**', '*.tex'), recursive=True)

        for file_path in files:
            actions = self._tag_file(file_path, mode)
            if actions:
                results[file_path] = actions

        return results

    def _tag_file(self, file_path: str, mode: str) -> list[dict]:
        """Tag a single file. Returns list of actions."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        actions = []

        # Find regions to skip
        skip_regions = self._find_skip_regions(content)

        # Find already tagged terms to avoid duplicates
        already_tagged = self._find_tagged_positions(content)

        # Get terms from lexicon, sorted by length (longer first to avoid partial matches)
        terms = []
        for entry in self.lexicon:
            term = entry['term']
            if len(term) > 2:  # Skip very short terms
                terms.append((term, entry))
            for syn in entry.get('synonyms', []):
                if len(syn) > 2:
                    terms.append((syn, entry))

        terms.sort(key=lambda x: len(x[0]), reverse=True)

        # Collect all matches first
        all_matches = []  # (start, end, matched_text, entry)
        matched_ranges = set()  # Track what we've already matched to avoid overlaps

        for term, entry in terms:
            # Build pattern for this term with word boundaries
            escaped = re.escape(term)
            pattern = re.compile(
                r'(?<![\\a-zA-Z])'  # not preceded by backslash or letter
                + escaped
                + r'(?![a-zA-Z])',  # not followed by letter
                re.IGNORECASE
            )

            for match in pattern.finditer(content):
                start = match.start()
                end = match.end()
                matched_text = match.group()

                # Skip if in a protected region
                if self._in_skip_region(start, end, skip_regions):
                    continue

                # Skip if already tagged
                if self._is_already_tagged(start, end, already_tagged):
                    continue

                # Skip if inside a command argument
                if self._in_command_argument(content, start):
                    continue

                # Skip if overlapping with a previous match (longer terms take priority)
                overlaps = False
                for ms, me in matched_ranges:
                    if start < me and end > ms:
                        overlaps = True
                        break
                if overlaps:
                    continue

                matched_ranges.add((start, end))
                all_matches.append((start, end, matched_text, entry))

        # Sort matches by position (descending) so we can apply from end to start
        # This way, earlier positions aren't affected by later insertions
        all_matches.sort(key=lambda x: x[0], reverse=True)

        # Apply matches (from end to start)
        new_content = content
        for start, end, matched_text, entry in all_matches:
            entry_type = entry.get('type', 'subject')
            canonical = entry['term']

            action = {
                'term': matched_text,
                'canonical': canonical,
                'type': entry_type,
                'position': start,
                'line': content[:start].count('\n') + 1,
            }

            if mode == 'guide':
                action['action'] = 'suggest'
                actions.append(action)
            elif mode in ('assist', 'auto'):
                tag = self._make_tag(matched_text, canonical, entry_type)
                new_content = new_content[:start] + tag + new_content[end:]
                action['action'] = 'tagged'
                actions.append(action)

        # Reverse actions list so it's in document order
        actions.reverse()

        # Write if changes were made
        if mode != 'guide' and new_content != content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

        return actions

    def _make_tag(self, text: str, canonical: str, entry_type: str) -> str:
        """Create an inline index tag for the given text."""
        # Use inline versions that preserve visible text
        if entry_type == 'language':
            cmd = 'ili'
        elif entry_type == 'name':
            cmd = 'ini'
        else:
            cmd = 'isi'

        # If text differs from canonical (case, synonym), use sort@display format
        if text.lower() != canonical.lower():
            return f'\\{cmd}{{{canonical}@{text}}}'
        else:
            return f'\\{cmd}{{{text}}}'

    def _find_skip_regions(self, content: str) -> list[tuple[int, int]]:
        """Find regions that should not be tagged (math, verbatim, etc.)."""
        regions = []

        # Inline math: $...$
        for match in re.finditer(r'\$[^$]+\$', content):
            regions.append((match.start(), match.end()))

        # Display math: \[...\]
        for match in re.finditer(r'\\\[.*?\\\]', content, re.DOTALL):
            regions.append((match.start(), match.end()))

        # Environments
        for env in SKIP_ENVIRONMENTS:
            pattern = re.compile(
                r'\\begin\{' + re.escape(env) + r'\}.*?\\end\{' + re.escape(env) + r'\}',
                re.DOTALL
            )
            for match in pattern.finditer(content):
                regions.append((match.start(), match.end()))

        # Comments (% to end of line)
        for match in re.finditer(r'(?<!\\)%.*$', content, re.MULTILINE):
            regions.append((match.start(), match.end()))

        return regions

    def _find_tagged_positions(self, content: str) -> set[tuple[int, int]]:
        """Find positions of existing index tags."""
        positions = set()
        for match in INDEX_TAG_PATTERN.finditer(content):
            positions.add((match.start(), match.end()))
        return positions

    def _in_skip_region(self, start: int, end: int, regions: list[tuple[int, int]]) -> bool:
        """Check if position overlaps with any skip region."""
        for reg_start, reg_end in regions:
            if start < reg_end and end > reg_start:
                return True
        return False

    def _is_already_tagged(self, start: int, end: int, tagged: set[tuple[int, int]]) -> bool:
        """Check if position is within an existing tag."""
        for tag_start, tag_end in tagged:
            # Check if our match is inside a tag
            if start >= tag_start and end <= tag_end:
                return True
            # Check if overlapping
            if start < tag_end and end > tag_start:
                return True
        return False

    def _in_command_argument(self, content: str, pos: int) -> bool:
        """Check if position is inside a command's argument.
        
        Only skips if the command is in SKIP_COMMANDS or is an index command.
        """
        # Look backwards for an unmatched {
        depth = 0
        i = pos - 1
        while i >= 0:
            char = content[i]
            if char == '}':
                depth += 1
            elif char == '{':
                if depth > 0:
                    depth -= 1
                else:
                    # Found unmatched {, check if preceded by command
                    # Look for \command pattern before this {
                    before = content[max(0, i-50):i].rstrip()
                    cmd_match = re.search(r'\\([a-zA-Z]+)(\[[^\]]*\])?\s*$', before)
                    if cmd_match:
                        cmd_name = cmd_match.group(1)
                        # Only skip if it's a command we explicitly want to skip
                        if cmd_name in SKIP_COMMANDS:
                            return True
                        if cmd_name in ('is', 'isi', 'il', 'ili', 'in', 'ini',
                                       'index', 'sindex', 'nindex', 'lindex'):
                            return True
                        # If it's \begin{...}, the content after } is NOT an argument
                        if cmd_name == 'begin':
                            return True # We are inside the {env_name} argument
                    
                    # For other commands, we assume it's safe to tag the argument 
                    # (e.g., \section{Term}, \emph{Term})
                    return False
            elif char == '\\':
                # Escaped character, skip
                i -= 1
            i -= 1
        return False
