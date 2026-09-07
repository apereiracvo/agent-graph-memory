---
name: eng-design
description: Create a repository-aligned design artifact for a non-trivial Python, Graphiti/Cognee, Docker/MCP, or documentation change.
---

# Design

Create `{workbook}/design.md` for a non-trivial change after reading `AGENTS.md`, the root README, and relevant current documentation or source files.

Use this when the change has material unknowns, crosses repository surfaces, or needs decisions before implementation. Do not use it for a small, directly specified documentation correction.

The design must identify the observed current state, intended outcome, affected paths, ownership, compatibility or rollback concerns (including graph/`.state` safety), validation approach, open questions, and explicit exclusions. Use only repository paths and commands verified during the work. Do not invent a service, deployment system, UI, or data store.

Write only the assigned workbook artifact, update the workbook activity log when assigned, and report the design summary and open questions. Do not implement the design.