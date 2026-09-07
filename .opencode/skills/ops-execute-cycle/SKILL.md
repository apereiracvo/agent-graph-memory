---
name: ops-execute-cycle
description: Execute one planned repository change cycle through implementation, validation, and the configured review path.
---

# Execute Cycle

Read `AGENTS.md`, the active workbook, and the referenced implementation plan before acting. Confirm the selected cycle, ownership, dependencies, editable paths, acceptance criteria, and documented validation commands. Stop and report if the workbook or plan is unavailable.

Implement only the cycle's authorized files using observed repository conventions. Run only safe, documented local verification (`uv run pytest tests`, `uv run ruff check src tests`, `docker compose config`); read a script or runbook before invoking it, and never run graph-destructive, container-destructive, or server-affecting commands (`docker compose down -v`, MCP clear tools, `.graphiti/` deletion) without explicit human authorization and a scoped graph.

For `formal` review, use `eng-code-review` and send required findings to a separate implementing agent. For `self` review, check each acceptance criterion and validation result. Update the plan and workbook activity log only when assigned. Do not stage, commit, deploy, publish, or create external changes unless the human explicitly asks.