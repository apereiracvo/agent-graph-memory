---
name: ops-init-workbook
description: >
  Initialize a task workbook for a team. Creates a `docs/temp/<team>/<timestamp>-<source-id>/`
  directory with a `README.md` containing metadata and an activity log.
  Use this when starting any non-trivial task that needs a workbook for specs, research, or artifacts.
---

# Init Workbook

Creates a new task workbook directory under `docs/temp/<team>/<timestamp>-<source-id>/` with a templated `README.md`.

The timestamp uses compact sortable format `YYYYMMDD-HHMM` so directory listings show workbooks in creation order.

## Usage

```bash
bash .opencode/skills/ops-init-workbook/scripts/init-workbook.sh --team <team> --source-id <id> --title "Title"
```

## Arguments

| Argument | Required | Description |
| -------- | -------- | ----------- |
| `--team` | Yes | Team name, usually `engineering` for feature work |
| `--source-id` | Yes | Unique ID with a team prefix such as `eng-ingest-batch`; use lowercase letters, numbers, and hyphens only after the prefix |
| `--title` | Yes | Human-readable workbook title |

### Source ID Prefixes

| Team | Prefix | Example |
| ---- | ------ | ------- |
| Engineering | `eng-` | `eng-ingest-batch` |
| Operations | `ops-` | `ops-mcp-audit` |

## Examples

```bash
bash .opencode/skills/ops-init-workbook/scripts/init-workbook.sh \
  --team engineering --source-id eng-ingest-batch --title "Ingestion batch improvements"
```

## When to Use

- Starting any multi-step feature or investigation
- Beginning a spike or research task
- Any task that will produce specs, plans, or research artifacts
- Not needed for trivial bugfixes

## What It Creates

```text
docs/temp/<team>/<timestamp>-<source-id>/
  README.md
```

Example generated path:

```text
docs/temp/engineering/20260608-1430-eng-ingest-batch/
  README.md
```

The README metadata keeps both the original `source_id` and the full timestamped `workbook_id`, plus `created_at`.

## Environment Variables

- `AGENT_ROLE` — if set, used as the workbook owner in the README. Defaults to `engineering/systems-architect`.