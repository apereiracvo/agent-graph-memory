#!/usr/bin/env bash
set -e

# ops-init-workbook skill
# Usage: bash .opencode/skills/ops-init-workbook/scripts/init-workbook.sh --team <team> --source-id <id> --title "Title"

# Parse arguments
TEAM=""
SOURCE_ID=""
TITLE=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --team)
      TEAM="$2"
      shift 2
      ;;
    --source-id)
      SOURCE_ID="$2"
      shift 2
      ;;
    --title)
      TITLE="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1"
      exit 1
      ;;
  esac
done

# Validate required arguments
if [[ -z "$TEAM" ]] || [[ -z "$SOURCE_ID" ]] || [[ -z "$TITLE" ]]; then
  echo "Error: Missing required arguments"
  echo "Usage: bash .opencode/skills/ops-init-workbook/scripts/init-workbook.sh --team <team> --source-id <id> --title \"Title\""
  echo ""
  echo "Examples:"
  echo "  bash .opencode/skills/ops-init-workbook/scripts/init-workbook.sh --team engineering --source-id eng-ingest-batch --title \"Ingestion batch improvements\""
  echo "  bash .opencode/skills/ops-init-workbook/scripts/init-workbook.sh --team operations --source-id ops-mcp-audit --title \"MCP safety audit\""
  exit 1
fi

# Validate team
VALID_TEAMS=("engineering" "operations")
VALID_TEAMS_STR="${VALID_TEAMS[*]}"
if [[ ! " ${VALID_TEAMS_STR} " =~ " ${TEAM} " ]]; then
  echo "Error: Invalid team '$TEAM'"
  echo "Valid teams: ${VALID_TEAMS_STR}"
  exit 1
fi

# Validate source-id prefix
case $TEAM in
  engineering)
    REQUIRED_PREFIX="eng-"
    ;;
  operations)
    REQUIRED_PREFIX="ops-"
    ;;
esac

if [[ ! "$SOURCE_ID" =~ ^${REQUIRED_PREFIX} ]]; then
  echo "Error: Source ID must start with '${REQUIRED_PREFIX}' for team '$TEAM'"
  echo "Given: '$SOURCE_ID'"
  echo ""
  echo "Examples for $TEAM:"
  echo "  ${REQUIRED_PREFIX}001"
  echo "  ${REQUIRED_PREFIX}feature-name"
  echo "  ${REQUIRED_PREFIX}spike-description"
  exit 1
fi

if [[ ! "$SOURCE_ID" =~ ^${REQUIRED_PREFIX}[a-z0-9][a-z0-9-]*$ ]]; then
  echo "Error: Source ID may only contain lowercase letters, numbers, and hyphens after '${REQUIRED_PREFIX}'"
  echo "Given: '$SOURCE_ID'"
  echo ""
  echo "Examples for $TEAM:"
  echo "  ${REQUIRED_PREFIX}001"
  echo "  ${REQUIRED_PREFIX}feature-name"
  echo "  ${REQUIRED_PREFIX}spike-description"
  exit 1
fi

# Construct timestamped workbook path.
# Compact timestamp prefix keeps directory listings in creation order.
TIMESTAMP=$(date +%Y%m%d-%H%M)
WORKBOOK_ID="${TIMESTAMP}-${SOURCE_ID}"
WORKBOOK_PATH="docs/temp/$TEAM/$WORKBOOK_ID"

# Check if workbook already exists
if [[ -d "$WORKBOOK_PATH" ]]; then
  echo "Error: Workbook already exists: $WORKBOOK_PATH"
  echo "Tip: To resume, cd into the workbook and update README.md"
  exit 1
fi

# Create workbook directory
mkdir -p "$WORKBOOK_PATH"

# Get current date
DATE=$(date +%Y-%m-%d)
CREATED_AT=$(date +%Y-%m-%dT%H:%M:%S%z)

# Get current agent (from environment or default)
AGENT="${AGENT_ROLE:-systems-architect}"

# Create README.md from template
cat > "$WORKBOOK_PATH/README.md" <<EOF
---
title: "$TITLE"
status: active
owner: $AGENT
team: $TEAM
source_id: "$SOURCE_ID"
workbook_id: "$WORKBOOK_ID"
created_at: "$CREATED_AT"
---

# $TITLE - Workbook

## Purpose

[Why this workbook exists and what it aims to produce]

## Status

Active - just created. Starting work.

## Activity Log

| Date | Agent | Action |
|------|-------|--------|
| $DATE | $AGENT | Created workbook |

---

## Notes

[Optional: Add working notes, decisions, blockers, open questions here]
EOF

# Output success message
echo ""
echo "Workbook created: $WORKBOOK_PATH"
echo "README.md initialized with metadata"
echo ""
echo "Next steps:"
echo "   cd $WORKBOOK_PATH"
echo "   # Create spec.md, notes.md, or other documents"
echo ""