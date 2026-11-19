# Project Agent Instructions

Before substantive project work, read `agent/AGENTS.md`, `agent/PROJECT.md`, and the relevant role guide in `agent/`. Follow their workflow, owner-confirmation gates, and project rules.

If you are the main session the owner talks to, you are the **Orchestrator**: read `agent/ORCHESTRATOR.md` and follow its "Session start" steps (begin with `docs/pr<N>/PROGRESS.md` on the PR's working branch) before doing anything else. Run every other role as a separate subagent, talk to the owner in Chinese, and treat the owner's short commands (`进度`, `继续`, `讲解`, `开始修改`, `这块可以了`, `待决定`, `验证`, `保存进度`, or their English forms) as defined in `agent/ORCHESTRATOR.md`.

If you were started as a role subagent (Planner, Analyst, Reviewer, Reporter, Validator), follow only your role guide in `agent/`.
