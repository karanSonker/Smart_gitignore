"""
cli.py
------
The actual smart-gitignore command.

Flow:
  1. Walk the target directory (skipping .git) and collect:
       - every file extension present
       - every directory name present
       - every exact filename present
  2. Compare against DEFAULT_RULES (and MEDIA_RULES if --include-media).
  3. Work out which patterns are genuinely new (not already in .gitignore).
  4. If any matching files are ALREADY tracked by git, warn the user —
     adding a pattern to .gitignore does NOT untrack files that are
     already committed. This is the #1 confusion beginners have.
  5. Show a preview. Write only on confirmation (or --yes).
"""

import argparse
import os
import subprocess
import sys
from datetime import date
from fnmatch import fnmatch
from pathlib import Path

from .rules import DEFAULT_RULES, MEDIA_RULES


def warn_media_skipped(extensions, dirnames, filenames):
    """
    If media files exist in the project but --include-media wasn't passed,
    surface that immediately as a warning — not buried in the README.
    We deliberately do NOT ignore media by default because many projects
    intentionally commit images/icons/docs, and silently suggesting to
    ignore them could make someone lose tracked assets.
    """
    matched = match_rules(MEDIA_RULES, extensions, dirnames, filenames)
    if not matched:
        return
    total_examples = []
    for rule in matched:
        total_examples.append(rule.name.replace(" (opt-in)", ""))
    print(f"{WARN_PREFIX} found media files ({', '.join(total_examples)}) but skipping them by default.")
    print("  Media is often committed on purpose (docs, icons, website assets), so this tool")
    print("  will never silently suggest ignoring it. Re-run with --include-media if you")
    print("  actually want these ignored.\n")

HEADER = "# --- Added by smart-gitignore on {date} ---"

WARN_PREFIX = "⚠ WARNING:"


def scan_directory(root: Path):
    """Walk the directory tree and collect extensions, dirnames, filenames."""
    extensions = set()
    dirnames = set()
    filenames = set()

    for current_root, dirs, files in os.walk(root):
        # never descend into .git
        if ".git" in dirs:
            dirs.remove(".git")

        for d in dirs:
            dirnames.add(d)

        for f in files:
            filenames.add(f)
            ext = Path(f).suffix
            if ext:
                extensions.add(ext)

    return extensions, dirnames, filenames


def match_rules(rules, extensions, dirnames, filenames):
    """Return the list of Rule objects that apply to what's on disk."""
    matched = []
    for rule in rules:
        hit = False
        if rule.match_extensions and extensions.intersection(rule.match_extensions):
            hit = True
        if rule.match_dirnames and dirnames.intersection(rule.match_dirnames):
            hit = True
        if rule.match_filenames and filenames.intersection(rule.match_filenames):
            hit = True
        if hit:
            matched.append(rule)
    return matched


def load_existing_gitignore(path: Path):
    if not path.exists():
        return []
    return [line.rstrip("\n") for line in path.read_text(encoding="utf-8").splitlines()]


def compute_new_patterns(matched_rules, existing_lines):
    existing_set = set(line.strip() for line in existing_lines)
    new_by_category = {}
    for rule in matched_rules:
        fresh = [p for p in rule.patterns if p not in existing_set]
        if fresh:
            new_by_category[rule.name] = fresh
    return new_by_category


def is_git_repo(root: Path) -> bool:
    return (root / ".git").exists()


def get_tracked_files(root: Path):
    """Return the list of files git already tracks, or [] if not a repo / git missing."""
    if not is_git_repo(root):
        return []
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.splitlines()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


def find_already_tracked_matches(tracked_files, new_by_category):
    """Check whether any already-tracked file would match one of our new patterns."""
    all_patterns = [p for patterns in new_by_category.values() for p in patterns]
    warnings = []
    for f in tracked_files:
        basename = os.path.basename(f)
        for pattern in all_patterns:
            # directory-style pattern e.g. "venv/" -> check path prefix
            if pattern.endswith("/"):
                dirname = pattern.rstrip("/")
                if f == dirname or f.startswith(dirname + "/") or ("/" + dirname + "/") in ("/" + f):
                    warnings.append((f, pattern))
                    break
            else:
                if fnmatch(basename, pattern) or fnmatch(f, pattern):
                    warnings.append((f, pattern))
                    break
    return warnings


def untrack_files(root: Path, warnings):
    """
    Actually run `git rm --cached` for each already-tracked file that matches
    a new .gitignore pattern. Only ever called after the user explicitly
    typed 'y' — this tool never runs git commands without that confirmation.
    Returns (succeeded, failed) lists of filenames.
    """
    succeeded, failed = [], []
    for f, _pattern in warnings:
        try:
            subprocess.run(
                ["git", "-C", str(root), "rm", "--cached", "--quiet", f],
                check=True, capture_output=True, text=True,
            )
            succeeded.append(f)
        except subprocess.CalledProcessError as e:
            failed.append((f, e.stderr.strip() or str(e)))
    return succeeded, failed


