# Architecture

## Platform and Stack

- Windows
- Python 3.11
- Playwright for official web UI automation
- APScheduler for scheduled orchestration
- YAML configuration and environment-based secrets

## P1 Skeleton

`main.py` is currently a minimal entry point. It loads `config.yaml`, validates the minimum settings needed for startup, and prints `ready` when called with `--dry-run`. It deliberately contains no P2-P5 workflow logic.

## Planned Module Boundaries

- `config.yaml`: allowed sites, execution mode, schedule, AI provider, and disabled optional providers.
- `.env`: local secrets loaded at runtime; `.env.example` contains placeholders only.
- **P2:** ingestion and rights verification.
- **P3:** AI analysis and caption generation.
- **P4:** human approval and official publishing.
- **P5:** history, scheduling, and cleanup.

Dependencies should point inward: P3 depends on P2 outputs, P4 depends on P2/P3 outputs plus approval, and P5 observes and records every stage. Later modules should communicate through explicit data objects and recorded outcomes rather than shared mutable state.

## Data Flow

`Ingest -> Rights check -> AI analyse -> Caption -> Approve -> Publish -> History -> Cleanup`

Each stage should return a durable outcome. A failed rights check, missing approval, unverified provider, disallowed destination, or platform protection must stop the workflow.

## Provider Boundaries

Gemini is the selected active provider. Meta Model API is a disabled optional provider because official documentation verifies model inference, not content publishing. No Meta provider connection is implemented in P1.

## Security and Safety

- Restrict browser activity to the configured official sites.
- Do not bypass CAPTCHAs, bot detection, access controls, or rate limits.
- Do not remove watermarks or provenance markers.
- Require documented rights or permission.
- Read secrets only from environment variables and never log them.
- Preserve an auditable history for every publishing attempt.
