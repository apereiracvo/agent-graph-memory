from __future__ import annotations

import argparse
from pathlib import Path

from agent_graph_memory.compat import patch_graphiti_core, patch_mcp_server


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graphiti-root", type=Path)
    parser.add_argument("--mcp-root", type=Path)
    args = parser.parse_args()

    patch_graphiti_core(args.graphiti_root)
    if args.mcp_root:
        patch_mcp_server(args.mcp_root)


if __name__ == "__main__":
    main()