def build_output_block(new_by_category):
    lines = [HEADER.format(date=date.today().isoformat())]
    for category, patterns in new_by_category.items():
        lines.append(f"\n# {category}")
        lines.extend(patterns)
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="smart-gitignore",
        description="Scan a project and auto-add sensible .gitignore rules "
                     "(logs, env files, venvs, node_modules, caches, etc.)."
    )
    parser.add_argument("path", nargs="?", default=".", help="Project directory (default: current directory)")
    parser.add_argument("--include-media", action="store_true",
                         help="Also detect and ignore images/video/audio files (off by default — "
                              "many projects intentionally commit media assets).")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change, write nothing.")
    parser.add_argument("-y", "--yes", action="store_true", help="Write .gitignore changes without prompting.")
    parser.add_argument("--auto-untrack", action="store_true",
                         help="Also run 'git rm --cached' on already-tracked matches without "
                              "prompting. Off by default — untracking is asked for separately "
                              "from writing .gitignore, since it touches your git index.")
    args = parser.parse_args(argv)

    root = Path(args.path).resolve()
    if not root.exists():
        print(f"Error: path '{root}' does not exist.")
        sys.exit(1)

    rules = list(DEFAULT_RULES)
    if args.include_media:
        rules += MEDIA_RULES

    print(f"Scanning {root} ...")
    extensions, dirnames, filenames = scan_directory(root)
    matched_rules = match_rules(rules, extensions, dirnames, filenames)

    # Design decision #1, surfaced live: warn about skipped media instead of
    # just documenting it in the README.
    if not args.include_media:
        warn_media_skipped(extensions, dirnames, filenames)

    gitignore_path = root / ".gitignore"
    existing_lines = load_existing_gitignore(gitignore_path)
    new_by_category = compute_new_patterns(matched_rules, existing_lines)

    if not new_by_category:
        print("Nothing new to add — your .gitignore already covers what's here, "
              "or no risky file types were found.")
        return

    print("\nDetected files that should probably be ignored:\n")
    for category, patterns in new_by_category.items():
        print(f"  [{category}]")
        for p in patterns:
            print(f"    {p}")
    print()

    # Design decision #3, surfaced live: files already committed need manual
    # untracking — a .gitignore rule alone changes nothing for them.
    tracked_files = get_tracked_files(root)
    already_tracked_hit = False
    tracked_warnings = []
    if tracked_files:
        tracked_warnings = find_already_tracked_matches(tracked_files, new_by_category)
        if tracked_warnings:
            already_tracked_hit = True
            print(f"{WARN_PREFIX} these files are already tracked by git.")
            print("  Adding a pattern to .gitignore will NOT remove them from the repo")
            print("  or from your git history. The fix is to untrack them:\n")
            for f, pattern in tracked_warnings[:20]:
                print(f"    git rm --cached \"{f}\"    # matched pattern: {pattern}")
            if len(tracked_warnings) > 20:
                print(f"    ... and {len(tracked_warnings) - 20} more")
            print("\n  (If any of these ever contained secrets, git rm --cached is not")
            print("  enough — they're still in old commits. Use git filter-repo or the")
            print("  BFG Repo-Cleaner, and rotate the leaked credentials regardless.)\n")

    if args.dry_run:
        print("(dry run — no files were changed)")
        return

    # Design decision #2, surfaced live: this tool never runs a git command
    # or touches files beyond what you explicitly confirm. Writing .gitignore
    # and untracking already-committed files are two separate actions with
    # two separate y/n prompts below — saying yes to one never triggers the other.
    print(f"{WARN_PREFIX} this tool only changes what you explicitly confirm.")
    print("  Writing .gitignore and untracking files are asked about separately.\n")

    wrote_gitignore = False
    if not args.yes:
        answer = input(f"Append these rules to {gitignore_path}? [y/N] ").strip().lower()
        if answer == "y":
            wrote_gitignore = True
        else:
            print("Cancelled — .gitignore was not changed.")
    else:
        wrote_gitignore = True

    if wrote_gitignore:
        block = build_output_block(new_by_category)
        with open(gitignore_path, "a", encoding="utf-8") as f:
            if existing_lines:
                f.write("\n")
            f.write(block)
        print(f"Done. Updated {gitignore_path}")

    # Separate, explicit y/n for the destructive action: untracking files
    # that are already committed. Never bundled with the prompt above unless
    # the user opted in via --auto-untrack.
    if already_tracked_hit:
        print()
        if args.auto_untrack:
            run_untrack = True
        else:
            reply = input(
                f"Run 'git rm --cached' on the {len(tracked_warnings)} already-tracked "
                f"file(s) shown above now? [y/N] "
            ).strip().lower()
            run_untrack = (reply == "y")

        if run_untrack:
            succeeded, failed = untrack_files(root, tracked_warnings)
            if succeeded:
                print(f"\nUntracked {len(succeeded)} file(s):")
                for f in succeeded:
                    print(f"    git rm --cached \"{f}\"  done")
                print("\n  These files still exist on disk — only removed from git's index.")
                print("  Commit this to finish: git commit -m \"Stop tracking ignored files\"")
            if failed:
                print(f"\nFailed to untrack {len(failed)} file(s):")
                for f, err in failed:
                    print(f"    {f}: {err}")
        else:
            print("Skipped — no files were untracked. You can run the commands above manually anytime.")


if __name__ == "__main__":
    main()
