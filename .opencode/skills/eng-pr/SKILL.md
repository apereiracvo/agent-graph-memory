---
name: eng-pr
description: Create a reviewer-friendly GitHub pull request from an already implemented branch when explicitly requested.
---

# Pull Request

Use this skill only when the human explicitly requests a PR. Before creating one, inspect the full branch scope, current working tree, selected base branch, recent commits, and the branch diff. Read `AGENTS.md` and affected repository documentation so the summary reflects the actual experimental Graphiti/Cognee project.

Draft a concise title and body covering the outcome, changed paths, validation (`uv run pytest tests`, `uv run ruff check src tests`, `docker compose config`), risks, reviewer focus, and any graph/container follow-up. Do not claim graph or runtime changes occurred merely because source or documentation changed. Do not invent a default branch, deployment workflow, release scheme, or infrastructure topology; use the human-provided base branch or report that it needs confirmation.

Create the PR with `gh` only after the branch is ready and the human has requested publication. Return the PR URL, title, and validation summary. Do not alter version files, deploy, stage, commit, or push unless explicitly requested as part of the task.