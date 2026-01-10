"""Command-line interface for book indexer."""

import argparse
import json
import os
import sys
import yaml
from book_indexer.tagger import Tagger
from book_indexer.lexicon import Lexicon
from book_indexer.llm_assist import run_assist, apply_report, LLMError
from book_indexer.llm_judge import run_judge, apply_judgment


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

    tagger = Tagger(lexicon, placement=args.placement, command_set=args.command_set)

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

  # LLM-assisted lexicon suggestions
  book-indexer assist chapters/ --lexicon lexicon.yaml --report llm_report.json

  # LLM-assisted judgement of existing tags
  book-indexer judge chapters/ --report llm_judgment.json
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
    tag_parser.add_argument('--placement',
        choices=['after', 'inline'], default='after',
        help='Tag placement: after (default) or inline (replace text)')
    tag_parser.add_argument('--command-set',
        choices=['auto', 'typed', 'langsci'], default='auto',
        help='Index command set for inserted tags (default: auto)')
    tag_parser.add_argument('--strip', '-s', action='store_true',
        help='Strip existing tags before tagging')
    tag_parser.add_argument('--report', '-r',
        help='Save detailed JSON report to file')

    # assist command
    assist_parser = subparsers.add_parser('assist',
        help='LLM-assisted lexicon normalization and cross-references')
    assist_parser.add_argument('dir_path',
        help='Path to directory containing LaTeX files')
    assist_parser.add_argument('--lexicon', '-l', default='lexicon.yaml',
        help='Path to lexicon file (default: lexicon.yaml)')
    assist_parser.add_argument('--report', '-r', default='llm_report.json',
        help='Output JSON report (default: llm_report.json)')
    assist_parser.add_argument('--apply', action='store_true',
        help='Apply updates to lexicon in place')
    assist_parser.add_argument('--provider',
        choices=['openai', 'anthropic', 'command'], default='openai',
        help='LLM provider to use (default: openai)')
    assist_parser.add_argument('--model',
        help='Model name for the LLM provider (optional)')
    assist_parser.add_argument('--api-key',
        help='Override API key (otherwise use provider env var)')
    assist_parser.add_argument('--base-url',
        help='Override provider API base URL')
    assist_parser.add_argument('--llm-command',
        help='Shell command to run when provider=command')
    assist_parser.add_argument('--include-hidden', action='store_true',
        help='Include hidden directories when scanning for .tex files')
    assist_parser.add_argument('--chunk-size', type=int, default=20,
        help='Number of entries per LLM call (default: 20)')
    assist_parser.add_argument('--max-contexts', type=int, default=2,
        help='Max contexts per entry (default: 2)')
    assist_parser.add_argument('--context-window', type=int, default=80,
        help='Characters to include around each match (default: 80)')
    assist_parser.add_argument('--temperature', type=float, default=0.2,
        help='LLM temperature (default: 0.2)')
    assist_parser.add_argument('--max-tokens', type=int, default=1200,
        help='Max tokens per LLM response (default: 1200)')
    assist_parser.add_argument('--progress', action='store_true',
        help='Print progress updates during LLM assist')

    # judge command
    judge_parser = subparsers.add_parser('judge',
        help='LLM-assisted relevance check for existing index tags')
    judge_parser.add_argument('dir_path',
        help='Path to directory containing LaTeX files')
    judge_parser.add_argument('--report', '-r', default='llm_judgment.json',
        help='Output JSON report (default: llm_judgment.json)')
    judge_parser.add_argument('--provider',
        choices=['openai', 'anthropic', 'command'], default='openai',
        help='LLM provider to use (default: openai)')
    judge_parser.add_argument('--model',
        help='Model name for the LLM provider (optional)')
    judge_parser.add_argument('--api-key',
        help='Override API key (otherwise use provider env var)')
    judge_parser.add_argument('--base-url',
        help='Override provider API base URL')
    judge_parser.add_argument('--llm-command',
        help='Shell command to run when provider=command')
    judge_parser.add_argument('--include-hidden', action='store_true',
        help='Include hidden directories when scanning for .tex files')
    judge_parser.add_argument('--chunk-size', type=int, default=25,
        help='Number of tags per LLM call (default: 25)')
    judge_parser.add_argument('--context-window', type=int, default=160,
        help='Characters to include around each tag (default: 160)')
    judge_parser.add_argument('--temperature', type=float, default=0.2,
        help='LLM temperature (default: 0.2)')
    judge_parser.add_argument('--max-tokens', type=int, default=1200,
        help='Max tokens per LLM response (default: 1200)')
    judge_parser.add_argument('--progress', action='store_true',
        help='Print progress updates during LLM judgement')
    judge_parser.add_argument('--resume', action='store_true',
        help='Resume from an existing report by skipping decided tags')
    judge_parser.add_argument('--checkpoint', action='store_true',
        help='Write the judgment report after each batch')

    # apply-judgment command
    apply_judge_parser = subparsers.add_parser('apply-judgment',
        help='Apply an LLM judgement report by removing dropped tags')
    apply_judge_parser.add_argument('report_path',
        help='Path to LLM judgment JSON (e.g., llm_judgment.json)')

    # apply-report command
    apply_parser = subparsers.add_parser('apply-report',
        help='Apply an existing LLM report to a lexicon')
    apply_parser.add_argument('report_path',
        help='Path to LLM report JSON (e.g., llm_report.json)')
    apply_parser.add_argument('--lexicon', '-l', default='lexicon.yaml',
        help='Path to lexicon file (default: lexicon.yaml)')
    apply_parser.add_argument('--applied-report',
        help='Write applied diff JSON (default: <report>.applied.json)')

    args = parser.parse_args()

    if args.command == 'scan':
        cmd_scan(args)
    elif args.command == 'strip':
        cmd_strip(args)
    elif args.command == 'tag':
        cmd_tag(args)
    elif args.command == 'assist':
        try:
            run_assist(
                dir_path=args.dir_path,
                lexicon_path=args.lexicon,
                report_path=args.report,
                apply=args.apply,
                provider=args.provider,
                model=args.model,
                api_key=args.api_key,
                base_url=args.base_url,
                command=args.llm_command,
                include_hidden=args.include_hidden,
                chunk_size=args.chunk_size,
                max_contexts=args.max_contexts,
                context_window=args.context_window,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                progress=args.progress or args.verbose,
            )
            print(f"LLM report saved to {args.report}")
        except LLMError as exc:
            print(f"LLM assist failed: {exc}", file=sys.stderr)
            sys.exit(1)
    elif args.command == 'judge':
        try:
            run_judge(
                dir_path=args.dir_path,
                report_path=args.report,
                provider=args.provider,
                model=args.model,
                api_key=args.api_key,
                base_url=args.base_url,
                command=args.llm_command,
                include_hidden=args.include_hidden,
                chunk_size=args.chunk_size,
                context_window=args.context_window,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                progress=args.progress or args.verbose,
                resume=args.resume,
                checkpoint=args.checkpoint,
            )
            print(f"LLM judgment report saved to {args.report}")
        except LLMError as exc:
            print(f"LLM judgment failed: {exc}", file=sys.stderr)
            sys.exit(1)
    elif args.command == 'apply-report':
        try:
            applied_path = args.applied_report
            if not applied_path:
                root, ext = os.path.splitext(args.report_path)
                applied_path = f"{root}.applied.json" if ext else f"{args.report_path}.applied.json"
            count = apply_report(args.report_path, args.lexicon, applied_path)
            print(f"Applied {count} updates to {args.lexicon}")
            print(f"Applied report saved to {applied_path}")
        except LLMError as exc:
            print(f"Apply report failed: {exc}", file=sys.stderr)
            sys.exit(1)
    elif args.command == 'apply-judgment':
        try:
            removed = apply_judgment(args.report_path)
            print(f"Removed {removed} tags")
        except LLMError as exc:
            print(f"Apply judgment failed: {exc}", file=sys.stderr)
            sys.exit(1)


if __name__ == '__main__':
    main()
