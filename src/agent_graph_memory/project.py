from __future__ import annotations

import json
import subprocess
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

TEXT_SUFFIXES = {
    ".css",
    ".graphql",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".py",
    ".rs",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
TEXT_NAMES = {"Dockerfile", "Makefile", "Procfile"}
SKIPPED_PARTS = {".git", ".graphiti", ".venv", "dist", "node_modules", "vendor"}


@dataclass(frozen=True)
class Episode:
    name: str
    source_description: str
    reference_time: str
    body: str


def _git_files(root: Path) -> list[Path] | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return [root / line for line in result.stdout.splitlines() if line]


def project_files(root: Path) -> Iterable[Path]:
    candidates = _git_files(root) or [path for path in root.rglob("*") if path.is_file()]
    for path in sorted(candidates):
        relative = path.relative_to(root)
        if any(part in SKIPPED_PARTS for part in relative.parts):
            continue
        if path.name not in TEXT_NAMES and path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        yield path


def extract_project(root: Path, max_file_bytes: int = 100_000) -> list[Episode]:
    root = root.resolve()
    episodes = []
    for path in project_files(root):
        if path.stat().st_size > max_file_bytes:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        relative = path.relative_to(root).as_posix()
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
        episodes.append(
            Episode(
                name=f"project file: {relative}",
                source_description=f"File {relative} from project {root.name}",
                reference_time=modified,
                body=(
                    f"Project: {root.name}\n"
                    f"Path: {relative}\n"
                    f"File contents:\n\n{content}"
                ),
            )
        )
    return episodes


def write_jsonl(episodes: Iterable[Episode], destination: Path) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with destination.open("w", encoding="utf-8") as output:
        for episode in episodes:
            output.write(json.dumps(asdict(episode), ensure_ascii=True) + "\n")
            count += 1
    return count


def read_jsonl(source: Path) -> Iterable[Episode]:
    with source.open(encoding="utf-8") as lines:
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                yield Episode(**json.loads(line))
            except (json.JSONDecodeError, TypeError) as error:
                raise ValueError(f"Invalid episode at {source}:{line_number}: {error}") from error
