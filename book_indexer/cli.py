"""Command-line interface for book indexer."""

import argparse
import json
import sys
import yaml
from book_indexer.tagger import Tagger
from book_indexer.lexicon import Lexicon


def cmd_scan(args):
    """Scan directory for existing tags and build lexicon."""
    tagger = Tagger()
    entries = tagger.extract_lexicon_from_directory(args.dir_path)

    # Save as YAML
    lexicon = Lexicon()
    for entry in entries:
        lexicon.add_entry(entry['term'], entry['type'])
    lexicon.save(args.output)

    print(f"Scanned {len(entries)} unique entries from {args.dir_path}")
    print(f"Lexicon saved to {args.output}")

    # Print summary by type
    by_type = {}
    for entry in entries:
        t = entry['type']
        by_type[t] = by_type.get(t, 0) + 1
    for t, count in sorted(by_type.items()):
        print(f"  {t}: {count}")


def cmd_strip(args):
    """Strip all index tags from LaTeX files."""
    tagger = Tagger()
    results = tagger.strip_tags(args.dir_path)

    total = sum(results.values())
    print(f"Stripped {total} tags from {len(results)} files")

    if args.verbose:
        for path, count in sorted(results.items()):
            print(f"  {path}: {count}")


def cmd_tag(args):
    """Apply index tags to LaTeX files."""
    lexicon = Lexicon(args.lexicon)
    if len(lexicon) == 0:
        print(f"Error: No entries in lexicon {args.lexicon}", file=sys.stderr)
        sys.exit(1)

    tagger = Tagger(lexicon)

    if args.strip:
        print("Stripping existing tags first...")
        strip_results = tagger.strip_tags(args.dir_path)
        stripped = sum(strip_results.values())
        print(f"  Stripped {stripped} tags from {len(strip_results)} files")

    print(f"Tagging in '{args.mode}' mode...")
    results = tagger.tag_directory(args.dir_path, mode=args.mode)

    total_actions = sum(len(actions) for actions in results.values())
    print(f"{'Suggested' if args.mode == 'guide' else 'Applied'} {total_actions} tags in {len(results)} files")

    # Output detailed report
    if args.report:
        report = []
        for path, actions in results.items():
            for action in actions:
                report.append({
                    'file': path,
                    'line': action.get('line'),
                    'term': action.get('term'),
                    'canonical': action.get('canonical'),
                    'type': action.get('type'),
                    'action': action.get('action'),
                })
        with open(args.report, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
        print(f"Report saved to {args.report}")

    if args.verbose:
        for path, actions in sorted(results.items()):
            print(f"\n{path}:")
            for action in actions[:10]:  # Limit output
                print(f"  L{action.get('line', '?')}: {action.get('term')} ({action.get('type')})")
            if len(actions) > 10:
                print(f"  ... and {len(actions) - 10} more")


def main():
    parser = argparse.ArgumentParser(
        description="Book Indexer - LaTeX index tag management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan existing tags to create a lexicon
  book-indexer scan chapters/ --output lexicon.yaml

  # Preview what would be tagged (guide mode)
  book-indexer tag chapters/ --lexicon lexicon.yaml --mode guide

  # Apply tags automatically
  book-indexer tag chapters/ --lexicon lexicon.yaml --mode auto

  # Strip and re-tag
  book-indexer tag chapters/ --lexicon lexicon.yaml --mode auto --strip
"""
    )
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Verbose output')

    subparsers = parser.add_subparsers(dest='command', required=True,
                                       help='Available commands')

    # scan command
    scan_parser = subparsers.add_parser('scan',
        help='Scan for existing tags and generate lexicon')
    scan_parser.add_argument('dir_path',
        help='Path to directory containing LaTeX files')
    scan_parser.add_argument('--output', '-o', default='lexicon.yaml',
        help='Output lexicon file (default: lexicon.yaml)')

    # strip command
    strip_parser = subparsers.add_parser('strip',
        help='Remove all index tags from LaTeX files')
    strip_parser.add_argument('dir_path',
        help='Path to directory containing LaTeX files')

    # tag command
    tag_parser = subparsers.add_parser('tag',
        help='Insert index tags into LaTeX files')
    tag_parser.add_argument('dir_path',
        help='Path to directory containing LaTeX files')
    tag_parser.add_argument('--mode', '-m',
        choices=['guide', 'assist', 'auto'], default='assist',
        help='Tagging mode: guide (preview), assist (safe), auto (full)')
    tag_parser.add_argument('--lexicon', '-l', default='lexicon.yaml',
        help='Path to lexicon file (default: lexicon.yaml)')
    tag_parser.add_argument('--strip', '-s', action='store_true',
        help='Strip existing tags before tagging')
    tag_parser.add_argument('--report', '-r',
        help='Save detailed JSON report to file')

    args = parser.parse_args()

    if args.command == 'scan':
        cmd_scan(args)
    elif args.command == 'strip':
        cmd_strip(args)
    elif args.command == 'tag':
        cmd_tag(args)


if __name__ == '__main__':
    main()
