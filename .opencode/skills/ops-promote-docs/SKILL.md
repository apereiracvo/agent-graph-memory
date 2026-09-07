---
name: ops-promote-docs
description: Extract verified durable documentation from a completed workbook after explicit human approval.
---

# Promote Documentation

Use this skill only after a workbook is complete and the human explicitly approves promotion. Read `AGENTS.md`, the workbook, referenced implementation or configuration files, and the relevant durable documentation. Preserve the repository's documentation rules: durable Markdown belongs under `docs/` (and any `cognee_bench/README.md` or `reports/` notes for those surfaces), and documentation must reflect observed, verified repository state rather than intent.

First present a minimal promotion plan that identifies authoritative target documents, verified facts to add, artifacts to exclude, and any drift handling. Do not copy a workbook wholesale. After approval, update only the documented source of truth, preserve `.env.example` placeholders instead of real values, and do not promote secrets, personal data, local configuration, `.graphiti/` episodes, raw HP content, Cognee `.state`, or generated run artifacts unless explicitly scoped as reports.

Update the workbook status and activity log only when readiness and approval conditions are met. Do not modify source, graph, or container runtime as part of this documentation workflow.