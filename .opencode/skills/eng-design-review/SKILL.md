---
name: eng-design-review
description: Perform a structured read-only review of a workbook design artifact.
---

# Review Design

Review `{workbook}/design.md` without applying changes. Read `AGENTS.md`, the design, upstream workbook artifacts when relevant, and referenced repository documentation or source files.

Write `{workbook}/review-design.md` with an **APPROVE**, **APPROVE WITH CONDITIONS**, or **REQUEST CHANGES** verdict and categorized, evidence-backed findings. Review repository fit, observed paths and commands, safety (including graph-destructive operation scope), file ownership, validation, compatibility or rollback, open questions, and scope boundaries.

Do not assume absent application, cloud, or deployment infrastructure. The reviewer may write only the assigned review artifact and activity-log row when assigned.