# Safe evolution rules

## Status

Accepted as the project change gate.

## Rules

- Every feature branch includes behavior and acceptance tests. Never mark a requirement complete from a plan or code comment alone.
- Keep user data account-scoped. New sensitive fields require a documented purpose, opt-in control, retention/deletion behavior, export behavior, and context exclusion by default.
- Every schema change ships with a forward migration, a tested downgrade where safe, and an update to export/deletion behavior.
- Do not silently rewrite prior goal values, evidence, progression, or scores. Corrections must remain explainable and auditable.
- Publish formulas and rule versions before adding a score or reward. Until the product owner approves the Life Score model, show measurements without a composite score.
- Keep AI, calendar, notification, and agent adapters off until provider, consent, failure handling, and credentials are reviewed. No automatic provider switching.
- No production deployment until authentication hardening, encrypted backup/restore, monitoring, and rollback gates have evidence.
- Merge focused branches into `main` only after local tests/lint/format checks and CI pass.

## Consequences

This policy prioritizes traceable, reversible changes and clearly labels deferred scope. CI verifies code-level checks; operational gates require separate manual evidence and are not implied by CI success.
