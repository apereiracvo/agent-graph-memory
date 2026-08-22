from __future__ import annotations

import argparse
import asyncio
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_EPISODES = Path(".graphiti/episodes.jsonl")
load_dotenv(".env.local")

from agent_graph_memory.compat import patch_graphiti_core

patch_graphiti_core()

from graphiti_core.nodes import EpisodeType

from agent_graph_memory.graph import graphiti_client, group_id
from agent_graph_memory.project import extract_project, read_jsonl, write_jsonl


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="graph-memory")
    commands = parser.add_subparsers(dest="command", required=True)

    extract = commands.add_parser("extract", help="Extract text files into inspectable JSONL")
    extract.add_argument("project", nargs="?", type=Path, default=Path.cwd())
    extract.add_argument("--output", type=Path, default=DEFAULT_EPISODES)
    extract.add_argument("--max-file-bytes", type=int, default=100_000)

    ingest = commands.add_parser("ingest", help="Ingest extracted episodes into Graphiti")
    ingest.add_argument("episodes", nargs="?", type=Path, default=DEFAULT_EPISODES)
    ingest.add_argument("--limit", type=int)

    query = commands.add_parser("query", help="Search facts in the project graph")
    query.add_argument("text")
    query.add_argument("--limit", type=int, default=10)

    benchmark = commands.add_parser("benchmark", help="Measure and project Graphiti API costs")
    benchmark.add_argument("--output-dir", type=Path, default=Path("reports"))
    return parser


def _require_openai_key() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required; copy .env.example to .env and set it")


async def _ingest(path: Path, limit: int | None) -> None:
    _require_openai_key()
    episodes = list(read_jsonl(path))
    if limit is not None:
        episodes = episodes[:limit]
    async with graphiti_client() as client:
        for index, episode in enumerate(episodes, start=1):
            print(f"[{index}/{len(episodes)}] {episode.name}")
            await client.add_episode(
                name=episode.name,
                episode_body=episode.body,
                source_description=episode.source_description,
                reference_time=datetime.fromisoformat(episode.reference_time),
                source=EpisodeType.text,
                group_id=group_id(),
            )


async def _query(text: str, limit: int) -> None:
    _require_openai_key()
    async with graphiti_client() as client:
        results = await client.search(text, group_ids=[group_id()], num_results=limit)
    if not results:
        print("No facts found.")
        return
    for result in results:
        print(f"- {result.fact}")


def main() -> None:
    args = _parser().parse_args()
    if args.command == "extract":
        count = write_jsonl(
            extract_project(args.project, max_file_bytes=args.max_file_bytes), args.output
        )
        print(f"Wrote {count} episodes to {args.output}")
    elif args.command == "ingest":
        asyncio.run(_ingest(args.episodes, args.limit))
    elif args.command == "query":
        asyncio.run(_query(args.text, args.limit))
    elif args.command == "benchmark":
        from agent_graph_memory.benchmark import run_benchmark

        json_path, markdown_path = asyncio.run(run_benchmark(args.output_dir))
        print(f"Wrote {json_path} and {markdown_path}")


if __name__ == "__main__":
    main()
