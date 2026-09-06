"""
rules.py
--------
Defines the categories smart-gitignore knows how to detect, and the
patterns it will write into .gitignore for each one.

Design note:
Every category is "safe by default" — i.e. things that are almost NEVER
meant to be committed (logs, envs, venvs, dependency folders, caches).

Media files (images/video/audio) are kept OUT of the default set and only
included when the user explicitly passes --include-media, because many
projects legitimately commit images (docs, website assets, icons) and we
never want to silently suggest ignoring something that belongs in the repo.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class Rule:
    name: str                 # Human readable category name
    patterns: List[str]       # Patterns to add to .gitignore
    match_extensions: List[str] = None   # File extensions that trigger this rule
    match_dirnames: List[str] = None     # Directory names that trigger this rule
    match_filenames: List[str] = None    # Exact filenames that trigger this rule


DEFAULT_RULES: List[Rule] = [
    Rule(
        name="Logs",
        patterns=["*.log", "*.log.*", "logs/", "npm-debug.log*", "yarn-debug.log*", "yarn-error.log*"],
        match_extensions=[".log"],
        match_dirnames=["logs"],
    ),
    Rule(
        name="Environment / Secrets",
        patterns=[".env", ".env.local", ".env.*.local", "*.env"],
        match_filenames=[".env"],
        match_extensions=[".env"],
    ),
    Rule(
        name="Python Virtual Environments",
        patterns=["venv/", ".venv/", "env/", "ENV/", "virtualenv/"],
        match_dirnames=["venv", ".venv", "env", "ENV", "virtualenv"],
    ),
    Rule(
        name="Python Cache",
        patterns=["__pycache__/", "*.pyc", "*.pyo", "*.pyd", ".pytest_cache/", ".mypy_cache/"],
        match_extensions=[".pyc", ".pyo", ".pyd"],
        match_dirnames=["__pycache__", ".pytest_cache", ".mypy_cache"],
    ),
    Rule(
        name="Node.js Dependencies",
        patterns=["node_modules/", ".npm/", ".yarn/"],
        match_dirnames=["node_modules"],
    ),
    Rule(
        name="Build Artifacts",
        patterns=["dist/", "build/", "*.egg-info/", "target/", "out/"],
        match_dirnames=["dist", "build", "target", "out"],
    ),
    Rule(
        name="OS Junk Files",
        patterns=[".DS_Store", "Thumbs.db", "desktop.ini"],
        match_filenames=[".DS_Store", "Thumbs.db", "desktop.ini"],
    ),
    Rule(
        name="Editor / IDE",
        patterns=[".vscode/", ".idea/", "*.sublime-workspace", "*.swp"],
        match_dirnames=[".vscode", ".idea"],
        match_extensions=[".swp"],
    ),
]

# Opt-in only — see design note above.
MEDIA_RULES: List[Rule] = [
    Rule(
        name="Media - Images (opt-in)",
        patterns=["*.png", "*.jpg", "*.jpeg", "*.gif", "*.bmp", "*.webp"],
        match_extensions=[".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"],
    ),
    Rule(
        name="Media - Video (opt-in)",
        patterns=["*.mp4", "*.mov", "*.avi", "*.mkv", "*.wmv"],
        match_extensions=[".mp4", ".mov", ".avi", ".mkv", ".wmv"],
    ),
    Rule(
        name="Media - Audio (opt-in)",
        patterns=["*.mp3", "*.wav", "*.flac", "*.aac"],
        match_extensions=[".mp3", ".wav", ".flac", ".aac"],
    ),
]
