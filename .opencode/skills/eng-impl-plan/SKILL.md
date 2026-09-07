---
name: eng-impl-plan
description: Convert an accepted design or clear requirements into small, trackable implementation cycles for this repository.
---

# Implementation Plan

Read `AGENTS.md`, the design or requirements, and the current repository surfaces before planning. Write `{workbook}/implementation-plan.md` only for a non-trivial tracked change.

For every cycle, specify owner from the current agent definitions, dependencies, exact files to create or modify, acceptance criteria, documented validation commands, review mode (`self` or `formal`), and scope exclusions. Order work around actual dependencies; do not prescribe nonexistent application layers, providers, or tooling. Use `engineering/backend-developer` for Python/Graphiti/Cognee implementation, `engineering/devops-engineer` for Docker/MCP and operational configuration, `operations/librarian` for durable docs, and the other retained agents only where their actual scope applies.

Update the workbook activity log only when assigned. This skill does not implement, commit, deploy, or create a PR.