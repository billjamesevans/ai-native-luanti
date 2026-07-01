#!/usr/bin/env python3
"""Fail a push when high-confidence credentials are present.

The scanner intentionally reports only file, line, pattern, and classification.
It never prints the matched secret value.
"""

from __future__ import annotations

import argparse
import math
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ZERO_SHA = "0" * 40
SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "build",
    "cmake-build-debug",
    "cmake-build-minsizerel",
    "cmake-build-release",
    "cmake-build-relwithdebinfo",
    "node_modules",
}
SKIP_EXTS = {
    ".7z",
    ".a",
    ".apk",
    ".bin",
    ".bmp",
    ".bz2",
    ".dmp",
    ".dylib",
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".mp3",
    ".mp4",
    ".o",
    ".pdf",
    ".png",
    ".so",
    ".sqlite",
    ".tgz",
    ".wasm",
    ".webp",
    ".zip",
}
PLACEHOLDER_MARKERS = (
    "changeme",
    "dummy",
    "example",
    "fake",
    "fixture",
    "not-a-real",
    "placeholder",
    "redacted",
    "sample",
    "test",
    "your_",
    "your-",
)


@dataclass(frozen=True)
class Pattern:
    name: str
    regex: re.Pattern[str]
    group: int = 0


@dataclass(frozen=True)
class Finding:
    source: str
    path: str
    line: int
    pattern: str
    classification: str


