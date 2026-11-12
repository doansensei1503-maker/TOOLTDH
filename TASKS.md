# Tasks

## P1 — Project Skeleton and Documentation

- [x] Create the nine required project files.
- [x] Define requirements, architecture, safety rules, and module boundaries.
- [x] Configure the allowed sites, approval mode, schedule, and AI provider.
- [x] Add placeholder-only environment configuration.
- [x] Implement a minimal dry-run entry point.
- [x] Verify Meta/Muse publishing capability against official documentation.
- [x] Validate `python main.py --dry-run` prints `ready`.

## P2 — Ingest and Rights Check

- [ ] Define source adapters and source configuration.
- [ ] Enforce the destination/site allowlist.
- [ ] Capture rights and permission evidence.
- [ ] Fail closed when rights cannot be established.

## P3 — AI Analysis and Captioning

- [ ] Implement the configured Gemini provider.
- [ ] Produce structured analysis output.
- [ ] Generate captions and metadata.
- [ ] Add provider error handling and retries.

## P4 — Approval and Publishing

- [ ] Implement the human approval gate.
- [ ] Implement only official publishing interfaces.
- [ ] Record publish attempts and outcomes.
- [ ] Never bypass CAPTCHAs or platform protections.

## P5 — History, Scheduling, and Cleanup

- [ ] Persist auditable job history.
- [ ] Add APScheduler scheduling.
- [ ] Add retry and failure handling.
- [ ] Clean temporary files and browser sessions safely.
