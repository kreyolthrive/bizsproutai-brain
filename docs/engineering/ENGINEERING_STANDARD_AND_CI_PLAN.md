# BizSproutAI Engineering Standard
## Correctness, Style, and Design (CSD)

**Status:** Proposed implementation baseline  
**Applies to:** `bizsproutai-frontend`, `bizsproutai-backend`, and `bizsproutai-brain`  
**Version:** 1.0 — 2026-11-04

## 1. Purpose

This standard establishes a consistent, reviewable engineering system across BizSproutAI repositories. Every change must be evaluated across three dimensions:

1. **Correctness** — the software satisfies its requirements and behaves safely under expected and adverse conditions.
2. **Style** — the code is consistent, readable, and mechanically formatted.
3. **Design** — the implementation has appropriate boundaries, security properties, and maintainability.

A change is not ready merely because it compiles. It must satisfy the applicable CSD checks and have evidence proportionate to its risk.

## 2. Correctness

### Required practices
- Define expected behavior and acceptance criteria before implementation.
- Add or update tests with each behavior change; preserve existing tests.
- Test success paths, invalid input, authorization failures, boundary conditions, and relevant failure/retry paths.
- Use static types and compile/type checks appropriate to the language.
- Validate external input at trust boundaries. Never rely on client-side validation for server-side security.
- Keep database migrations deterministic, reviewable, and safe to apply in the documented order.
- Make tests isolated and repeatable; do not depend on production data or real user credentials.
- Use mocks or disposable local services for deterministic CI. Real-provider acceptance tests must be separately controlled for cost and credentials.

### Test layers
- **Unit:** pure functions and isolated components.
- **Contract/integration:** API, database, authorization, migration, and service boundaries.
- **End-to-end:** critical user journeys across the integrated application.
- **Security/regression:** authorization, input handling, secrets, concurrency, and previously fixed defects.

Every test must have a clear assertion. A test that only executes code without verifying behavior is a smoke check, not a behavioral test.

## 3. Style

- Use the repository's selected formatter and linter; do not introduce competing tools for the same purpose without an explicit decision.
- Commit formatter and linter configuration so local development and CI use the same rules.
- Use descriptive names, small cohesive functions, explicit return types where useful, and consistent error handling.
- Avoid unexplained abbreviations, dead code, unused imports, unchecked casts, and broad suppression directives.
- Keep functions and modules focused. Explain non-obvious security, concurrency, or compatibility decisions in comments.
- Keep dependencies minimal, pinned or lockfile-controlled, and reviewed before upgrades.
- Use the repository's package manager and frozen/locked install mode in CI.
- Apply a consistent editor baseline through `.editorconfig` where practical: UTF-8, LF endings, final newline, and language-appropriate indentation.

Language-specific tooling:
- **Frontend:** Prettier (or a documented existing formatter), ESLint, TypeScript, pnpm lockfile.
- **Backend:** Deno formatter, linter, type checker, tests, and committed dependency lock/import map.
- **Brain:** Ruff formatter/linter, Mypy where type coverage is practical, pytest, and pinned/locked Python dependencies.

## 4. Design

- Keep presentation, domain logic, infrastructure, and persistence responsibilities separated.
- Prefer explicit interfaces and narrow dependencies over hidden global state.
- Enforce authentication and authorization on the server and at data-access boundaries.
- Apply least privilege to runtime credentials, CI permissions, database roles, and service access.
- Use parameterized database access and transactions for multi-step state changes.
- Design mutations for safe retries where duplicate requests or network failures are possible.
- Define API contracts and handle backward compatibility deliberately.
- Avoid logging secrets, tokens, personal data, or sensitive request payloads.
- Include useful correlation/request identifiers in operational logs without exposing credentials.
- Document architectural exceptions and record the reason, owner, and review date.

## 5. Pull request standard

Every pull request must include:
- Problem and intended behavior.
- Summary of the implementation.
- Tests and checks run, including relevant limitations.
- Migration, configuration, dependency, or operational impact.
- Security/privacy impact where applicable.
- Rollback or recovery notes for risky changes.

Reviewers assess CSD independently:
- Correctness: is behavior demonstrated by tests and evidence?
- Style: does the change follow repository conventions?
- Design: are boundaries, security, and future maintenance sound?