PATTERNS = (
    Pattern(
        "openai_api_key",
        re.compile(r"(?<![A-Za-z0-9])sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}"),
    ),
    Pattern("github_token", re.compile(r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9_]{20,}")),
    Pattern("aws_access_key", re.compile(r"(?<![A-Z0-9])AKIA[0-9A-Z]{16}(?![A-Z0-9])")),
    Pattern("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    Pattern(
        "secret_env_assignment",
        re.compile(
            r"(?i)\b(OPENAI_API_KEY|GITHUB_TOKEN|ANTHROPIC_API_KEY|AWS_SECRET_ACCESS_KEY)"
            r"\b\s*[:=]\s*[\"']?([^\"'\s#]+)"
        ),
        group=2,
    ),
)


def run_git(args: list[str], *, input_text: str | None = None) -> str:
    completed = subprocess.run(
        ["git", *args],
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed.stdout


def token_entropy(value: str) -> float:
    if not value:
        return 0.0
    return -sum((value.count(char) / len(value)) * math.log2(value.count(char) / len(value)) for char in set(value))


def classify(value: str) -> str:
    lower = value.lower()
    if any(marker in lower for marker in PLACEHOLDER_MARKERS):
        return "placeholder"
    if re.search(r"(.)\1{8,}", value) or "0000000000" in value:
        return "low_entropy_placeholder"
    if token_entropy(value) < 3.5:
        return "low_entropy_placeholder"
    return "high_confidence_secret"


def should_scan_path(path: str) -> bool:
    parts = Path(path).parts
    if any(part in SKIP_DIRS for part in parts):
        return False
    if Path(path).suffix.lower() in SKIP_EXTS:
        return False
    return True


def scan_text(text: str, *, source: str, path: str) -> list[Finding]:
    findings: list[Finding] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        for pattern in PATTERNS:
            for match in pattern.regex.finditer(line):
                value = match.group(pattern.group)
                classification = classify(value)
                if classification == "high_confidence_secret":
                    findings.append(Finding(source, path, line_no, pattern.name, classification))
    return findings


def scan_worktree_paths(paths: Iterable[str], *, source: str, repo: Path) -> list[Finding]:
    findings: list[Finding] = []
    for rel_path in paths:
        if not should_scan_path(rel_path):
            continue
        path = repo / rel_path
        if not path.is_file():
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        findings.extend(scan_text(text, source=source, path=rel_path))
    return findings


def current_findings(repo: Path, *, tracked: bool, untracked: bool) -> list[Finding]:
    findings: list[Finding] = []
    if tracked:
        files = run_git(["ls-files"]).splitlines()
        findings.extend(scan_worktree_paths(files, source="tracked", repo=repo))
    if untracked:
        files = run_git(["ls-files", "--others", "--exclude-standard"]).splitlines()
        findings.extend(scan_worktree_paths(files, source="untracked", repo=repo))
    return findings


def changed_files_for_commit(commit: str) -> list[str]:
    return run_git(["diff-tree", "--root", "--no-commit-id", "--name-only", "-r", commit]).splitlines()


def show_commit_file(commit: str, path: str) -> str | None:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.decode("utf-8", errors="ignore")


def all_history_blob_paths() -> dict[str, str]:
    blobs: dict[str, str] = {}
    for line in run_git(["rev-list", "--objects", "--all"]).splitlines():
        fields = line.split(" ", 1)
        if len(fields) != 2:
            continue
        blob, path = fields
        if blob in blobs or not should_scan_path(path):
            continue
        blobs[blob] = path
    return blobs


def show_blob(blob: str) -> str | None:
    completed = subprocess.run(
        ["git", "cat-file", "-p", blob],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.decode("utf-8", errors="ignore")


def scan_commits(commits: Iterable[str]) -> list[Finding]:
    findings: list[Finding] = []
    for commit in commits:
        short_commit = commit[:12]
        for path in changed_files_for_commit(commit):
            if not should_scan_path(path):
                continue
            text = show_commit_file(commit, path)
            if text is None:
                continue
            findings.extend(scan_text(text, source=f"commit:{short_commit}", path=path))
    return findings


def scan_all_history_blobs() -> list[Finding]:
    findings: list[Finding] = []
    blob_paths = all_history_blob_paths()
    if not blob_paths:
        return findings

    object_list_path = ""
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as object_list:
            object_list_path = object_list.name
            for blob in blob_paths:
                object_list.write(f"{blob}\n")

        with open(object_list_path, "rb") as object_list:
            process = subprocess.Popen(
                ["git", "cat-file", "--batch"],
                stdin=object_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if process.stdout is None or process.stderr is None:
                raise RuntimeError("git cat-file --batch did not expose output streams")

            for blob, path in blob_paths.items():
                header_bytes = process.stdout.readline()
                if not header_bytes:
                    break
                header = header_bytes.decode("ascii", errors="replace").strip()
                fields = header.split()
                if len(fields) < 3 or fields[0] != blob:
                    continue
                try:
                    size = int(fields[2])
                except ValueError:
                    continue
                data = process.stdout.read(size)
                process.stdout.read(1)
                if fields[1] != "blob":
                    continue
                text = data.decode("utf-8", errors="ignore")
                findings.extend(scan_text(text, source=f"blob:{blob[:12]}", path=path))

            stderr = process.stderr.read().decode("utf-8", errors="ignore")
            return_code = process.wait()
            if return_code != 0:
                raise RuntimeError(stderr.strip() or "git cat-file --batch failed")
    finally:
        if object_list_path:
            try:
                os.unlink(object_list_path)
            except OSError:
                pass

    return findings


def pre_push_commits(pre_push_stdin: str) -> list[str]:
    commits: set[str] = set()
    for raw_line in pre_push_stdin.splitlines():
        fields = raw_line.split()
        if len(fields) != 4:
            continue
        _local_ref, local_sha, _remote_ref, remote_sha = fields
        if local_sha == ZERO_SHA:
            continue
        if remote_sha == ZERO_SHA:
            revs = run_git(["rev-list", local_sha, "--not", "--remotes"]).splitlines()
        else:
            revs = run_git(["rev-list", f"{remote_sha}..{local_sha}"]).splitlines()
        commits.update(revs)
    return sorted(commits)


def print_findings(findings: list[Finding]) -> None:
    for finding in findings:
        print(
            f"{finding.source}\t{finding.path}:{finding.line}\t"
            f"{finding.pattern}\t{finding.classification}",
            file=sys.stderr,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracked", action="store_true", help="scan tracked worktree files")
    parser.add_argument("--untracked", action="store_true", help="scan untracked non-ignored files")
    parser.add_argument("--pre-push", action="store_true", help="read git pre-push refs from stdin and scan pushed commits")
    parser.add_argument("--all-history", action="store_true", help="scan all commits reachable from this repository")
    args = parser.parse_args()

    repo = Path(run_git(["rev-parse", "--show-toplevel"]).strip())
    if not any((args.tracked, args.untracked, args.pre_push, args.all_history)):
        args.tracked = True
        args.untracked = True

    findings: list[Finding] = []
    if args.tracked or args.untracked:
        findings.extend(current_findings(repo, tracked=args.tracked, untracked=args.untracked))
    if args.pre_push:
        findings.extend(scan_commits(pre_push_commits(sys.stdin.read())))
    if args.all_history:
        findings.extend(scan_all_history_blobs())

    if findings:
        print("High-confidence secret material found. Matched values are intentionally hidden.", file=sys.stderr)
        print_findings(findings)
        return 1

    print("No high-confidence secret material found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
