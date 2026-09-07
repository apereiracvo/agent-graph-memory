---
name: eng-code-review
description: Perform a structured read-only formal review of one tracked implementation cycle and write a workbook review artifact.
---

# Review Implementation Cycle

Review the assigned cycle without modifying repository files. Read `AGENTS.md`, the active workbook plan, changed files, relevant repository documentation, and the smallest necessary local context.

Write `{workbook}/phase-{N}-review.md` with an **APPROVE**, **APPROVE WITH CONDITIONS**, or **REQUEST CHANGES** verdict. Categorize findings as Blocker, Should Fix, or Suggestion; every finding must give a path, location, rationale, and recommended correction.

Assess acceptance criteria, accuracy, safety, source-of-truth discipline, configuration/documentation consistency, secret handling, generated-output hygiene, and validation evidence. Evaluate Python, Graphiti/Cognee, Docker/MCP, browser, or data concerns only when the changed files actually contain those surfaces. Do not assume an application layout, cloud provider, or domain model. The reviewer may write only the assigned review artifact and activity-log row when assigned.