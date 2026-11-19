# Agent Instructions

Project: prediction-market-datapipeline.

## Workflow

Read `agent/PROJECT.md`, this file, the request, and the relevant role guide before substantive work. The main session the owner talks to is the Orchestrator and also follows `agent/ORCHESTRATOR.md`, starting each session by reading `docs/pr<N>/PROGRESS.md`. The other role guides are instructions for subagents; they do not run by themselves.

### Roles

| Role | Guide | Job | May edit |
| --- | --- | --- | --- |
| Orchestrator | `ORCHESTRATOR.md` | The main session the owner talks to. Starts every other role as a subagent, relays owner questions, commits converged blocks, keeps `PROGRESS.md` current, keeps the owner informed. Never plans, codes, reviews, explains code, or validates itself. | Process records (`PROGRESS.md`, owner answers in `PLAN.md` and `REVIEW_LOG.md`) |
| Planner | `PLANNER.md` | Turn the request into a plan of phases and blocks with acceptance examples. | `PLAN.md` |
| Analyst | `ANALYST.md` | Implement a block; fix or dispute findings; apply owner feedback. | Code, tests, project docs, its response in `REVIEW_LOG.md`, checklist in `PROGRESS.md` |
| Reviewer | `REVIEWER.md` | Review one Analyst revision per round; raise findings and owner questions. | Its round in `REVIEW_LOG.md` |
| Reporter | `REPORTER.md` | Explain a finished phase to the owner, block by block, and answer follow-up questions. | `PROGRESS.md`, Decisions section of `PLAN.md` |
| Validator | `VALIDATOR.md` | Independently check the whole PR after every phase is accepted. | Nothing |

**Independence.** Each role step is a **new subagent**; nobody, including the Orchestrator, plays two roles. The one exception is that a Reporter keeps answering the owner's follow-up questions for the phase report it started. Roles pass context only through files: `PLAN.md`, the revision packet, `REVIEW_LOG.md`, and `PROGRESS.md`. Reviewer and Validator never see Analyst's reasoning. In Claude Code, use the role agents in `.claude/agents/`; elsewhere use any separate-context mechanism and say which one was used.

### Terms

- **Block:** one change that can be reviewed on its own (e.g., PR2 `B2`, the SQLite ledger). IDs `B1`, `B2`, ….
- **Phase:** a group of related blocks that is built completely and then reported to the owner together. IDs `P1`, `P2`, …. A small PR may be a single phase.
- **Inner loop:** Analyst ⇄ Reviewer on one block until Reviewer marks it `converged`.
- **Feedback loop:** owner feedback on a reported phase → inner loops on the affected blocks → Reporter reports the changes → more feedback, until the owner accepts the phase.

### Flow

```text
Planner writes PLAN.md (phases + blocks) ─► owner approves the plan              [pause 1]
│
├─► Phase P1
│     ├─ inner loop for each block: Analyst ⇄ Reviewer until converged
│     │     (blocking design question ─► ask owner now                          [pause 2])
│     │     (block converged ─► Orchestrator commits it to the PR branch)
│     ├─ all blocks converged ─► Reporter explains P1, one block at a time      [pause 3]
│     ├─ owner feedback ─► "start fixes" ─► inner loops on affected blocks
│     │     ─► Reporter reports only what changed ─► more feedback …
│     └─ owner says the phase is accepted
├─► Phase P2 … (same)
│
└─► every phase accepted ─► Validator checks the whole PR
      ├─ changes required ─► inner loops ─► Reporter reports the changes ─► new Validator rechecks
      └─ ready for owner review ─► owner decides merge                          [pause 4]
```

### Steps

1. **Plan.** A Planner subagent writes `docs/pr<N>/PLAN.md`: goal, scope, phases, blocks with acceptance examples, and dependencies between blocks. Routine choices are made and recorded with their reason; open choices become owner questions. **Pause 1:** work starts only after the owner approves the plan.
2. **Inner loop (each block of the current phase).**
   1. An Analyst subagent implements the block and ends with a revision packet.
   2. A new Reviewer subagent reviews the revision on disk, reruns the checks itself, and writes the round in `REVIEW_LOG.md`.
   3. If any `must-fix` or `should-fix` is open, a new Analyst step addresses each one (fixed or disputed with evidence), then a new Reviewer round follows. A fix counts as resolved only after a later Reviewer round confirms it.
   4. The block is `converged` when no `must-fix`, `should-fix`, or blocking owner question is open and lint, format, and the full test suite pass in Reviewer's own run.
   5. The Orchestrator then commits the block's changes to the PR branch (never pushes) with a message naming the block and its final review round.

   The owner is not given a report during the inner loop, only a one-line progress note after each step (e.g., "B2 round 2 reviewed: 1 should-fix open, back to Analyst").
