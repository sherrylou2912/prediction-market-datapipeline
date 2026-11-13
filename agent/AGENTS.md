# Agent Instructions

Project: prediction-market-datapipeline.

## Workflow and roles

- Start each substantive PR or task by reading `agent/PROJECT.md`, this file, the request, and the relevant role guide. These are guidance files, not automatically running agents.

### Roles

| Role | Guide | Responsibility | Modifies code? |
| --- | --- | --- | --- |
| Planner | `PLANNER.md` | Define scope, blocks, and acceptance criteria; ask the owner about unresolved open choices. | No |
| Analyst | `ANALYST.md` | Implement the agreed block; address review findings. | Yes |
| Reviewer | `REVIEWER.md` | Review each Analyst revision inside the block loop; raise findings until none remain. | No |
| Reporter | `REPORTER.md` | Report the converged block to the owner, including what review changed, and propose further changes. | No |
| Validator | `VALIDATOR.md` | Independently validate the final change after all block loops finish, including code necessity and simplification proposals. | No |

### Process

```text
Planner prepares the brief and blocks using the owner's request and prior decisions
  │
  ├─► Block loop (repeat for each block)
  │     ┌──────────────────────────────────────────────┐
  │     │ 1. Analyst implements / revises the block     │
  │     │ 2. Reviewer reviews the latest revision       │
  │     │    ├─ open findings → back to step 1          │
  │     │    └─ no open findings → converged            │
  │     └──────────────────────────────────────────────┘
  │     3. Reporter reports the block and proposes further changes
  │     4. Continue within the authorized scope; ask the owner only
  │        when an open decision cannot be resolved from project context
  │
  └─► All blocks done → Validator validates the final change
        ├─ changes required → Analyst fixes → Reviewer loop → Reporter → Validator rechecks
        └─ ready for owner review → owner decides merge
```

1. **Plan.** Planner prepares the task brief and meaningful blocks from the owner's request, prior decisions, and project rules (see `PLANNER.md`). Make and record routine choices autonomously. Ask the owner only when a material open question requires their preference, the available evidence cannot resolve a decision, or explicit authorization is otherwise required.
2. **Implement.** Analyst implements one block and hands Reviewer a revision packet (see `ANALYST.md`).
3. **Review.** Reviewer reviews the latest revision and records findings for the round (see `REVIEWER.md`). Analyst addresses every open finding — fix, or dispute with evidence — and hands over a new revision. Repeat steps 2–3.
4. **Converge.** The block loop ends when Reviewer reports no open `must-fix` or `should-fix` findings on the latest revision and the required checks pass. `suggestion` and `out-of-scope` items do not block convergence; they pass to Reporter.
5. **Report.** Reporter explains to the owner what the block does, what each review round changed, which disputes or deferrals remain, and proposes further changes for the next loop (see `REPORTER.md`).
6. **Continue or ask.** After reporting, continue to the next authorized loop or block without requesting routine confirmation. Record agent-made choices and reasons separately from owner-confirmed decisions. Pause only work that depends on an unresolved open question or an explicitly required authorization; continue independent work where possible. Keep changes within the requested scope and honor any explicit request to pause or review first.
7. **Validate.** After all authorized block loops are reported and no unresolved decision blocks validation, Validator independently validates the whole change (see `VALIDATOR.md`). Findings return to Analyst and go through the Reviewer loop and a Reporter report again before Validator rechecks. Only `ready for owner review` ends the workflow; the owner decides merge.

### Loop rules

