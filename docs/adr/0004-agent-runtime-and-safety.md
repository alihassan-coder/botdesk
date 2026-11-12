# 0004: Agent runtime, approvals and safety rules

- Status: accepted
- Date: 2026-11-12
- Based on: [architecture review](../architecture/review-2026-11-12.md) (findings 1, 3, 6, 7) and [agents-and-plugins.md](../architecture/agents-and-plugins.md)

## Context

Bots act inside people's email and other apps. Two things must never happen: a risky action that runs without the approval it needed, and an action that runs twice (two identical emails sent). The review found that the first design could do the second: LangGraph re-runs a step from its first line when a paused run resumes. It also found holes in our prompt-injection defences.

## Decisions

1. **A run is a LangGraph graph** with a Postgres checkpointer. The tool pipeline is split into separate graph nodes (decide → wait for approval → execute → record). Side effects happen only in the execute node, after the decision is saved.
2. **Every tool call is recorded** in `tool_executions` (started / succeeded / failed), keyed by run and step. If a run resumes and finds a call marked *started* but not *succeeded*, it does **not** retry blindly. It moves the run to **`needs_attention`** and asks a person, unless the tool is declared `idempotent`.
3. **Approving is atomic.** The decision is a single conditional `UPDATE` (only a *pending* approval can be decided), so a double-clicked Approve resumes the run once.
4. **Security levels: three, plus seven risk classes.**
   - Levels: **Read only**, **Ask before acting** (default) and **Autonomous within limits**.
   - Risk classes: `read`, `write-internal`, **`write-external`** (new: reversible changes in other apps, like drafts, labels and calendar holds), `external-send`, `spend`, `destructive` and `credential`.

   | Level | read | write-internal | write-external | external-send | spend | destructive | credential |
   |---|---|---|---|---|---|---|---|
   | Read only | auto | auto | deny | deny | deny | deny | deny |
   | Ask before acting | auto | auto | ask | ask | ask | ask | ask |
   | Autonomous within limits | auto | auto | auto | auto | ask | ask | ask |

   - **Fixed rules:** `credential` is never automatic, and in v1 neither is `destructive`.
   - **Effective level:** the strictest of the organization ceiling, the bot's level and the routine's level.
5. **Taint is run-level and strict.** Once a run has read outside text (an email body, a web page, an MCP result), every later call above `write-internal` needs approval, even for *Autonomous* bots. The UI says so plainly. The optional auto-review model may **never** approve a tainted call; only a person can.
6. **Concurrency:** one run at a time **per chat** (keeps order), at most **2 running per bot**, and a cap per organization. Every run has limits: steps (default 25), time, tokens and cost.
7. **One tool call at a time per step** in v1. Parallel calls for `read`-only tools may come later as an optimisation.
8. **Paused runs meet new code.** Graph changes must keep old checkpoints loadable (add nodes, don't rename or remove them while runs are paused). Old checkpoints are cleaned up by a scheduled job.

## Consequences

- New tables: `tool_executions`, `run_events`; new run state `needs_attention`.
- The web app's risk-class list (`apps/web/src/data/types.ts`) and `POLICY` table gain `write-external`. GLOSSARY.md is updated to three levels.
- Some actions will ask more often (strict taint). That's deliberate; saved rules ("always allow labelling from this bot") are how users reduce approval fatigue, and those rules can never allow `credential` or tainted `external-send`.
