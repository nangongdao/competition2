<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

This project is managed by Trellis. The working knowledge you need lives under `.trellis/`:

- `.trellis/workflow.md` — development phases, when to create tasks, skill routing
- `.trellis/spec/` — package- and layer-scoped coding guidelines (read before writing code in a given layer)
- `.trellis/workspace/` — per-developer journals and session traces
- `.trellis/tasks/` — active and archived tasks (PRDs, research, jsonl context)

If a Trellis command is available on your platform (e.g. `/trellis:finish-work`, `/trellis:continue`), prefer it over manual steps. Not every platform exposes every command.

If you're using Codex or another agent-capable tool, additional project-scoped helpers may live in:
- `.agents/skills/` — reusable Trellis skills
- `.codex/agents/` — optional custom subagents

Managed by Trellis. Edits outside this block are preserved; edits inside may be overwritten by a future `trellis update`.

<!-- TRELLIS:END -->

## Project Delivery Requirements

After completing any upgrade or feature, publish the completed work to the project repository at `https://github.com/nangongdao/competition2`.

Use meaningful Conventional Commit messages so the history explains the work clearly. Good examples include:

- `feat: 完成用户登录模块`
- `fix: 修复数据展示错误`
- `docs: 更新项目提交和 PR 流程`

Project submissions must be delivered through a Pull Request (PR). Follow the activity guidance for the target repository, open the PR against the appropriate branch, and include the day's progress in the PR description.

Before opening a PR, make sure the submitted branch contains only the relevant changes for that upgrade or feature and that validation commands have been run where applicable.