Large refactors should be separated from behavior changes when practical. Do not mix unrelated changes.

## 6. CI and merge governance

- CI runs on pushes to all branches and on pull requests targeting protected branches.
- Mandatory workflows must not use path filters that can leave required checks absent.
- Each repository exposes one stable required aggregate status check named **`required-ci`**.
- The aggregate runs even when upstream jobs fail or are skipped and exits non-zero unless every mandatory job completed successfully.
- A skipped, cancelled, timed-out, or missing mandatory job is not a pass.
- Required checks are configured by exact check name and expected GitHub App/source where supported.
- Pull requests must be up to date with their base branch before merge.
- Require review approval and resolved conversations; prohibit force pushes and branch deletion.
- No administrator bypass unless separately approved and documented.
- Keep expensive, credentialed, or real-provider acceptance tests separate from per-push deterministic CI; schedule or manually dispatch them with explicit cost controls.
- Pin GitHub Actions to full commit SHAs and pin tool/runtime versions. Avoid floating `latest` tags.
- Use least-privilege workflow permissions, normally `contents: read`, and grant write scopes only to the job that needs them.
- Use explicit runner images (initial target: `ubuntu-24.04`) rather than floating `ubuntu-latest` where compatibility permits.

## 7. Environment reproducibility

- Local development and CI must use documented, compatible runtime and database versions.
- Docker Compose is the shared local orchestration mechanism, not a replacement for CI.
- Pin container image versions; add health checks, persistent development volumes, deterministic initialization, and documented reset behavior.
- Never place real secrets in Compose files, committed environment files, fixtures, or images. Commit only safe `.env.example` templates.
- Before selecting a PostgreSQL image, confirm the Supabase local stack's PostgreSQL major version and extensions. Do not run a second conflicting database beside the Supabase-managed stack.
- Use disposable databases and test fixtures. Do not connect local test workflows to production.

## 8. Exceptions and enforcement

An exception must state the affected repository/path, reason, risk, compensating control, owner, and expiry/review date. Security-critical controls may not be waived by an informal comment.

The standard is enforced through repository configuration and required CI checks, not by documentation alone. Branch protection/ruleset changes are a separate controlled operation and must be verified after configuration.

## 9. Adoption

Adopt incrementally. Preserve existing passing tests and workflows, introduce checks in a non-production branch, resolve baseline failures, and only then make the stable aggregate a required check. Do not weaken an existing check simply to obtain a green build.

## Repository implementation plan — Brain

**Repository:** `kreyolthrive/bizsproutai-brain`  
**Audited base:** `aabce06d18a773470fd2540fb5a24aaccc427608`

### Preserve and integrate existing work
- Main currently performs dependency installation, `py_compile`, and FastAPI import smoke test.
- The branch `security/launch-audit-20261030-review` already contains pytest tests, `requirements-dev.txt`, `requirements.lock.txt`, `pyproject.toml`, Ruff/Mypy configuration, and an expanded CI workflow.
- Review and integrate that existing work through a controlled PR; do not recreate it or merge it automatically.

### Implement on a feature branch
1. Review the existing security-audit branch against current main and reconcile drift before reusing it.
2. Make runtime and development dependency installation reproducible using the reviewed lock strategy; avoid unpinned `pip install -r requirements.txt`.
3. Run pytest as a required check, retaining the current syntax and FastAPI import smoke checks.
4. Add Ruff lint and format checks, and Mypy for the configured scope. Document gradual-typing exclusions explicitly.
5. Add dependency vulnerability auditing with a clear severity policy and exception process.
6. Add `required-ci` and make it fail if any required quality, test, type, or security job fails or is skipped.

### Candidate required check set
- Locked dependency install and dependency audit
- Ruff lint and format
- Mypy configured scope
- pytest
- Python compile and FastAPI import smoke test

### Acceptance criteria
- Existing test suite from the review branch is retained and run on the implementation branch.
- The workflow executes on pushes to all branches and PRs targeting protected branches.
- A deliberate pytest/lint/type failure makes `required-ci` fail.
- Dependency installation is reproducible from committed lock data.
- No application secrets or production services are required for unit CI.