3. **Phase report.** When every block of the phase has converged, a Reporter subagent explains the phase in Chinese, **one block at a time**, and moves to the next block when the owner says so (see `REPORTER.md`). It also asks the non-blocking owner questions collected during review. **Pause 3:** the workflow waits while the owner reads and asks questions; the same Reporter answers follow-ups.
4. **Feedback.** Reporter records each owner remark with an ID (`P1-F3` = phase 1, feedback 3) and a type:
   - *question*: Reporter answers it; no code change and no record needed;
   - *change request*: added to the open change requests in `PROGRESS.md` and handled in the feedback loop;
   - *decision*: recorded as owner-confirmed in the Decisions section of `PLAN.md`; if it needs a code change it is also added as a change request.
5. **Feedback loop.** When the owner says "start fixes", the Orchestrator groups the open change requests by block and runs an inner loop for each affected block. Then a Reporter subagent reports **only what changed**: each feedback item, how it was handled, the review rounds it took, and the checks rerun. Blocks without changes are not re-explained. Each Reviewer round names the feedback IDs it addresses, so `REVIEW_LOG.md` keeps the history. Repeat steps 4–5 until the owner says the phase is accepted; record the acceptance in `PLAN.md`. Then start the next phase.
6. **Validate.** When every phase is accepted, a Validator subagent checks the whole PR. Its findings go through inner loops and a changes-only Reporter report; then a **new** Validator subagent rechecks. Only `ready for owner review` ends the workflow. **Pause 4:** the owner decides merge.

Outside the four pauses and blocking owner questions, the Orchestrator keeps going without asking for routine confirmation, and stops whenever the owner asks it to.

### Rules

- **Every change goes through the loop.** This includes one-line fixes, doc changes that affect behavior or rules, and anything the owner asks for during a report. Nothing is edited directly in the main session. The owner may waive the loop for one trivial change (typo, wording); record the waiver in `PROGRESS.md`.
- **Owner questions.** Any role raises one when the plan, earlier decisions, and project rules cannot settle a choice.
  - *Blocking* (the current block cannot continue correctly without the answer): the Orchestrator asks it right away. Work on other blocks continues.
  - *Non-blocking*: collected in `PROGRESS.md` and asked during the phase report.
  - Every question uses this format, in Chinese, answerable in a minute by a non-specialist: (1) one-sentence background in everyday words; (2) a concrete scenario or short timeline showing what happens now; (3) two or three options, each saying what would happen and what it costs; (4) a recommendation with a one-sentence reason.
  - Record each answer (date, "owner-confirmed") in the Decisions section of `PLAN.md` and in the review round that raised it.
