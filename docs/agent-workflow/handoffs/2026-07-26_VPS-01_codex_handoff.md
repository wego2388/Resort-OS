# VPS-01 — Hostinger access and base hardening handoff

> Historical base-host checkpoint. Deployment/TLS/DNS state is superseded by
> `2026-07-26_VPS-02_ip_deployment_codex_handoff.md` and the user's later
> IP-only decision.

**Date:** 2026-07-26  
**Operator:** Codex  
**State:** base host ready; application not deployed  
**Commit / push:** none

## Confirmed inventory

- Hostinger VM ID: `1856853`
- IPv4: `191.218.161.133`
- Provider hostname: `srv1856853.hstgr.cloud`
- Local hostname: `resort-os-prod`
- Plan: KVM 2 — 2 vCPU, 8 GiB RAM, 100 GiB disk
- OS: Ubuntu 24.04 LTS
- Running kernel after update/reboot: `6.8.0-136-generic`
- Docker: `29.6.2`
- Docker Compose: `v5.3.1`
- Production containers/projects at handoff: none

## Hostinger control path

- Official `hostinger-api-mcp` `1.22.0` is installed with a user-local,
  checksum-verified Node `24.18.0`; the system Node installation was not
  replaced.
- OAuth PKCE completed through Hostinger and the credential file is mode
  `0600`. No access or refresh token is recorded in this handoff.
- Codex MCP entries exist for the Hostinger VPS and DNS servers.
- Hostinger account domain portfolio returned empty. In particular,
  `alkhaymaresort.com`, previously hard-coded in the marketing build, is not
  registered and is not treated as an owned production domain.

## SSH and host security

- The root password exposed in a supplied screenshot was rotated through the
  Hostinger API and never printed or persisted locally.
- A named operator `resortos` was created with `sudo` and `docker` access.
- Key-only access is configured through local alias `resort-os-vps`.
- Effective OpenSSH policy was verified:
  - `PermitRootLogin no`
  - `PasswordAuthentication no`
  - `KbdInteractiveAuthentication no`
  - `AuthenticationMethods publickey`
  - `AllowUsers resortos`
  - agent/TCP/X11 forwarding disabled
  - three authentication attempts and a 30-second login grace
- `fail2ban` SSH jail is active with no banned addresses at handoff.
- UFW is active, default-deny inbound, and permits only:
  - `22/tcp` rate-limited
  - `80/tcp`
  - `443/tcp`
  - `8081/tcp` temporary marketing HTTP UAT
  - `8443/tcp` temporary marketing TLS UAT

The policy source is versioned under `deploy/security/`. The SSH drop-in is
named `00-resort-os-hardening.conf` because Ubuntu's OpenSSH configuration is
first-value-wins and the cloud-init file otherwise precedes a `99-*` policy.

## Provider network firewall

- Hostinger firewall ID: `335259`
- Name: `resort-os-prod-ingress`
- Attached to VM `1856853`
- Accept rules: TCP `22`, `80`, `443`, `8081`, `8443`
- All other inbound provider traffic is dropped by default.

Ports `8081` and `8443` are temporary staging ports. Remove them from both
Hostinger Firewall and UFW after real-domain routing moves public and staff
traffic to `443`.

## Updates, TLS, and filesystem

- All OS packages are current; no reboot is pending.
- `unattended-upgrades` is enabled and active.
- Docker log rotation was already correctly configured at 10 MiB × 3 files.
- Certbot `5.7.0` was installed from the official snap.
- A publicly trusted Let's Encrypt certificate was issued for
  `srv1856853.hstgr.cloud`, valid through `2026-10-24`.
- Certbot's renewal timer is enabled and active. The repository also contains
  the container reload hook/service to install with the application release.
- Prepared, empty paths:
  - `/opt/resort-os`
  - `/opt/elkheima-marketing-website`
  - `/var/backups/resort-os`
  - `/var/www/certbot`

## Recovery and backup status

- A clean pre-application Hostinger snapshot was created:
  - snapshot ID `314805`
  - created `2026-07-26T18:43:33Z`
  - provider expiry `2026-07-27T18:43:33Z`
- Hostinger's backups API returned no retained backup points. The temporary
  snapshot is not an application backup strategy.
- After PostgreSQL is deployed, the required gate is:
  - daily custom-format `pg_dump`
  - tested restore into a disposable database
  - encrypted off-server copy
  - alerting on missed/failed backup

## Production configuration work completed locally

- Compose project name corrected to `resort-os-prod`.
- Production database password has no development fallback.
- The password is derived in memory from `DATABASE_URL` for Compose, avoiding
  two drifting secret copies.
- The archived `frontend/apps/public` service was removed.
- Marketing build context is portable and points to the sibling repository.
- Chat is disabled by default and cannot block the release.
- Unverified contact values default to empty.
- IP/staging Nginx routes now target `marketing_site`, not the removed
  `public_site`.
- Staging TLS configuration uses the real Hostinger hostname/certificate.
- `scripts/validate_prod_env.py` validates secrets and production policy
  without printing secret values.
- Local `.env.prod` is mode `0600`, uses HTTPS staging origins, enforces 2FA,
  and passed both the application settings validator and the new production
  preflight.

## Gates before application deployment

1. Finish CX-02C membership/bootstrap and CL-02B/CL-02C public privacy work.
2. Pass full backend, staff frontend, and marketing validation on the final
   shared source state.
3. Build both production images locally.
4. Produce an exact source/release manifest; no deployment should claim the
   current base Git SHA alone because the implementation is intentionally
   uncommitted.
5. Deploy to staging hostname, run migrations and first-branch/admin bootstrap.
6. Run smoke/UAT and a backup/restore drill before any real-domain cutover.
