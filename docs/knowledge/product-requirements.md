# LifeResets product requirements knowledge base

## Source and use

Source: *LifeResets Product Requirements Document*, version 1.0, dated 11 November 2026. The complete source remains in the owner's local Downloads folder. This repository is public, so this knowledge-base copy omits private personal measurements and identifying details from the source. Use the local source document for the final, detailed requirements audit.

The source is a proposed specification, not evidence that a feature exists. It labels requirements as confirmed, inferred, or open; preserve those labels during implementation. “Must” identifies minimum safe/useful scope, not a shipped status. Finish the requested build sequence, then fill the traceability status and evidence below against the original source.

## Product principles and boundaries

- Keep user autonomy, editable user-owned records, transparent formulas, and recovery after interruptions.
- Keep sensitive health, finance, identity, reflection, and AI-memory data private, minimized, and separately controlled.
- Require explicit approval before external writes, destructive actions, financial actions, or agent execution.
- Do not diagnose, prescribe, promise outcomes, punish rest, shame lapses, or silently change history.
- Keep game language optional, accessibility usable, and progression rules visible.
- Keep provider, calendar, hosting, canonical domain, and measurement decisions open until explicitly resolved.
- Design the primary experience for a lightweight Mac-first setup; large local models are not required.

## Product scope from the source

The source's functional catalog covers identity/profile, guided onboarding, eight configurable domains, goal/metric management, daily planning, habits/tasks/quests, long-range campaigns and reviews, progression and an explainable Life Score, THE CORE and provider controls, memory/knowledge capture, calendar, reminders, responsive PWA/offline support, career/learning, manual health and finance tracking, relationships/lifestyle, projects, guarded code/computer assistance, privacy/security, accessibility, operations, and release quality.

The described lifecycle includes a resumable seven-day onboarding, daily planning/action/reflection, a long-range campaign, weekly and monthly reviews, and recovery after missed time. Suggested domain names and user-specific targets are content in the private source and are intentionally omitted from public docs.

The MVP and release phases explicitly distinguish local/manual foundations from later integrations, offline sync, voice, wearables, richer knowledge retrieval, and sandboxed agents. A capability in the catalog or backlog is a requirement, not proof of implementation.

## Backlog traceability

Status values for final audit: **implemented**, **partial**, **deferred**, **blocked**, or **not started**. Add the code/test/manual-verification evidence after the full build, and cite the original PRD story acceptance criteria.

