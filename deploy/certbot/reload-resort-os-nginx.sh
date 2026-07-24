#!/bin/sh
set -eu

cd /opt/wegosharm/resort-os
/usr/bin/docker compose \
  -f docker-compose.prod.yml \
  -f docker-compose.prod.ip-tls.yml \
  exec -T nginx nginx -s reload
