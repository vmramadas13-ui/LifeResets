# THE CORE provider boundary

## Status

Accepted for the initial read-only implementation. The owner has selected a target provider portfolio; configuration and external calls remain deferred.

## Decision

THE CORE receives a bounded snapshot of account-owned goal, task, habit, and evidence records. Each record carries its source provenance. Questions, context count, and context character volume are bounded. The API has no tools, write capability, provider credentials, or cross-account access. The target portfolio is NVIDIA NIM, local Ollama, Gemini, and possible future OpenAI/Claude adapters, with task-aware privacy/cost routing. Until provider credentials, consent, retention, budget limits, and failure handling are configured, a deterministic local fallback reports saved-context counts and no external model is called.

## Rationale

This allows the product to validate authentication, ownership, context selection, and fallback behavior without sending personal information to an external service. Provider adapters may be added behind the same narrow interface only after provider-specific consent, retention, cost controls, routing behavior, fallback behavior, and account data boundaries are reviewed. The discovery preference does not authorize sending personal data to any provider.

## Consequences

- `POST /api/v1/core/respond` is authenticated and CSRF-protected.
- Initial responses are summaries from the local fallback; they are not generated recommendations.
- Context includes user-created text and provenance, but excludes profiles, credentials, sessions, and audit records.
- The route is read-only. It cannot create tasks, change goals, or invoke tools.
- Provider credentials, data categories sent to each provider, user-visible routing controls, provider-specific retention, rate/cost limits, and outage behavior remain implementation and deployment decisions.
