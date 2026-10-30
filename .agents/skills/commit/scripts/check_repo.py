#!/usr/bin/env python3
"""Pre-commit checks for Rillmark: links, verbatim prompt, secrets, public hygiene.

Usage:
    python3 .agents/skills/commit/scripts/check_repo.py            # working tree
    python3 .agents/skills/commit/scripts/check_repo.py --staged   # exact index snapshot

`--staged` reads every file from the git index (`git show :path`), so the result
describes exactly what would be committed, independent of unstaged edits.
Exits 1 on any failure. Standard library only.
"""

from __future__ import annotations

import argparse
import posixpath
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

# Canonical OptiBot system prompt, verbatim from the assignment.
SYSTEM_PROMPT = (
    "You are OptiBot, the customer-support bot for OptiSigns.com.\n"
    "• Tone: helpful, factual, concise.\n"
    "• Only answer using the uploaded docs.\n"
    "• Max 5 bullet points; else link to the doc.\n"
    '• Cite up to 3 "Article URL:" lines per reply.'
)
PROMPT_DOC = "docs/00-requirements.md"
PROMPT_SECTION = re.compile(r"^## 4\. System prompt.*?$(.*?)(?=^## |\Z)", re.M | re.S)
FENCE = re.compile(r"^```[^\n]*\n(.*?)^```\s*$", re.M | re.S)

SECRET_PATTERNS = [
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]
HYGIENE_PATTERN = re.compile(
    r"\bTASK-\d+\b|(?<![\w/])#\d{4}\b|\b(?:GPT|Claude|Codex|ChatGPT|Mission Control)\b|\bPi [A-F]\b"
)
PUBLIC_PREFIXES = ("README.md", "docs/")
SKIP_PARTS = {".git", "research", ".venv", "node_modules", "__pycache__", ".serena"}

INLINE_LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
REF_DEF = re.compile(r"^\s{0,3}\[([^\]]+)\]:\s*(\S+)", re.M)
REF_USE = re.compile(r"\[[^\]]+\]\[([^\]]*)\]")


class Snapshot:
    """A set of repository files and a reader for their text (index or working tree)."""

    def __init__(self, root: Path, staged: bool) -> None:
        self.root = root
        self.staged = staged
        self.paths = self._list()

    def _git(self, *args: str) -> bytes:
        # Fixed `git` argv list, no shell: trusted input by construction.
        result = subprocess.run(  # noqa: S603
            ["git", *args],  # noqa: S607
            cwd=self.root,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise SystemExit(f"FAIL git {' '.join(args)}: {result.stderr.decode().strip()}")
        return result.stdout

    def _list(self) -> set[str]:
        if self.staged:
            return {p for p in self._git("ls-files", "-z", "--cached").decode().split("\0") if p}
        found: set[str] = set()
        for path in self.root.rglob("*"):
            rel = path.relative_to(self.root)
            if path.is_file() and not SKIP_PARTS.intersection(rel.parts):
                found.add(rel.as_posix())
        return found

    def read(self, rel: str) -> str | None:
        """Return the file text, or None if it is binary or not in the snapshot."""
        if rel not in self.paths:
            return None
        raw = self._git("show", f":{rel}") if self.staged else (self.root / rel).read_bytes()
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return None

    def is_dir(self, rel: str) -> bool:
        prefix = rel.rstrip("/") + "/"
        return any(p.startswith(prefix) for p in self.paths)


def strip_code(text: str) -> str:
    return re.sub(r"`[^`\n]*`", "", re.sub(r"```.*?```", "", text, flags=re.S))


def slug(heading: str) -> str:
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def make_anchor_lookup(snap: Snapshot) -> Callable[[str], set[str]]:
    cache: dict[str, set[str]] = {}

    def anchors(rel: str) -> set[str]:
        if rel not in cache:
            text = re.sub(r"```.*?```", "", snap.read(rel) or "", flags=re.S)
            cache[rel] = {slug(h) for h in re.findall(r"^#{1,6}\s+(.*)$", text, flags=re.M)}
        return cache[rel]

    return anchors


def link_targets(text: str, rel: str) -> tuple[list[str], list[str]]:
    """Return (targets, errors) for inline and reference-style links in a Markdown file."""
    body = strip_code(text)
    targets = INLINE_LINK.findall(body)
    definitions = {label.lower(): target for label, target in REF_DEF.findall(body)}
    targets.extend(definitions.values())
    errors = [
        f"{rel}: undefined reference link [{label}]"
        for label in REF_USE.findall(body)
        if label and label.lower() not in definitions
    ]
    return targets, errors


def check_links(snap: Snapshot) -> list[str]:
    anchors = make_anchor_lookup(snap)
    errors: list[str] = []
    for rel in sorted(p for p in snap.paths if p.endswith(".md")):
        text = snap.read(rel)
        if text is None:
            continue
        targets, ref_errors = link_targets(text, rel)
        errors.extend(ref_errors)
        for link in targets:
            if re.match(r"[a-z][a-z0-9+.-]*:", link) or link.startswith("<"):
                continue
            target_rel, _, frag = link.partition("#")
            target = (
                posixpath.normpath(posixpath.join(posixpath.dirname(rel), target_rel))
                if target_rel
                else rel
            )
            if target not in snap.paths and not snap.is_dir(target):
                errors.append(f"{rel}: missing link target {link}")
            elif frag and target.endswith(".md") and frag not in anchors(target):
                errors.append(f"{rel}: missing anchor {link}")
    return errors


def check_prompt(snap: Snapshot) -> list[str]:
    text = snap.read(PROMPT_DOC)
    if text is None:
        return [f"{PROMPT_DOC}: missing (system prompt cannot be verified)"]
    section = PROMPT_SECTION.search(text)
    if section is None:
        return [f"{PROMPT_DOC}: section '## 4. System prompt' not found"]
    blocks = FENCE.findall(section.group(1))
    if len(blocks) != 1:
        return [
            f"{PROMPT_DOC}: expected exactly one fenced prompt block in §4, found {len(blocks)}"
        ]
    if blocks[0].replace("\r\n", "\n").rstrip("\n") != SYSTEM_PROMPT:
        return [f"{PROMPT_DOC}: §4 prompt block is not the exact canonical system prompt"]
    return []


def check_text(snap: Snapshot) -> list[str]:
    errors: list[str] = []
    for rel in sorted(snap.paths):
        text = snap.read(rel)
        if text is None:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"{rel}: secret-like string ({pattern.pattern[:24]}...)")
        if rel.startswith(PUBLIC_PREFIXES):
            for number, line in enumerate(text.splitlines(), 1):
                match = HYGIENE_PATTERN.search(line)
                if match:
                    errors.append(f"{rel}:{number}: public-hygiene marker '{match.group()}'")
    return errors


def repo_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    return Path(result.stdout.strip()) if result.returncode == 0 else Path.cwd()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--staged", action="store_true", help="check the exact git index snapshot")
    args = parser.parse_args(argv)
    snap = Snapshot(repo_root(), staged=args.staged)
    errors = check_links(snap) + check_prompt(snap) + check_text(snap)
    for error in errors:
        print("FAIL", error)
    markdown = sum(p.endswith(".md") for p in snap.paths)
    scope = "index" if args.staged else "working tree"
    verdict = "FAIL" if errors else "PASS"
    print(f"checked {len(snap.paths)} files ({markdown} markdown) in {scope}: {verdict}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
