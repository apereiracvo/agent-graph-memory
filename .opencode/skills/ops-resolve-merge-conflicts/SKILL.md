---
name: ops-resolve-merge-conflicts
description: Resolve a non-trivial Git merge or rebase conflict while preserving intended changes and repository conventions.
---

# Resolve Merge Conflicts

Use this skill for a non-trivial merge or rebase conflict. Inspect the conflict state with read-only Git commands, group files by the current agent definitions and repository guidance, and preserve intended changes from both sides rather than choosing a side wholesale.

Read the affected documentation, source, configuration, or setup files before resolving. Do not assume application migrations, UI packages, or infrastructure files exist. Run focused, safe validation for the actual files changed, including `git diff --check` and the repository's documented checks where applicable; read scripts before invoking them. Stage, commit, push, or rewrite history only when the human explicitly requests it.

Report conflict groups, resolution rationale, validations, unresolved risks, and any files that require human ownership decisions.