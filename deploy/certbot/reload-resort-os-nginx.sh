#!/bin/sh
set -eu

container_name="resort-os-prod-nginx-1"

/usr/bin/docker container inspect "$container_name" >/dev/null
/usr/bin/docker exec "$container_name" nginx -t
/usr/bin/docker exec "$container_name" nginx -s reload
