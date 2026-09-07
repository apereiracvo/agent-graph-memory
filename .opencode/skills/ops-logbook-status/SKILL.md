---
name: ops-logbook-status
description: >
  Show the status of task workbooks under `docs/temp/`. Lists active workbooks with
  their age, title, and staleness indicator. Can filter by team or show only stale workbooks.
---

# Workbook Status

Displays a status report of active task workbooks under `docs/temp/`.

## Usage

```bash
bash .opencode/skills/ops-logbook-status/scripts/status.sh [--team <team>] [--stale]
```

## Arguments

| Argument | Required | Description |
| -------- | -------- | ----------- |
| `--team` | No | Filter by team such as `engineering` or `operations` |
| `--stale` | No | Show only stale workbooks |

## Examples

```bash
bash .opencode/skills/ops-logbook-status/scripts/status.sh
bash .opencode/skills/ops-logbook-status/scripts/status.sh --team engineering
bash .opencode/skills/ops-logbook-status/scripts/status.sh --stale
```

## When to Use

- Before starting new work, to see what is already in progress
- During planning, to review active workbooks
- To find stale workbooks that need attention or archiving

## Output

The report shows each workbook with its team, source ID, age, title, and staleness summary.