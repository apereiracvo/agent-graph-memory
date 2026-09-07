---
name: eng-impl-plan-review
description: Perform a structured read-only review of a workbook implementation plan.
---

# Review Implementation Plan

Review `{workbook}/implementation-plan.md` without modifying it. Read `AGENTS.md`, upstream workbook artifacts when relevant, current agent definitions, and enough repository context to verify paths and commands.

Write `{workbook}/review-implementation-plan.md` with an **APPROVE**, **APPROVE WITH CONDITIONS**, or **REQUEST CHANGES** verdict and categorized findings. Check scope coverage, dependency order, ownership, actual paths, feasible validation, safety (including graph-isolation and confirmation gates for destructive operations), review placement, and exclusions. Do not assume application or deployment topology that the repository does not document. Update the workbook activity log only when assigned.