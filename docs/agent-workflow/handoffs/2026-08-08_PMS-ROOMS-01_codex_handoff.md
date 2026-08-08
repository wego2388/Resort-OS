# PMS-ROOMS-01 — Real room inventory deployment handoff

**Date:** 2026-08-08 (Africa/Cairo)  
**Owner:** Mohamed  
**Implementer / final reviewer:** Codex  
**Status:** DEPLOYED / PRODUCTION_VERIFIED

## Outcome

The 52 synthetic PMS rooms, five demo room types, and four demo rate plans were
replaced atomically with Mohamed's 14 approved real units. All units are on the
ground floor. The physical mix is 8 chalets and 6 studios; the view mix is 7
without a sea view, 2 with a side sea view, and 5 with a sea view.

No price was added. `base_rate`, capacity, and amenities remain `NULL`, and no
rate plans exist. Booking creation fails closed until a real rate or applicable
rate-plan override is approved, so an unpriced room can never become a zero-value
financial booking.

The Timeshare admin account created by Mohamed was explicitly outside this task.
The importer touches only PMS room/rate tables plus one attributable audit row;
production verification confirmed the requested account remains present.

## Source and implementation

- Branch: `claude/CX-02C-frontend-auth-bootstrap`.
- Commit: `eda66178762f44ad4661ab98f9cca442ba491bec` (pushed; divergence `0/0`).
- Migration: `d0e1f2a3b4c5`, revising `c9d4e5f6a7b8`.
- Controlled importer: `backend/app/real_room_inventory.py`.
- Safety tests: `backend/tests/test_real_room_inventory.py`.
- Staff UI: Rooms, Reception, and Booking room selection show the translated
  physical type and view; floor `0` is rendered as ground floor.

## Safety and validation

- Production precondition immediately before apply:
  `bookings=0`, `booking_rooms=0`, `housekeeping_tasks=0`, inventory `52/5/4`.
- Importer defaults to dry-run, requires an exact branch, explicit actor and
  confirmation for apply, holds a PostgreSQL advisory transaction lock, refuses
  referenced rooms, commits atomically, writes an audit marker, and is idempotent.
- Full backend: 2569 tests collected, reached 100%, exit `0`, zero failures.
- PMS focused: 86/86 passed; importer acceptance: 4/4 passed.
- Staff frontend: 95/95; Arabic/English parity 6264 keys each; type-check passed.
- Local production builds for Staff and Owner passed; only the existing Staff
  bundle size advisory remained. The VPS rebuilt the affected Staff service.
- PostgreSQL 16 fresh full-chain upgrade, downgrade one revision, and re-upgrade
  passed. Nullable columns and the room-view constraint were verified.
- `scripts/agent-check.sh`, Alembic single-head, Compose config, and diff checks
  passed.

## Production deployment record

- Active release: `/opt/resort-os-current -> /opt/resort-os-releases/eda6617`.
- Alembic: `d0e1f2a3b4c5 (head)`.
- Verified DB backup:
  `/var/backups/resort-os/database/resort_os_20260808_193804.dump`, `628499`
  bytes, SHA-256
  `99d18514852543a26bb5b34f4e4289eacc5b140d84e825fe147a04f686ace65c`.
- Rollback image manifest:
  `/var/backups/resort-os/source-releases/eda6617-rollback-images-20260808_193823.txt`.
- Exact-source archive:
  `/var/backups/resort-os/source-releases/eda6617.tar.gz`, SHA-256
  `4746a8319612177320746895b2f1b208fcd2e1da41f9f1192f4dc3bccbfd25dd`.
- Production environment and Compose validation, backend import, Alembic
  preflight, migration, and importer dry-run all passed before apply.
- The dry-run projected `52/5/4 -> 14/2/0`; apply returned the same exact result.
  A second dry-run returned `already_applied=true` with `14/2/0 -> 14/2/0`.
- Final inventory: 14 available floor-0 rooms; Chalet 8 / Studio 6;
  none 7 / side sea 2 / sea 5; two fully unpriced room types; zero rate plans;
  one audit marker.
- Backend, Celery worker/beat, and Staff are healthy with `RestartCount=0`.
  PostgreSQL and Redis health/ready are `ok`; Nginx config is valid.
- Apex, `www`, Staff, and Owner returned HTTP 200. The public room-type contract
  returned both types with `base_rate=null`; anonymous protected PMS returned 401.
- `resort-os-healthcheck.service` succeeded. Changed-service scans found zero
  `ERROR`, `CRITICAL`, or `Traceback` matches.

## Rollback

Application-only rollback is not compatible with the deliberately unpriced
types. A full rollback must restore the verified pre-deploy database dump and
the recorded backend/worker/beat/Staff image tags together, then point the active
release link back to `1d77e7b`. Do not downgrade while `NULL` rate/capacity data
exists; the migration intentionally blocks that unsafe operation.

## Remaining product decisions

- Approve real prices before accepting bookings.
- Approve capacities and per-type amenities separately; the supplied screenshot
  was not generalized across all 14 units.
- Other demo master data remains outside this completed PMS-room slice.
