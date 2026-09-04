#!/usr/bin/env bash
# Retired: copying an uncommitted worktree into production breaks release
# provenance and rollback. Kept only as a fail-closed compatibility entry point.
printf '%s\n' 'STOP: scripts/sync-deploy.sh is retired. Use the immutable-release procedure in DEPLOYMENT.md.' >&2
exit 64
