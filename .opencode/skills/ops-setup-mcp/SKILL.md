---
name: ops-setup-mcp
description: Add or reconfigure an OpenCode MCP server after confirming its purpose, safety, and supported configuration.
---

# Setup MCP

Use this skill for a requested OpenCode MCP addition or reconfiguration. First read `AGENTS.md`, `opencode.json`, current agent definitions, and the MCP's current authoritative documentation. Use only the OpenCode configuration surface that exists in this repository; do not create Claude Code configuration or assume other tool integrations.

Before editing, identify transport, package or endpoint, authentication requirements, exposed capabilities, which retained agents need access, output locations, and a low-risk verification method. Keep the Graphiti memory MCP, Context7, and Playwright only unless the human explicitly requests another MCP. Graphiti exposes memory mutation and clear tools: preserve the `enabled` and `timeout` posture, confirm any new graph-capable MCP keeps destructive operations behind explicit confirmation, and never read or authorize reads of `.env.local` or other runtime-local secret files. Do not add real credential values; use repository-approved placeholders only where a tracked example is appropriate.

After an authorized change, validate JSON, restart or rediscover OpenCode if available, list MCPs, and perform only a low-risk tool check. Report configuration paths, agents allowed to use the MCP, validation results, and follow-up requirements. Do not document unverified graph or runtime facts or alter durable docs unless explicitly in scope.