# Skills Framework

Skills are reusable workflows packaged as documentation plus optional scripts.

## Structure

Each skill is a directory containing:

```text
{skill-name}/
├── SKILL.md
└── scripts/
    └── {script}.sh
```

## Skill Discovery

Skills are discovered from their directories under `.opencode/skills/`. Do not maintain a manual skill list here; it drifts as skills are added, renamed, or removed. Use the `name` and `description` frontmatter in each `SKILL.md` as the source of truth.

## Adding a skill

1. Create a directory in `.opencode/skills/{your-skill-name}/`
2. Write `SKILL.md` with the skill description and usage contract
3. Add `scripts/` only if the workflow needs executable helpers
4. Reference the skill from agent instructions

## Repository-specific skills

Keep repository-specific skills in `.opencode/skills/` and document their scope clearly in the skill's `SKILL.md`.

## Invocation

Agents load skills through the OpenCode skill tool. Keep this README index-level; put workflow details in each skill's `SKILL.md`.