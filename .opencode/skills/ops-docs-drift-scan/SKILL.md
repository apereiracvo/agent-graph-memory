---
name: ops-docs-drift-scan
description: Catalog suspected documentation drift in an active workbook before any durable-document cleanup.
---

# Documentation Drift Scan

Read `AGENTS.md`, the active workbook, relevant durable documentation, and repository state before scanning. Produce a no-edit catalog at `{workbook}/docs-drift-catalog.md` that records scope, search patterns, evidence, classifications, and recommended follow-up.

Classify material hits as confirmed drift, allowed historical context, needs owner decision, already fixed, or out of scope. Verify claims against current repository files and documentation; do not infer graph or runtime state. Do not expose secrets or personal data, and do not modify durable docs as part of this skill. Update the workbook activity log only when assigned.