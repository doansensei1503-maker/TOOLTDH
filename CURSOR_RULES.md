# Cursor Rules

## Scope

- Follow the active phase in `TASKS.md`; do not implement later phases without instruction.
- Make the smallest change that satisfies the current task.
- Preserve existing architecture, behavior, and naming conventions.
- Inspect only files directly needed for the requested work.

## Safety

- Use only official web interfaces.
- Restrict automation to `allowed_sites` in `config.yaml`.
- Never bypass CAPTCHAs, bot detection, access controls, or rate limits.
- Never remove watermarks or provenance markers to hide origin.
- Process and publish only content with rights or permission.
- Never hard-code or commit passwords, API keys, cookies, or session tokens.
- Read secrets from environment variables; never print them.
- Fail closed when rights, permission, approval, provider, or destination state is unclear.
- Do not assume undocumented APIs are usable; verify against official documentation and record the result.

## Quality

- Keep configuration in `config.yaml` and secret placeholders in `.env.example`.
- Prefer clear, testable functions and explicit failures.
- Update `PROJECT_MASTER.md` and `PROGRESS.md` when module status or verification status changes.
- Record blockers honestly and do not claim unimplemented behavior.
- Stop when the requested phase is complete.
