# Handoff DB-01 — Codex

- **Implementer:** Codex
- **Date:** 2026-07-26
- **Scope:** PostgreSQL/Alembic fresh-chain blocker at `e3f5a7b9c2d4`
- **Status:** implementation and PostgreSQL verification complete
- **Commit / push / deploy:** none

## Outcome

The Alembic chain now upgrades a completely empty PostgreSQL database through
`e3f5a7b9c2d4` and reaches the current repository head
`b7e2c4a91f60`.

The fix also preserves the original cutover behavior on the old deployment
schema that contained the legacy `split_id`, FK, split table, payment table,
and their indexes.

## Root cause

`e3f5a7b9c2d4` was authored from a deployment database containing schema drift
that is absent from the revision history. It unconditionally dropped:

- `dining_order_items.split_id`
- `fk_dining_order_items_split_id`
- `dining_order_splits` and its order index
- `dining_order_payments` and its order/split indexes

No earlier migration creates any of those objects. A catalog inspection of a
disposable PostgreSQL database at predecessor revision `d2e4f6a8b1c3`
confirmed all of them are absent, while every other legacy table dropped by
the revision is present.

The first unconditional `DROP CONSTRAINT` therefore stopped every fresh
install before later revisions could run.

## Design decision

A new forward migration cannot repair this failure: Alembic must successfully
execute `e3f5a7b9c2d4` before it can reach any later corrective revision.
Special-casing the Alembic runner would make an unrelated global mechanism
responsible for one historical schema drift.

The smallest safe option was therefore to make only the drift-derived
operations in the historical revision catalog-aware:

- exact schema (`current_schema()`)
- exact table/column/constraint/index name
- exact PostgreSQL object kind
- exact FK constraint type
- exact index-to-table ownership

Expected history-managed legacy tables remain unconditional drops. Unexpected
dependencies or other schema mismatches still fail loudly; the migration does
not use `CASCADE` and does not broadly suppress database errors.

Databases already stamped at or beyond `e3f5a7b9c2d4` are unaffected because
Alembic never re-executes an applied revision. A second `upgrade head` was
verified as a no-op on the disposable database.

## Files

- `backend/alembic/versions/e3f5a7b9c2d4_drop_legacy_dining_cafe_restaurant_tables.py`
- `backend/tests/test_db01_alembic_chain.py`

No chat, marketing, CX-02C application file, Alembic environment file, or
current-head migration was changed.

## Regression coverage

`tests/test_db01_alembic_chain.py` adds:

1. A fresh empty-PostgreSQL chain test through current `head`, with schema
   assertions for the retained unified dining tables and deleted legacy
   tables/column.
2. A deployment-drift simulation at `d2e4f6a8b1c3`, including the exact
   legacy FK, tables, and indexes, followed by the cutover and then current
   `head`.
3. An actual Alembic downgrade attempt from `e3f5a7b9c2d4` to its predecessor.
   It must raise the documented `NotImplementedError`, and the transaction
   must leave `alembic_version` at `e3f5a7b9c2d4`.
4. A direct regression asserting that the destructive downgrade remains
   explicitly unsupported and instructs restoration from backup.

The PostgreSQL tests are opt-in, create randomly named disposable databases,
terminate only their own sessions, and remove those databases in fixture
cleanup.

## Verification

```text
DB01_MIGRATION_TEST_ADMIN_URL=<local-admin-dsn> \
  pytest tests/test_db01_alembic_chain.py -vv
→ 3 passed

pytest tests/test_db01_alembic_chain.py -q
→ 1 passed, 2 skipped (expected without the explicit PostgreSQL admin DSN)

python -m py_compile \
  alembic/versions/e3f5a7b9c2d4_drop_legacy_dining_cafe_restaurant_tables.py \
  tests/test_db01_alembic_chain.py
→ pass

alembic heads
→ b7e2c4a91f60 (head)

git diff --check -- <tracked DB-01 migration>
→ pass

new-file whitespace scan for the DB-01 test and handoff
→ pass

PostgreSQL cleanup query:
→ db01_temp_databases []
```

The local environment does not contain a `ruff` executable, so no Ruff result
is claimed.

## Downgrade and recovery note

The cutover deletes legacy data only after the unified dining copy. Its
pre-existing downgrade deliberately raises `NotImplementedError`; reconstructing
deleted business data from empty table definitions would be dishonest and
unsafe. Recovery below this revision requires a tested database backup.

No production/local shared database was migrated, stamped, downgraded, or
otherwise mutated during DB-01. Only isolated disposable databases were used.