- **Review log.** Record every round in `docs/pr<N>/REVIEW_LOG.md` (create it on the first round of the PR and register it in `docs/README.md`). Each round lists the reviewed revision, findings with IDs and severity, Analyst's response, and the checks each side actually ran. Reporter and Validator read this log; it is the evidence of what the loop changed.
- **Round limit.** If a block has not converged after 3 review rounds, or Analyst and Reviewer disagree on a finding after one exchange, stop the loop and escalate to the owner through Reporter with both positions. Do not loop indefinitely or let either role silently drop a finding.
- **Scope.** Reviewer findings must concern the current block and brief. New features, redesigns, or later-PR work are marked `out-of-scope` and go to Reporter as proposals; Analyst does not implement them unless already authorized.
- **Design decisions.** Resolve routine implementation and design choices using the approved project rules and task context; explain tradeoffs and record the decision. Escalate a genuinely open question that requires the owner's preference, a conflict with an approved decision, or a new dependency requiring authorization before implementing it.
- **Independence.** Run Reviewer and Validator in a context separate from Analyst (e.g., a fresh subagent or session) that receives the revision packet, not Analyst's reasoning. Validator should also be separate from Reviewer. For small tasks one agent may perform multiple roles, but say so explicitly in the report; a separate context is preferred for high-risk changes and is not proof of independence.
- **Small tasks.** For trivial changes (typos, documentation-only wording) the owner may waive the review loop or the Validator gate; record the waiver in the report.

### Handoff and evidence

- At each handoff identify the task, branch and worktree or commit, changed files, decisions, actual checks and results, failures, and unverified items. Do not treat planning, a report, a converged review loop, or a green test as proof of production readiness.
- Preserve existing work. Before a commit inspect staged changes; after a PR is opened, review the latest head and its checks. After merge, record the merged revision, verification, limitations, and handoff. Do not claim an unrun check passed or approve, merge, deploy, or trade without the owner's authorization.

## Authority and language

- `PROJECT.md` is the single source of truth for the v1 rebuild. Resolve conflicting code or documentation against it unless an explicit architectural decision changes it.
- Communicate with the project owner in Chinese. Prefer Chinese for new or updated Markdown and human-facing explanations where practical; retain clear English identifiers and established external formats. Do not translate existing files solely to change their language.

## Hard rules

1. All new venue integrations implement `VenueAdapter`. Keep venue-specific behavior inside adapters.
2. Never silently discard data or failures. Raise, log, or quarantine them with a reason.
3. Advance a checkpoint only after its data file is durably written, validated, and registered in a manifest.
4. Send anomalous records to `quarantine/`; never silently admit them to Silver.
5. Read secrets only from the environment. Never put them in code, logs, prompts, or documentation.
6. Do not add dependencies without the project owner's approval.
7. Update affected documentation with every PR.
8. Derive all new pipeline data paths from `DATA_ROOT`. Use a layer-scoped writer for data writes.
9. Read-only task entry points call `PipelineConfig.validate_for_read()`. Write-producing task entry points call `PipelineConfig.validate_for_write()` before `DataLayout.create()` or any data write. Keep the general `check` command free of disk-space probes and write side effects.
10. Put tunable job and experiment parameters in `src/config/` instead of scattering literals through task code. Provide documented defaults only when they are safe; keep required values explicit. Validate every effective parameter, including type, range, and relationships with other parameters, before an experiment starts or data processing has side effects. Reject invalid settings immediately with a clear error. At job start, log the effective non-secret values and whether defaults or overrides were used; never log secrets.
11. Every `src/config/` change must follow `src/config/developing.md`, add only files required by the current PR, and update both `src/config/README.md` and `src/config/README_FOR_DEVELOPER.md` in the same change.

## Conventions

- Support Python 3.9 and newer. Use `uv` for the existing environment and `ruff` for lint and format checks.
- Bronze is immutable raw data; Silver is validated canonical data; Gold is a purpose-built product.
- Use `uv run ruff check .`, `uv run ruff format --check .`, and `uv run pytest tests/ -v` before delivery.
- Keep legacy indexers separate from the v1 pipeline until their respective migration PRs.
- Keep documentation in the layout described by `docs/README.md`: PR-specific plans, rules, and reading progress under `docs/pr<N>/`, architecture decision records under `docs/adr/`, and legacy-workflow docs under `docs/legacy/`. Add new documents to that index.
- Keep the new pipeline under `src/`; do not use a version number as the source folder name. Put settings and validation in `src/config/`, contracts in `src/data_schema/`, data directory and writer code in `src/data_io/`, and venue implementations in `src/adapters/`.

## Owner notes

- Keep the project owner's private design notes in `docs/notes.md`.
- Write them in concise Chinese as numbered entries. State the idea, pipeline, and called functions; mark proposed functions as unimplemented.
- Never include secrets, credentials, or personal data.
