# LifeResets product requirements knowledge base

## Source and use

Source: *LifeResets Product Requirements Document*, version 1.0, dated 11 November 2026, with *LifeResets — Product Discovery Q&A* as supplemental evidence of user choices. Both original documents remain in the owner's local Downloads folder. This repository is public, so the knowledge base omits private measurements, account details, and identifying information. See [the product discovery coverage audit](product-discovery-audit.md) for the Q&A crosswalk, conflict resolutions, and remaining gaps.

The source is a proposed specification, not evidence that a feature exists. It labels requirements as confirmed, inferred, or open; preserve those labels during implementation. “Must” identifies minimum safe/useful scope, not a shipped status. Finish the requested build sequence, then fill the traceability status and evidence below against the original source.

## Product principles and boundaries

- Keep user autonomy, editable user-owned records, transparent formulas, and recovery after interruptions.
- Keep sensitive health, finance, identity, reflection, and AI-memory data private, minimized, and separately controlled.
- Require explicit approval before external writes, destructive actions, financial actions, or agent execution.
- Do not diagnose, prescribe, promise outcomes, punish rest, shame lapses, or silently change history.
- Keep game language optional, accessibility usable, and progression rules visible.
- The discovery sets local-first self-hosting and a target provider portfolio; keep deployment details, credentials, provider scopes, canonical domain, and Life Score rules open until configured and reviewed.
- The blueprint began Mac-first; the user clarified on 11 November 2026 that iPhone is the primary use device, with Mac support. Large local models are not required.

## Product scope from the source

The source's functional catalog covers identity/profile, guided onboarding, eight configurable domains, goal/metric management, daily planning, habits/tasks/quests, long-range campaigns and reviews, progression and an explainable Life Score, THE CORE and provider controls, memory/knowledge capture, calendar, reminders, responsive PWA/offline support, career/learning, manual health and finance tracking, relationships/lifestyle, projects, guarded code/computer assistance, privacy/security, accessibility, operations, and release quality.

The described lifecycle includes a resumable seven-day onboarding, daily planning/action/reflection, a long-range campaign, weekly and monthly reviews, and recovery after missed time. Suggested domain names and user-specific targets are content in the private source and are intentionally omitted from public docs.

The MVP and release phases explicitly distinguish local/manual foundations from later integrations, offline sync, voice, wearables, richer knowledge retrieval, and sandboxed agents. A capability in the catalog or backlog is a requirement, not proof of implementation.

## Backlog traceability

Status values for final audit: **implemented**, **partial**, **deferred**, **blocked**, or **not started**. Add the code/test/manual-verification evidence after the full build, and cite the original PRD story acceptance criteria.

