#!/usr/bin/env bash
# Retired: mutable checkout deployment conflicts with the immutable production
# release model. Kept only as a fail-closed compatibility entry point.
printf '%s\n' 'STOP: scripts/deploy.sh is retired. Use the immutable-release procedure in DEPLOYMENT.md.' >&2
exit 64
