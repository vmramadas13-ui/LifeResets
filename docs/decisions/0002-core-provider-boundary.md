# THE CORE provider boundary

## Status

Accepted for the initial read-only implementation; selecting a hosted model provider remains open.

## Decision

THE CORE receives a bounded snapshot of account-owned goal, task, habit, and evidence records. Each record carries its source provenance. Questions, context count, and context character volume are bounded. The API has no tools, write capability, provider credentials, or cross-account access. Until a provider is selected and configured, a deterministic local fallback reports saved-context counts.

## Rationale

This allows the product to validate authentication, ownership, context selection, and fallback behavior without sending personal information to an external service. A provider adapter can be added behind the same narrow interface after provider, consent, retention, and cost controls are reviewed.

## Consequences

- `POST /api/v1/core/respond` is authenticated and CSRF-protected.
- Initial responses are summaries from the local fallback; they are not generated recommendations.
- Context includes user-created text and provenance, but excludes profiles, credentials, sessions, and audit records.
- The route is read-only. It cannot create tasks, change goals, or invoke tools.
- A hosted model, privacy disclosure, provider-specific retention settings, and provider outage behavior remain deployment decisions.