- **Round limit.** Up to 8 review rounds per block per loop. Escalate earlier only if Analyst and Reviewer still disagree on a finding after two exchanges, or the same finding stays `not resolved` for three rounds in a row. At 8 rounds the Orchestrator asks the owner whether to continue. After an owner decision the loop resumes; escalation never ends a block.
- **Decisions.** Record agent-made choices with their reason separately from owner-confirmed decisions. Never change an approved decision without asking.
- **Scope.** Findings concern the current block and plan. Later-phase or later-PR work is `out-of-scope` and goes into the phase report as a proposal.
- **Records** (all on the PR's working branch only; never merged into `main`):

  | File | Contents |
  | --- | --- |
  | `docs/pr<N>/PLAN.md` | Phases, blocks, acceptance examples; Decisions (owner-confirmed and agent decisions, phase acceptances); future-PR requirements. Grows over time. |
  | `docs/pr<N>/REVIEW_LOG.md` | Every review round: what it addresses (findings, feedback IDs, Validator findings), checks each side ran, findings, Analyst responses, owner questions. Grows over time. |
  | `docs/pr<N>/PROGRESS.md` | **Latest snapshot only**, rewritten each time: handoff note, status of each phase and block, open change requests, open owner questions, next step. Older versions live in git history. |

  Block states: `not started` → `implementing` → `in review (round n)` → `waiting for owner` → `converged`. Phase states: `in development` → `ready to report` → `reporting` → `fixing feedback (loop n)` → `accepted`.

### Talking to the owner

The owner reads every report, question, and progress note, and is not a senior software engineer. Every role that writes for the owner follows these rules:

- **Language.** Talk to the owner in Chinese. Write owner-facing documents (`PLAN.md`, `REVIEW_LOG.md`, `PROGRESS.md`, explanation notes) in Chinese, keeping code identifiers, commands, and severity labels in English. Agent documents (`agent/*.md`, `.claude/agents/`, `.claude/commands/`) are written in English.
- **Plain words.** Short sentences. Explain every technical term in one simple sentence the first time it appears (e.g., "a transaction is a group of changes that either all happen or none happen"). If an explanation only makes sense to an expert, rewrite it.
- **Human order.** Explain code in the order a person would follow it: what it is for and what triggers it, then the steps in the order they actually happen, saying *why* each step exists before *how* it works. Do not walk through functions in file order.
- **Small examples.** Explain anything non-trivial with a concrete example using real values or a short timeline (e.g., "10:00 task A writes `a.parquet`; 10:01 task B tries to move the same checkpoint and is rejected because …").
- **Conclusion first.** Start with the answer, then the details. Say clearly what was verified by running something and what is an inference.

### Shortcut commands

The owner can drive the workflow with short commands, in English or Chinese, with or without `/` (in Claude Code they are slash commands in `.claude/commands/`). `agent/ORCHESTRATOR.md` defines exactly what each one does.

| Command | 中文 | Purpose |
| --- | --- | --- |
| `status` | `进度` | Where the PR stands |
| `continue work` | `继续` | Run the next steps until the owner is needed |
| `explain [phase or block]` | `讲解 [阶段或块]` | Reporter explains a phase, one block at a time (`next` / `下一个`) |
| `start fixes` | `开始修改` | Send the phase's open change requests into the feedback loop |
| `accept phase` | `这块可以了` | Accept the current phase and move on |
| `decisions` | `待决定` | Ask every open owner question |
| `validate` | `验证` | Run Validator once every phase is accepted |
| `save progress` | `保存进度` | Rewrite `PROGRESS.md` as a short handoff for the next session; use at the end of every conversation |

### Handoff and evidence

- Every handoff names the branch and commit or worktree, changed files (including untracked), decisions, checks actually run with results, failures, and unverified items. A plan, report, converged loop, or green test is not proof of production readiness.
- Preserve existing work. Inspect staged changes before each commit; commit only converged blocks and process records, and never push, open a PR, or merge without the owner's instruction. After a PR is opened, review its latest head and checks. Never claim an unrun check passed, and never approve, merge, deploy, or trade without the owner's authorization.

## Authority and language

- `PROJECT.md` is the single source of truth for the v1 rebuild. Resolve conflicting code or documentation against it unless an explicit architectural decision changes it.
- Communicate with the project owner in Chinese, following "Talking to the owner" above. Owner-facing documents are written in Chinese and agent documents in English; keep clear English identifiers and established external formats. Do not translate other existing files solely to change their language.

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
- Legacy indexers and analysis code are not on `main`; they are preserved on `archive/upstream-main-2026-11-13`. Bring a piece into the v1 pipeline only through its migration PR, adapted to the adapter and writer interfaces.
- Keep documentation in the layout described by `docs/README.md`: long-term formal documents under `docs/`, architecture decision records under `docs/adr/`, and PR process records under `docs/pr<N>/` on the PR's working branch only. Add new formal documents to that index.
- Keep `main` clean: it receives only pipeline code, tests, and formal documents through reviewed pull requests. Process records (`PLAN.md`, `REVIEW_LOG.md`, `PROGRESS.md`, owner notes, superseded reports) stay on the PR's working branch, which is kept after merge as the audit trail; do not merge them into `main`. A concise post-merge summary report for a PR may live in `docs/reports/` (owner decision 2026-11-13).
- Keep the new pipeline under `src/`; do not use a version number as the source folder name. Put settings and validation in `src/config/`, contracts in `src/data_schema/`, data directory and writer code in `src/data_io/`, and venue implementations in `src/adapters/`.

## Owner notes

- Keep the project owner's private design notes in `docs/notes.md` on working branches only; they are not merged into `main`.
- Write them in concise Chinese as numbered entries. State the idea, pipeline, and called functions; mark proposed functions as unimplemented.
- Never include secrets, credentials, or personal data.