| Story | Requirement area | Final status | Evidence / gap |
| --- | --- | --- | --- |
| LR-001 | Profile and preferred address | Partial | Profile API stores display name, timezone, and preferences; callsign/personal address flow is not in the UI. `tests/test_identity.py`. |
| LR-002 | Resumable onboarding | Partial | Seven-step resumable checklist, skip/complete/in-progress states, no answers collected. No guided prompts or baseline capture. `tests/test_lifecycle.py`. |
| LR-003 | Editable life domains | Partial | Eight-code catalog is fixed; no rename, reorder, hide, or subareas. `src/liferesets/domain_data.py`. |
| LR-004 | Goal baselines, targets, and edits | Partial | Owned goals and unit-labelled metrics support target/current/baseline and dates; confidence and revision history are absent. `tests/test_domain_data.py`. |
| LR-005 | Daily capacity-aware plan | Partial | Deterministic weekly preview of pending tasks and goal prompts; no capacity, energy, calendar context, or daily edits. `tests/test_planning.py`. |
| LR-006 | Habits and task recovery | Partial | Tasks and habit definitions support status, schedule, minimum action, and recovery text; recurrence execution and rescheduling history are absent. `tests/test_domain_data.py`. |
| LR-007 | Multi-step quests | Partial | Preview labels tasks/prompts as quests; no multi-step quest model or lifecycle. `src/liferesets/planning.py`. |
| LR-008 | Long-range campaign | Partial | Owned 90-calendar-day campaign create/list/status lifecycle; no weekly arcs, checkpoints, or retrospective. `tests/test_lifecycle.py`. |
| LR-009 | Calendar planning and approval | Partial | Authenticated read-only iCalendar export; no busy-time read or approval-based write. `tests/test_notifications.py`. |
| LR-010 | Weekly review | Partial | Weekly review drafts and consent-gated response storage; no guided review prompts or carry-forward planning. `tests/test_lifecycle.py`. |
| LR-011 | Monthly review | Partial | Monthly review drafts and consent-gated response storage; no guided review prompts or carry-forward planning. `tests/test_lifecycle.py`. |
| LR-012 | Reflection and recovery | Partial | Review responses require current `reflection_storage` consent; no missed-time recovery flow or supportive lapse prompts. `tests/test_lifecycle.py`. |
| LR-013 | XP event ledger | Partial | XP is derived from completed tasks using a visible rule; no append-only event ledger, correction events, or rule versioning. `tests/test_rpg.py`. |
| LR-014 | Ranks and attributes | Partial | Level only; ranks and attributes are not modeled. `src/liferesets/rpg.py`. |
| LR-015 | Skills, class, titles, achievements | Partial | Two derived task-count achievements; no skill tree, class, titles, or skill evidence. `tests/test_rpg.py`. |
| LR-016 | Prestige and Chronicle | Not started | No prestige or Chronicle. |
| LR-017 | Explainable Life Score | Deferred | No composite score implemented; formula and missing-data policy remain open by design. |
| LR-018 | Anti-gaming and fair recovery | Partial | No inactivity penalty in current derivation; caps, duplicate prevention, pause controls, and explicit recovery policy are absent. |
| LR-019 | THE CORE coaching | Partial | Authenticated local deterministic summary with bounded context and provenance; no generated coaching or learning conversation. `tests/test_core.py`. |
| LR-020 | Provider routing and fallback | Partial | Adapter protocol and deterministic fallback exist; no configured provider/router. Provider decision is open. |
| LR-021 | CORE memory controls | Not started | No stored AI memory, review, edit, expiry, or deletion. |
| LR-022 | Knowledge capture and search | Not started | No notes, links, tags, or search. |
| LR-023 | AI task guardrails | Partial | Authenticated goal-scoped proposal preview cannot execute, write, use tools, or access external services. No sandboxed execution. `tests/test_agent.py`. |
| LR-024 | Career roadmap | Partial | Generic career goals/tasks can be recorded; no roadmap or role competency model. |
| LR-025 | Learning paths | Partial | Generic learning goals/tasks can be recorded; no curriculum, skill evidence, or spaced review. |
| LR-026 | Fitness measurements | Partial | Generic metrics can represent dated measurements; no dedicated fitness log/trend or sensitive-data opt-in. |
| LR-027 | Smoking reduction/quit tracking | Not started | No dedicated private tracking or supportive lapse flow. |
| LR-028 | Sleep and consistency tracking | Not started | No dedicated sleep measures/trends or feature controls. |
| LR-029 | Financial position tracking | Partial | Generic unit-labelled metrics only; no separate asset/liability ledger, net calculation, or assumptions. |
| LR-030 | SaaS/project tracking | Partial | Generic goals/tasks/evidence only; no hypothesis, customer validation, release, or feedback model. |
| LR-031 | Relationships and lifestyle goals | Partial | Generic qualitative domain goals are supported; no dedicated commitments/review model. |
| LR-032 | Export and controlled deletion | Partial | Account export includes profile, consents, audit, domain, campaign, onboarding, and review records; hard deletion is password/CSRF/phrase protected and cascades lifecycle data. No deletion preview or backup-retention disclosure. `tests/test_identity.py`, `tests/test_domain_data.py`, `tests/test_lifecycle.py`. |
| LR-033 | Backup and restore | Not started | Runbook explicitly records encrypted backup and restore as a release blocker. |
| LR-034 | Authentication and security | Partial | Argon2id, revocable server-side sessions, CSRF, and account isolation are tested; MFA, password recovery, and deployed rate limiting are absent. |
| LR-035 | Notification preferences and quiet hours | Partial | In-app due-task inbox only; no categories, quiet hours, push, or email. `tests/test_notifications.py`. |
| LR-036 | Responsive and offline access | Partial | Responsive installable shell; service worker caches static assets only. No offline edits, sync queue, or conflict resolution. `tests/test_web.py`. |
| LR-037 | Accessibility and game-layer toggle | Partial | Semantic forms, labels, visible keyboard focus, and text status are present; no persistent theme/terminology/reduced-motion controls or manual accessibility audit. |
| LR-038 | System observability | Partial | Liveness/readiness, structured logging setup, and minimal audit events; no metrics dashboard, alerting, provider/backup health. |
| LR-039 | Testing, migration, and rollback | Partial | CI, migration upgrade/downgrade, and automated tests pass; no staging deployment/rollback rehearsal or restore-integrity test. |
| LR-040 | User-controlled sharing | Not started | No sharing feature or public links. |

## Release and acceptance gates

The source's definition of done requires repeatable acceptance evidence, useful empty/error states, private-data-safe logs, aligned data/migration/export/deletion behavior, accessibility basics, documented dependencies/consent/provider behavior, approval for consequential actions, and a release with rollback and verified backup/restore evidence.

Build sequence from the source:

1. Decisions, data classes, threat boundaries, consent, and restore strategy.
2. Foundation, identity, schema, audit, secure configuration, export, and backup skeleton.
3. Configurable domains, goals, measures, history, and manual entry.
4. Planning, tasks, habits, quests, reminders, recovery.
5. Campaign and recurring review ceremonies.
6. Versioned progression, explainable score, and Chronicle.
7. THE CORE, provider/memory consent, and knowledge tools.
8. Personal goal templates and sensitive manual measurements.
9. Responsive/accessibility/PWA/notifications.
10. Calendar integrations and guarded agent only after their security gates.

## Decisions to preserve as open until resolved

Provider meaning/configuration; canonical domain labels; single-user versus SaaS deployment; hosting; initial AI provider; Life Score formula; rank/XP mechanics; calendar provider/scopes; locale/timezone defaults; source/date of personal baselines; notification channels/quiet hours. Resolve any dependent choice before connecting an external service or publishing personal data.

## Post-build verification snapshot

Audit performed against the original local PRD after implementation stages 4–13 on 11 November 2026. This snapshot classifies all 40 backlog stories; it does not claim the full PRD is complete. Module-level acceptance implemented in this build is limited to the features described in the linked repository README and tests. Requirements marked partial/not started/deferred remain outstanding for a future scoped release. Latest local verification: 43 tests passed; Ruff lint and format checks passed; GitHub Actions passed for branch `feat/bounded-agent-operations` (run 42899108232). Lifecycle changes are currently in progress on `feat/campaign-reviews` and will receive a CI run before merge.

Known release blockers: no encrypted backup/restore, hosted hardening, production deployment, provider/calendar write integration, offline synchronization, user-approved Life Score, or completed accessibility/recovery review. These limits are also recorded in `docs/operations.md` and `docs/decisions/0002-core-provider-boundary.md`.
