import json
from pathlib import Path

from agent_graph_memory.project import extract_project, read_jsonl, write_jsonl


def test_extract_project_filters_and_describes_files(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("print('hello')\n")
    (tmp_path / "image.png").write_bytes(b"not text")

    episodes = extract_project(tmp_path)

    assert len(episodes) == 1
    assert episodes[0].name == "project file: app.py"
    assert "print('hello')" in episodes[0].body


def test_jsonl_round_trip(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Test\n")
    destination = tmp_path / "episodes.jsonl"

    assert write_jsonl(extract_project(tmp_path), destination) == 1
    raw = json.loads(destination.read_text().strip())
    assert raw["name"] == "project file: README.md"
    assert next(iter(read_jsonl(destination))).body.endswith("# Test\n")
