"""
test_cli.py
-----------
Automated tests for smart-gitignore. Run with:

    pip install -e .[dev]
    pytest -v

Covers:
  - directory scanning (extensions/dirnames/filenames detection)
  - rule matching
  - computing only-new patterns (no duplicate lines)
  - detecting already-tracked files that match new patterns
  - full end-to-end run against a real temporary git repo
"""

import subprocess
from pathlib import Path

import pytest

from smart_gitignore.cli import (
    scan_directory,
    match_rules,
    compute_new_patterns,
    find_already_tracked_matches,
    main,
)
from smart_gitignore.rules import DEFAULT_RULES, MEDIA_RULES


def make_git_repo(path: Path):
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)


def git_commit_all(path: Path, message="commit"):
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=path, check=True)


def git_ls_files(path: Path):
    result = subprocess.run(
        ["git", "ls-files"], cwd=path, capture_output=True, text=True, check=True
    )
    return result.stdout.splitlines()


# ---------- unit tests ----------

def test_scan_directory_detects_extensions_and_dirs(tmp_path):
    (tmp_path / "app.log").touch()
    (tmp_path / "main.py").touch()
    (tmp_path / "venv").mkdir()
    (tmp_path / ".env").touch()

    extensions, dirnames, filenames = scan_directory(tmp_path)

    assert ".log" in extensions
    assert ".py" in extensions
    assert "venv" in dirnames
    assert ".env" in filenames


def test_scan_directory_skips_git_folder(tmp_path):
    make_git_repo(tmp_path)
    # .git contains lots of files/extensions internally; none should leak in
    extensions, dirnames, filenames = scan_directory(tmp_path)
    assert ".git" not in dirnames


def test_match_rules_logs(tmp_path):
    (tmp_path / "debug.log").touch()
    extensions, dirnames, filenames = scan_directory(tmp_path)
    matched = match_rules(DEFAULT_RULES, extensions, dirnames, filenames)
    names = [r.name for r in matched]
    assert "Logs" in names


def test_match_rules_media_off_by_default(tmp_path):
    (tmp_path / "logo.png").touch()
    extensions, dirnames, filenames = scan_directory(tmp_path)
    matched = match_rules(DEFAULT_RULES, extensions, dirnames, filenames)
    names = [r.name for r in matched]
    assert not any("Media" in n for n in names)


def test_match_rules_media_when_included(tmp_path):
    (tmp_path / "logo.png").touch()
    extensions, dirnames, filenames = scan_directory(tmp_path)
    all_rules = DEFAULT_RULES + MEDIA_RULES
    matched = match_rules(all_rules, extensions, dirnames, filenames)
    names = [r.name for r in matched]
    assert any("Media" in n for n in names)


def test_compute_new_patterns_skips_existing(tmp_path):
    (tmp_path / "app.log").touch()
    extensions, dirnames, filenames = scan_directory(tmp_path)
    matched = match_rules(DEFAULT_RULES, extensions, dirnames, filenames)
    existing_lines = ["*.log"]  # already present
    new = compute_new_patterns(matched, existing_lines)
    logs_patterns = new.get("Logs", [])
    assert "*.log" not in logs_patterns   # shouldn't duplicate
    assert "logs/" in logs_patterns       # but other log patterns still offered


def test_find_already_tracked_matches(tmp_path):
    make_git_repo(tmp_path)
    (tmp_path / "app.log").touch()
    (tmp_path / "main.py").touch()
    git_commit_all(tmp_path)

    new_by_category = {"Logs": ["*.log", "logs/"]}
    tracked = git_ls_files(tmp_path)
    warnings = find_already_tracked_matches(tracked, new_by_category)

    matched_files = [f for f, _pattern in warnings]
    assert "app.log" in matched_files
    assert "main.py" not in matched_files


def test_find_already_tracked_matches_empty_when_nothing_tracked_matches(tmp_path):
    make_git_repo(tmp_path)
    (tmp_path / "main.py").touch()
    git_commit_all(tmp_path)

    new_by_category = {"Logs": ["*.log", "logs/"]}
    tracked = git_ls_files(tmp_path)
    warnings = find_already_tracked_matches(tracked, new_by_category)
    assert warnings == []


# ---------- end-to-end tests (run the real CLI) ----------

def test_end_to_end_dry_run_does_not_write(tmp_path, capsys):
    (tmp_path / "app.log").touch()
    main([str(tmp_path), "--dry-run"])
    captured = capsys.readouterr()
    assert "Logs" in captured.out
    assert not (tmp_path / ".gitignore").exists()


def test_end_to_end_yes_writes_gitignore(tmp_path):
    (tmp_path / "app.log").touch()
    main([str(tmp_path), "--yes"])
    gitignore = tmp_path / ".gitignore"
    assert gitignore.exists()
    content = gitignore.read_text()
    assert "*.log" in content


def test_end_to_end_no_new_patterns_when_nothing_risky(tmp_path, capsys):
    (tmp_path / "README.md").touch()
    main([str(tmp_path), "--yes"])
    captured = capsys.readouterr()
    assert "Nothing new to add" in captured.out
    assert not (tmp_path / ".gitignore").exists()


def test_end_to_end_auto_untrack_removes_from_git_index(tmp_path):
    make_git_repo(tmp_path)
    (tmp_path / "app.log").touch()
    (tmp_path / "main.py").touch()
    git_commit_all(tmp_path)

    main([str(tmp_path), "--yes", "--auto-untrack"])

    tracked_after = git_ls_files(tmp_path)
    assert "app.log" not in tracked_after
    assert "main.py" in tracked_after
    # file must still exist on disk — untracking is not deleting
    assert (tmp_path / "app.log").exists()


def test_end_to_end_media_skipped_unless_flag(tmp_path):
    (tmp_path / "logo.png").touch()
    main([str(tmp_path), "--yes"])
    gitignore = tmp_path / ".gitignore"
    # no risky non-media files -> nothing written at all
    assert not gitignore.exists()


def test_end_to_end_media_included_with_flag(tmp_path):
    (tmp_path / "logo.png").touch()
    main([str(tmp_path), "--yes", "--include-media"])
    gitignore = tmp_path / ".gitignore"
    assert gitignore.exists()
    assert "*.png" in gitignore.read_text()


def test_running_twice_does_not_duplicate_rules(tmp_path):
    (tmp_path / "app.log").touch()
    main([str(tmp_path), "--yes"])
    first_content = (tmp_path / ".gitignore").read_text()

    main([str(tmp_path), "--yes"])
    second_content = (tmp_path / ".gitignore").read_text()

    assert first_content == second_content  # nothing new to append second time
