#!/usr/bin/env bash
# Retired: the reviewed domain/TLS cutover is complete. Production now uses
# docker-compose.prod.domain.yml through the immutable release runbook.
printf '%s\n' 'STOP: domain cutover is already complete. Use DEPLOYMENT.md for production operations.' >&2
exit 64
