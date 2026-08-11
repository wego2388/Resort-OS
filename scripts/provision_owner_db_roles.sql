-- scripts/provision_owner_db_roles.sql
-- ═══════════════════════════════════════════════════════════════════════
-- Owner Intelligence Cockpit — restricted Postgres roles.
-- Decision 0004 §Isolation model item 5; security review 2026-08-11.
--
-- Run ONCE per environment (dev/staging/production) by a DB admin, after
-- `alembic upgrade head` has created all tables (the GRANTs below target
-- tables that must already exist). Not an alembic migration on purpose —
-- role provisioning is a per-environment deployment step, not schema
-- history that should replay identically everywhere (passwords differ
-- per environment and must never be committed).
--
-- Usage:
--   psql "$DATABASE_URL" \
--     -v owner_read_password='<generate a real secret>' \
--     -v owner_metadata_write_password='<generate a real secret>' \
--     -f scripts/provision_owner_db_roles.sql
--
-- After running, set in the environment (never commit the password):
--   OWNER_READ_DATABASE_URL=postgresql+psycopg://owner_read_role:<pw>@host:port/resort_os
--   OWNER_METADATA_WRITE_DATABASE_URL=postgresql+psycopg://owner_metadata_write_role:<pw>@host:port/resort_os
--
-- Re-running is safe (idempotent): CREATE ROLE IF NOT EXISTS guards, and
-- GRANT statements are naturally idempotent in Postgres.
-- ═══════════════════════════════════════════════════════════════════════

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'owner_read_role') THEN
    CREATE ROLE owner_read_role LOGIN PASSWORD :'owner_read_password';
  ELSE
    ALTER ROLE owner_read_role LOGIN PASSWORD :'owner_read_password';
  END IF;

  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'owner_metadata_write_role') THEN
    CREATE ROLE owner_metadata_write_role LOGIN PASSWORD :'owner_metadata_write_password';
  ELSE
    ALTER ROLE owner_metadata_write_role LOGIN PASSWORD :'owner_metadata_write_password';
  END IF;
END
$$;

-- ── OwnerReadSession — SELECT only, every business table ────────────────
-- Connection privilege + read access to the whole public schema. No
-- INSERT/UPDATE/DELETE grant anywhere — this is the actual enforcement
-- layer the acceptance test proves against.
GRANT CONNECT ON DATABASE resort_os TO owner_read_role;
GRANT USAGE ON SCHEMA public TO owner_read_role;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO owner_read_role;
-- Future tables created after this script runs inherit the same SELECT-only
-- grant automatically (matches this project's convention of tables being
-- added via alembic migrations over time).
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO owner_read_role;

-- Decision 0004 §Isolation model item 5: "Audit writer — reuses whichever
-- mechanism already writes AuditLog elsewhere in the codebase; if that
-- mechanism needs a dedicated grant, it is INSERT-only on audit_logs."
-- The owner router logs a deliberate report open/drill-down/export/
-- allocation-rule action through this same read session (never routine
-- polling — see owner/api/router.py's _log_owner_audit) and needs exactly
-- this one extra INSERT grant to do so, nothing broader.
GRANT INSERT ON audit_logs TO owner_read_role;
GRANT USAGE ON SEQUENCE audit_logs_id_seq TO owner_read_role;

-- ── OwnerMetadataWriteSession — INSERT/UPDATE/DELETE, owner tables only ──
-- No access whatsoever to any operational business table (folios, orders,
-- payments, bookings, ...) — only the two tables the owner module itself
-- owns. Also grants SELECT on the same two tables so services.py's
-- read-before-write checks (existing draft lookup, uniqueness check) work
-- on this session without needing a second connection.
GRANT CONNECT ON DATABASE resort_os TO owner_metadata_write_role;
GRANT USAGE ON SCHEMA public TO owner_metadata_write_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON owner_watchlist TO owner_metadata_write_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON owner_allocation_rules TO owner_metadata_write_role;
GRANT USAGE ON SEQUENCE owner_watchlist_id_seq TO owner_metadata_write_role;
GRANT USAGE ON SEQUENCE owner_allocation_rules_id_seq TO owner_metadata_write_role;
-- Same audit-writer grant as owner_read_role, for allocation-rule/watchlist
-- action logging done through this session — see note above.
GRANT INSERT ON audit_logs TO owner_metadata_write_role;
GRANT USAGE ON SEQUENCE audit_logs_id_seq TO owner_metadata_write_role;