| Story | Requirement area | Final status | Evidence / gap |
| --- | --- | --- | --- |
| LR-001 | Profile and preferred address | Partial | Profile API stores display name, timezone, and preferences; the character UI can edit Hunter name and callsign, but general profile/timezone settings remain API-only. `tests/test_identity.py`, `tests/test_rpg.py`. |
| LR-002 | Resumable onboarding | Partial | Seven one-at-a-time prompts with resumable progress and optional skip. Answers require separate `awakening_storage` consent, are account-exportable, and can be deleted. The seven-day schedule is guidance rather than a gate; numeric baseline capture within Awakening remains. `tests/test_lifecycle.py`, `migrations/versions/cc4f0e04d4b0_guided_awakening_answers.py`. |
| LR-003 | Editable life domains | Partial | Users can rename and reorder the eight built-in areas and hide an area from new goals; existing goals remain visible. The fixed area codes cannot be renamed and custom subareas are not supported. `tests/test_domain_data.py`, `migrations/versions/7d1db751c6a3_domain_preferences_and_metric_history.py`. |
| LR-004 | Goal baselines, targets, and edits | Partial | Account-owned goals and unit-labelled metrics support baseline, target, current value, confidence, and append-only dated history. The latest dated measurement drives the current value, older entries remain in history, and measurements are included in export. `tests/test_domain_data.py`, `tests/test_insights.py`. |
| LR-005 | Daily capacity-aware plan | Partial | Account-scoped plans persist a chosen date, capacity, energy, task list, and minutes per action. Users can complete, defer, or drop actions. Recovery previews older unfinished actions and requires a choice; nothing carries forward automatically and missed days have no penalty. Calendar context and suggested time blocks are absent. `tests/test_daily_planning.py`. |
| LR-006 | Habits and task recovery | Partial | Daily plan actions support completion, deferral, removal, and a recorded due date at planning time; recurring habit execution, optional decision reasons, and a complete rescheduling event history are absent. `tests/test_daily_planning.py`, `tests/test_domain_data.py`. |
| LR-007 | Multi-step quests | Partial | Preview labels tasks/prompts as quests; no multi-step quest model or lifecycle. `src/liferesets/planning.py`. |
| LR-008 | Long-range campaign | Partial | Owned 90-calendar-day campaign create/list/status lifecycle; no weekly arcs, checkpoints, or retrospective. `tests/test_lifecycle.py`. |
| LR-009 | Calendar planning and approval | Partial | Authenticated read-only iCalendar export; no busy-time read or approval-based write. `tests/test_notifications.py`. |
| LR-010 | Weekly review | Partial | Weekly review drafts and consent-gated response storage; no guided review prompts or carry-forward planning. `tests/test_lifecycle.py`. |
| LR-011 | Monthly review | Partial | Monthly review drafts and consent-gated response storage; no guided review prompts or carry-forward planning. `tests/test_lifecycle.py`. |
| LR-012 | Reflection and recovery | Partial | Review responses require current `reflection_storage` consent. Missed-plan recovery offers earlier unfinished actions as optional suggestions without shame, automatic carry-forward, or a penalty; guided reflection prompts are absent. `tests/test_daily_planning.py`, `tests/test_lifecycle.py`. |
| LR-013 | XP event ledger | Partial | Versioned task-completion and correction entries are append-only through the API; re-opening a completed task reverses its XP and repeated requests do not duplicate awards. The database does not enforce immutability and verified-effort rules are absent. `tests/test_rpg.py`. |
| LR-014 | Ranks and attributes | Partial | E-to-SSS ranks, level progress, and draft thresholds are visible. Thresholds are starter values, and evidence-backed attributes are not modeled. `src/liferesets/rpg.py`, `tests/test_rpg.py`. |
| LR-015 | Skills, class, titles, achievements | Partial | User-defined skills support definitions, levels, confidence, and clearly self-reported evidence; first/ten-action achievements are derived. Hidden class evolution and earned titles are not implemented. `tests/test_rpg.py`. |
| LR-016 | Prestige and Chronicle | Partial | Chronicle shows account-scoped milestones and XP corrections. Prestige is intentionally absent until the reset/preservation rules are decided; existing history is not erased. `src/liferesets/rpg.py`. |
| LR-017 | Explainable Life Score | Deferred | No composite score implemented; formula and missing-data policy remain open by design. |
| LR-018 | Anti-gaming and fair recovery | Partial | No inactivity penalty; duplicate completion requests do not reward twice, reopening reverses points, and progression can be paused. Repetitive-action caps and independent evidence verification are absent. `tests/test_rpg.py`. |
| LR-019 | THE CORE coaching | Partial | Authenticated local deterministic summary with bounded context and provenance; no generated coaching or learning conversation. `tests/test_core.py`. |
| LR-020 | Provider routing and fallback | Partial | Adapter protocol and deterministic fallback exist. Discovery selected NVIDIA NIM, local Ollama, Gemini, and possible future OpenAI/Claude adapters; none is configured or routed yet. Credentials, per-provider consent/retention, cost limits, and failure behavior remain. `docs/decisions/0002-core-provider-boundary.md`. |
| LR-021 | CORE memory controls | Not started | No stored AI memory, review, edit, expiry, or deletion. |
| LR-022 | Knowledge capture and search | Not started | No notes, links, tags, or search. |
| LR-023 | AI task guardrails | Partial | One account-scoped local task action can be proposed, explicitly approved, rejected, and conditionally undone; it cannot access external services or run code. No model-generated reasoning or sandboxed execution. `tests/test_agent.py`. |
| LR-024 | Career roadmap | Partial | Generic career goals/tasks can be recorded; no roadmap or role competency model. |
| LR-025 | Learning paths | Partial | Generic learning goals/tasks can be recorded; no curriculum, skill evidence, or spaced review. |
| LR-026 | Fitness measurements | Partial | Generic metrics can represent dated measurements; no dedicated fitness log/trend or sensitive-data opt-in. |
| LR-027 | Smoking reduction/quit tracking | Not started | No dedicated private tracking or supportive lapse flow. |
| LR-028 | Sleep and consistency tracking | Not started | No dedicated sleep measures/trends or feature controls. |
| LR-029 | Financial position tracking | Partial | Generic unit-labelled metrics only; no separate asset/liability ledger, net calculation, or assumptions. |
| LR-030 | SaaS/project tracking | Partial | Generic goals/tasks/evidence only; no hypothesis, customer validation, release, or feedback model. |
| LR-031 | Relationships and lifestyle goals | Partial | Generic qualitative domain goals are supported; no dedicated commitments/review model. |
| LR-032 | Export and controlled deletion | Partial | Account export includes profile, consents, audit, domain, campaign, onboarding, and review records; hard deletion is password/CSRF/phrase protected and cascades lifecycle data. No deletion preview or backup-retention disclosure. `tests/test_identity.py`, `tests/test_domain_data.py`, `tests/test_lifecycle.py`. |
| LR-033 | Backup and restore | Partial | Passphrase-encrypted SQLite create/verify/restore CLI, authenticated decryption, integrity/FK checks, no-overwrite restore, file permissions, and linked-record tests. PostgreSQL, schedules, rotation, and isolated operational restore drills remain. `tests/test_backup.py`, `docs/operations.md`. |
| LR-034 | Authentication and security | Partial | Argon2id, revocable server-side sessions, CSRF, and account isolation are tested; MFA, password recovery, and deployed rate limiting are absent. |
| LR-035 | Notification preferences and quiet hours | Partial | In-app due-task inbox only; no categories, quiet hours, push, or email. `tests/test_notifications.py`. |
| LR-036 | Responsive and offline access | Partial | iPhone-first responsive PWA shell with safe-area spacing and mobile navigation; service worker caches static assets only. No offline edits, sync queue, conflict resolution, or production HTTPS setup for iPhone access yet. `tests/test_web.py`. |
| LR-037 | Accessibility and game-layer toggle | Partial | Display preferences persist in the browser; controls include visible focus, text status, reduced motion, terminology mode, 44px targets, and opt-in on-device dictation with keyboard fallback. Physical iPhone/screen-reader and 200% text checks remain. `tests/test_web.py`, `docs/design/visual-requirements.md`. |
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

