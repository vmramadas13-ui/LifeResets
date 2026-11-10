# Local identity for the first private API

Date: 2026-11-11
Status: Accepted for the local identity foundation
Approval: The user selected local email/password with hashed passwords and revocable server-side sessions.

## Problem

Module 3 needs an account identity and authorization boundary before profile, consent, export, and deletion data can be safely exposed. No identity provider is configured, and the blueprint leaves the provider choice open.

## Decision

Use local email/password credentials for this API foundation. Create accounts only through an interactive local CLI command. Store Argon2id password hashes and opaque, random session-token hashes in the database. Use HttpOnly, SameSite Strict cookies and a session-bound CSRF token for state-changing requests. A new login revokes the account's previous sessions.

## Alternatives considered

- Integrate a managed identity provider now. This avoids maintaining password credentials but requires a provider selection, account, configuration, and deployment decisions that are not part of the current local setup.
- Add an unauthenticated registration endpoint. Rejected because this is a private personal application and an open registration route would expose account creation.

## Risks and limits

MFA, password recovery, and deployed login rate limiting are not implemented. The development session cookie is not Secure because local development uses HTTP loopback. Local SQLite data is not application-encrypted at rest. Keep the API bound to localhost until the deployment security review addresses these items, TLS, secret handling, backups, and the database strategy.

## Data and migration

The identity migration adds users, profiles, server-side sessions, consent records, and minimal audit events. A future provider can map its stable subject identifier to the existing user ID; session rows should be invalidated during provider migration. The migration and rollback were tested against a temporary SQLite database. The existing default local database was not changed during migration generation.

## Rollback

Before accounts contain user data, revert the code and downgrade the migration to the previous Alembic revision. Once user data exists, first export and back it up; dropping these tables requires a separate approved migration plan.

## Affected acceptance gates

Module 3: unauthorized access fails; consent, profile, audit, export, and deletion are account-scoped; deletion requires reauthentication and explicit confirmation; secrets are excluded from API responses and logs.
