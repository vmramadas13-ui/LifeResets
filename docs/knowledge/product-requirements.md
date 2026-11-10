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
| LR-001 | Profile and preferred address | TBD | |
| LR-002 | Resumable onboarding | TBD | |
| LR-003 | Editable life domains | TBD | |
| LR-004 | Goal baselines, targets, and edits | TBD | |
| LR-005 | Daily capacity-aware plan | TBD | |
| LR-006 | Habits and task recovery | TBD | |
| LR-007 | Multi-step quests | TBD | |
| LR-008 | Long-range campaign | TBD | |
| LR-009 | Calendar planning and approval | TBD | |
| LR-010 | Weekly review | TBD | |
| LR-011 | Monthly review | TBD | |
| LR-012 | Reflection and recovery | TBD | |
| LR-013 | XP event ledger | TBD | |
| LR-014 | Ranks and attributes | TBD | |
| LR-015 | Skills, class, titles, achievements | TBD | |
| LR-016 | Prestige and Chronicle | TBD | |
| LR-017 | Explainable Life Score | TBD | |
| LR-018 | Anti-gaming and fair recovery | TBD | |
| LR-019 | THE CORE coaching | TBD | |
| LR-020 | Provider routing and fallback | TBD | |
| LR-021 | CORE memory controls | TBD | |
| LR-022 | Knowledge capture and search | TBD | |
| LR-023 | AI task guardrails | TBD | |
| LR-024 | Career roadmap | TBD | |
| LR-025 | Learning paths | TBD | |
| LR-026 | Fitness measurements | TBD | |
| LR-027 | Smoking reduction/quit tracking | TBD | |
| LR-028 | Sleep and consistency tracking | TBD | |
| LR-029 | Financial position tracking | TBD | |
| LR-030 | SaaS/project tracking | TBD | |
| LR-031 | Relationships and lifestyle goals | TBD | |
| LR-032 | Export and controlled deletion | TBD | |
| LR-033 | Backup and restore | TBD | |
| LR-034 | Authentication and security | TBD | |
| LR-035 | Notification preferences and quiet hours | TBD | |
| LR-036 | Responsive and offline access | TBD | |
| LR-037 | Accessibility and game-layer toggle | TBD | |
| LR-038 | System observability | TBD | |
| LR-039 | Testing, migration, and rollback | TBD | |
| LR-040 | User-controlled sharing | TBD | |

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