## Decisions from discovery and remaining open points

Discovery decisions now recorded: iPhone is the primary client, with Mac support; the intended deployment is local-first/self-hosted, with private iPhone access through Tailscale; the intended provider portfolio is NVIDIA NIM, local Ollama, and Gemini, with possible future OpenAI/Claude adapters; THE CORE should use the user-selected, editable in-app address; and progression should eventually include Hunter ranks, skills, attributes, and a long campaign. These are product directions, not evidence that Tailscale, providers, or the larger progression system are configured. The running CORE remains deterministic and local until provider credentials, consent, retention, and failure handling are explicitly implemented.

Keep these items open: the Hunter's prominent name (Q41); exact rank review and demotion rules; Life Score formula and missing-data behavior; visual treatment across the Inkpop concept and cinematic System preference; which notifications are enabled and their quiet hours; calendar scopes and external write approvals; vault recovery and encryption architecture; and provider credentials, retention, and cost limits. Record any decision before implementing dependent behavior.

## Post-build verification snapshot

Audit updated against the original local PRD and Product Discovery Q&A on 12 November 2026. Of 40 stories, 34 are partial, 5 are not started, and 1 is deferred; none meets every acceptance criterion in full. The current feature branch has 66 passing local tests; Ruff lint and format, JavaScript syntax, and `git diff --check` pass. The preceding pushed commit passed GitHub CI; the guided Awakening change still needs its own hosted check after push. The PR review/merge is pending. The local preview was not rechecked on a physical iPhone or with a screen reader.

Known release blockers: PostgreSQL backup/restore, automated backup scheduling/rotation and restore monitoring, hosted hardening, production deployment, provider/calendar write integration, offline synchronization, user-approved Life Score, and a completed accessibility/recovery review. These limits are also recorded in `docs/operations.md` and `docs/decisions/0002-core-provider-boundary.md`.
