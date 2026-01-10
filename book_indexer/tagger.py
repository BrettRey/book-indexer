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

COMMAND_SETS = {
    'typed': {
        'subject': 'sindex',
        'name': 'nindex',
        'language': 'lindex',
    },
    'langsci': {
        'subject': 'is',
        'name': 'in',
        'language': 'il',
    },
}

INLINE_COMMANDS = {
    'subject': 'isi',
    'name': 'ini',
    'language': 'ili',
}

FOLLOWING_INDEX_TAG_PATTERN = re.compile(
    r'\s*\\(isi?|ili?|ini?|index|sindex|nindex|lindex)\b'
)

LATEX_COMMAND_PATTERN = re.compile(r'\\[a-zA-Z]+\*?(?:\[[^\]]*\])?')

HIERARCHY_STOPWORDS = {
    'a', 'an', 'and', 'for', 'in', 'of', 'on', 'or', 'the', 'to', 'with',
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

    def __init__(self, lexicon: Optional[Lexicon] = None,
                 placement: str = 'after', command_set: str = 'auto'):
        self.lexicon = lexicon
        self.placement = placement
        self.command_set = command_set
        self._auto_hierarchy = self._build_auto_hierarchy() if lexicon else {}

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

    def _resolve_command_set(self, content: str) -> dict[str, str]:
        """Resolve which index command set to use for tagging."""
        if self.placement == 'inline':
            return INLINE_COMMANDS

        if self.command_set != 'auto':
            return COMMAND_SETS.get(self.command_set, COMMAND_SETS['typed'])

        if re.search(r'\\(sindex|nindex|lindex)\b', content):
            return COMMAND_SETS['typed']
        if re.search(r'\\(is|il|in|isi|ili|ini)\b', content):
            return COMMAND_SETS['langsci']
        return COMMAND_SETS['typed']

    def _build_auto_hierarchy(self) -> dict[str, str]:
        """Infer simple hierarchy from shared multiword suffixes."""
        if not self.lexicon:
            return {}
        if not self.lexicon.get_rule('auto_hierarchy', True):
            return {}

        min_words = int(self.lexicon.get_rule('auto_hierarchy_min_words', 2))
        max_words = int(self.lexicon.get_rule('auto_hierarchy_max_words', 4))
        min_group = int(self.lexicon.get_rule('auto_hierarchy_min_group', 2))

        by_type: dict[str, list[dict]] = {}
        for entry in self.lexicon:
            entry_type = entry.get('type', 'subject')
            by_type.setdefault(entry_type, []).append(entry)

        mapping: dict[str, str] = {}

        for entries in by_type.values():
            suffix_groups: dict[str, int] = {}
            suffix_display: dict[str, str] = {}
            term_tokens: dict[str, list[str]] = {}

            for entry in entries:
                term = entry.get('term', '')
                if not term:
                    continue
                tokens = term.split()
                term_tokens[term] = tokens
                max_n = min(max_words, len(tokens))
                for n in range(min_words, max_n + 1):
                    suffix_tokens = tokens[-n:]
                    if suffix_tokens[0].lower() in HIERARCHY_STOPWORDS:
                        continue
                    suffix_key = ' '.join(t.lower() for t in suffix_tokens)
                    suffix_groups[suffix_key] = suffix_groups.get(suffix_key, 0) + 1
                    if suffix_key not in suffix_display:
                        suffix_display[suffix_key] = ' '.join(suffix_tokens)

            for entry in entries:
                term = entry.get('term', '')
                if not term:
                    continue
                tokens = term_tokens.get(term, term.split())
                max_n = min(max_words, len(tokens))
                best_key = None
                best_n = None
                for n in range(max_n, min_words - 1, -1):
                    suffix_key = ' '.join(t.lower() for t in tokens[-n:])
                    if tokens[-n].lower() in HIERARCHY_STOPWORDS:
                        continue
                    if suffix_groups.get(suffix_key, 0) >= min_group:
                        best_key = suffix_key
                        best_n = n
                        break

                if best_key and best_n:
                    prefix_tokens = tokens[:-best_n]
                    if prefix_tokens:
                        head = suffix_display[best_key]
                        sub = ' '.join(prefix_tokens)
                        mapping[term.lower()] = f"{head}!{sub}"

        return mapping

    def _split_hierarchy(self, value) -> list[str]:
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str):
            return [v.strip() for v in value.split('!') if v.strip()]
        return []

    def _strip_latex(self, text: str) -> str:
        """Strip LaTeX commands for sorting purposes."""
        text = LATEX_COMMAND_PATTERN.sub('', text)
        text = text.replace('{', '').replace('}', '')
        text = text.replace('~', ' ')
        text = text.replace('$', '')
        text = re.sub(r'\\([#$%&_{}])', r'\1', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _strip_sort_key(self, text: str) -> str:
        """Drop sort keys (foo@bar -> bar) for display-only output."""
        if '@' in text:
            return text.split('@', 1)[1]
        return text

    def _format_index_levels(self, levels: list[str]) -> str:
        formatted = []
        for level in levels:
            display = level.strip()
            if not display:
                continue
            sort_key = self._strip_latex(display)
            if sort_key and sort_key != display:
                formatted.append(f"{sort_key}@{display}")
            else:
                formatted.append(display)
        return '!'.join(formatted)

    def _normalize_crossref_target(self, target: str) -> str:
        target = target.strip()
        if not target:
            return ''
        if '!' in target:
            levels = self._split_hierarchy(target)
        else:
            entry = self.lexicon.get_entry(target) if self.lexicon else None
            if entry:
                if entry.get('hierarchy'):
                    levels = self._split_hierarchy(entry.get('hierarchy'))
                else:
                    levels = [entry.get('display', entry.get('term', target))]
            else:
                levels = [target]
        display_levels = [self._strip_sort_key(level) for level in levels if level]
        if not display_levels:
            return ''
        if len(display_levels) == 1:
            return display_levels[0]
        return ', '.join(display_levels)

    def _has_following_index_tag(self, content: str, end: int) -> bool:
        return FOLLOWING_INDEX_TAG_PATTERN.match(content, end) is not None

    def _entry_levels(self, entry: dict) -> list[str]:
        if entry.get('hierarchy'):
            levels = self._split_hierarchy(entry.get('hierarchy'))
        else:
            auto = self._auto_hierarchy.get(entry.get('term', '').lower())
            if auto:
                levels = self._split_hierarchy(auto)
            else:
                levels = [entry.get('display', entry.get('term', ''))]
        return [lvl for lvl in levels if lvl]

    def _build_index_tags(
        self,
        entry: dict,
        source_term: str,
        entry_type: str,
        is_synonym: bool,
        synonym_mode: str,
        command_set: dict[str, str],
        ref_state: dict[str, set[str]],
    ) -> list[str]:
        cmd = command_set.get(entry_type, command_set['subject'])
        tags: list[str] = []

        if is_synonym and synonym_mode == 'see':
            see_entry = self._format_index_levels([source_term])
            see_target = self._normalize_crossref_target(entry.get('term', source_term))
            if see_entry and see_target:
                key = f"see|{see_entry}|{see_target}"
                if key not in ref_state['see']:
                    tags.append(f"\\{cmd}{{{see_entry}|see{{{see_target}}}}}")
                    ref_state['see'].add(key)
            return tags

        see = entry.get('see')
        if see:
            targets = see if isinstance(see, list) else [see]
            base_levels = self._entry_levels(entry)
            base_entry = self._format_index_levels(base_levels)
            if not base_entry:
                return tags
            for target in targets:
                target_entry = self._normalize_crossref_target(str(target))
                if not target_entry:
                    continue
                key = f"see|{base_entry}|{target_entry}"
                if key in ref_state['see']:
                    continue
                tags.append(f"\\{cmd}{{{base_entry}|see{{{target_entry}}}}}")
                ref_state['see'].add(key)
            return tags

        base_levels = self._entry_levels(entry)
        base_entry = self._format_index_levels(base_levels)
        if base_entry:
            tags.append(f"\\{cmd}{{{base_entry}}}")
        else:
            return tags

        see_also = entry.get('see_also')
        if see_also:
            targets = see_also if isinstance(see_also, list) else [see_also]
            for target in targets:
                target_entry = self._normalize_crossref_target(str(target))
                if not target_entry:
                    continue
                key = f"seealso|{base_entry}|{target_entry}"
                if key in ref_state['seealso']:
                    continue
                tags.append(f"\\{cmd}{{{base_entry}|seealso{{{target_entry}}}}}")
                ref_state['seealso'].add(key)

        return tags

    def _make_inline_tag(self, text: str, entry_type: str) -> str:
        cmd = INLINE_COMMANDS.get(entry_type, INLINE_COMMANDS['subject'])
        return f"\\{cmd}{{{text}}}"

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
        ref_state = {'see': set(), 'seealso': set()}

        for file_path in files:
            actions = self._tag_file(file_path, mode, ref_state)
            if actions:
                results[file_path] = actions

        return results

    def _tag_file(self, file_path: str, mode: str,
                  ref_state: Optional[dict[str, set[str]]] = None) -> list[dict]:
        """Tag a single file. Returns list of actions."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        actions = []
        if ref_state is None:
            ref_state = {'see': set(), 'seealso': set()}

        # Find regions to skip
        skip_regions = self._find_skip_regions(content)

        # Find already tagged terms to avoid duplicates
        already_tagged = self._find_tagged_positions(content)

        command_set = self._resolve_command_set(content)
        synonym_mode = 'canonical'
        if self.lexicon:
            synonym_mode = str(self.lexicon.get_rule('synonym_mode', 'canonical')).lower()

        # Get terms from lexicon, sorted by length (longer first to avoid partial matches)
        terms = []
        for entry in self.lexicon:
            term = entry['term']
            if len(term) > 2:  # Skip very short terms
                terms.append((term, entry, False))
            for syn in entry.get('synonyms', []):
                if len(syn) > 2:
                    terms.append((syn, entry, True))

        terms.sort(key=lambda x: len(x[0]), reverse=True)

        # Collect all matches first
        all_matches = []  # (start, end, matched_text, entry, is_synonym, source_term)
        matched_ranges = set()  # Track what we've already matched to avoid overlaps

        for source_term, entry, is_synonym in terms:
            # Build pattern for this term with word boundaries
            escaped = re.escape(source_term)
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

                # Skip if an index tag already follows this term
                if self._has_following_index_tag(content, end):
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
                all_matches.append((start, end, matched_text, entry, is_synonym, source_term))

        # Sort matches by position (descending) so we can apply from end to start
        # This way, earlier positions aren't affected by later insertions
        all_matches.sort(key=lambda x: x[0], reverse=True)

        # Apply matches (from end to start)
        new_content = content
        insertions = []
        for start, end, matched_text, entry, is_synonym, source_term in all_matches:
            entry_type = entry.get('type', 'subject')
            canonical = entry['term']

            action = {
                'term': matched_text,
                'canonical': canonical,
                'type': entry_type,
                'position': start,
                'line': content[:start].count('\n') + 1,
            }

            if self.placement == 'inline':
                tag = self._make_inline_tag(matched_text, entry_type)
                if mode == 'guide':
                    action['action'] = 'suggest'
                    action['tag'] = tag
                    actions.append(action)
                elif mode in ('assist', 'auto'):
                    new_content = new_content[:start] + tag + new_content[end:]
                    action['action'] = 'tagged'
                    action['tag'] = tag
                    actions.append(action)
                continue

            tags = self._build_index_tags(
                entry=entry,
                source_term=source_term,
                entry_type=entry_type,
                is_synonym=is_synonym,
                synonym_mode=synonym_mode,
                command_set=command_set,
                ref_state=ref_state,
            )
            if not tags:
                continue

            action['tags'] = tags
            if mode == 'guide':
                action['action'] = 'suggest'
                actions.append(action)
            elif mode in ('assist', 'auto'):
                insertions.append((end, ''.join(tags)))
                action['action'] = 'tagged'
                actions.append(action)

        # Reverse actions list so it's in document order
        actions.reverse()

        # Write if changes were made
        if mode != 'guide':
            if insertions:
                insertions.sort(key=lambda x: x[0], reverse=True)
                for pos, tag in insertions:
                    new_content = new_content[:pos] + tag + new_content[pos:]
            if new_content != content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)

        return actions

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
