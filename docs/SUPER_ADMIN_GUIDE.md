# Super Admin Guide — El Kheima Resort OS

> **Audience:** Resort owner and designated super-admin operators.
> **Version:** 2026-07 (Gate 2B3A / 2B3B complete)
> **Arabic version:** `docs/SUPER_ADMIN_GUIDE_AR.md`

---

## Table of Contents

1. [What Is super\_admin?](#1-what-is-super_admin)
2. [Login and Mandatory 2FA (TOTP)](#2-login-and-mandatory-2fa-totp)
3. [What super\_admin Can and Cannot Do](#3-what-super_admin-can-and-cannot-do)
4. [Step-Up Authentication](#4-step-up-authentication)
5. [Managing Users](#5-managing-users)
6. [Managing Permissions](#6-managing-permissions)
7. [Global Settings](#7-global-settings)
8. [Audit Log](#8-audit-log)
9. [Session Management](#9-session-management)
10. [Security Rules](#10-security-rules)
11. [Emergency Procedures](#11-emergency-procedures)

---

## 1. What Is super\_admin?

`super_admin` is the highest-privilege account in Resort OS (level 100, above
`admin` at 80). It sits outside the normal role hierarchy and cannot be
overridden by any explicit permission denial.

**There must always be at least two active super-admin accounts.** If you have
only one and it is locked or compromised, recovery requires direct server
access. The system enforces this — it will refuse to deactivate or demote the
last remaining active super-admin.

`super_admin` is a **named personal account, never a shared login.** Each
operator has their own credentials, their own TOTP device, and their own
recovery codes.

---

## 2. Login and Mandatory 2FA (TOTP)

### First-time setup

1. Receive your temporary credentials from the system administrator (email +
   temporary password + enrollment token).
2. Navigate to `https://[your-resort-domain]/login` and sign in.
3. You will be forced to change your password immediately (minimum 12
   characters).
4. After the password change you are redirected to `/2fa-setup`.
5. Scan the QR code with an authenticator app (Google Authenticator, Aegis,
   Authy, or any TOTP-compatible app).
6. **Write down the recovery codes and store them offline** — printed paper
   in a safe is the recommended method. You see them exactly once.
7. Enter the 6-digit code from your app to confirm enrollment.

### Every subsequent login

1. Enter email + password.
2. Enter the current 6-digit TOTP code.
3. The system rejects login without a valid TOTP. There is no production
   bypass.

### Lost authenticator — recovery

Use one of your saved recovery codes in place of the TOTP code at the login
screen. Each recovery code is single-use. After regaining access, immediately
go to **Account → Security** to regenerate recovery codes and re-enroll TOTP.

If all recovery codes are exhausted, see [Emergency Procedures](#11-emergency-procedures).

---

## 3. What super\_admin Can and Cannot Do

### ✅ Permitted

| Area | Actions |
|---|---|
| Users | Create staff accounts, change roles, activate/deactivate |
| Permissions | Grant or deny specific permissions to any non-super-admin user |
| Global settings | Read and update system-wide settings |
| Branch settings | Read branch settings; update with correct scope |
| Audit log | Read all audit events (read-only) |
| Sessions | View own sessions, revoke any session |
| Security | View security activity, manage own 2FA |

### ❌ Not permitted (by design)

| Action | Reason |
|---|---|
| Grant/deny permissions to a `super_admin` | Invariant #2 — super-admin authority cannot be restricted by a permission override |
| Demote or deactivate the last active `super_admin` | Invariant #4 — the system must always have at least one |
| Demote or deactivate your own account via the control panel | Invariant #3 — prevents accidental self-lockout |
| Edit posted orders, payments, or journals | Financial records are locked after posting |
| Erase or modify audit history | Audit log is append-only |
| Read stored passwords, tokens, or encryption keys | These are never exposed in the UI |
| Run SQL or shell commands from the UI | Not exposed |
| Write to settings not in the approved registry | Rejected by the settings validator |

---

## 4. Step-Up Authentication

Every sensitive mutation — creating accounts, changing roles, granting or
denying permissions, editing global settings — requires **step-up
authentication** in addition to your active login session.

### How it works

1. You initiate a sensitive action (e.g. change a user's role).
2. A confirmation dialog appears. You must provide:
   - **Current password.**
   - **Current TOTP code** (mandatory for `super_admin`).
   - **Reason** — plain text, minimum 3 characters, stored in the audit log.
3. The system issues a single-use step-up token valid for approximately
   5 minutes. The token is cryptographically bound to the exact operation you
   declared — it cannot be reused for a different action.
4. The token is consumed atomically at the moment the mutation executes.

### Why a reason is required

The reason is recorded alongside the actor, target, timestamp, IP address,
and request ID. Every sensitive action produces an attributable audit event
with no exceptions.

### Token expiry

If more than ~5 minutes pass between confirming step-up and submitting the
action, the token expires. The operation is rejected with `STEP_UP_REQUIRED`.
Re-confirm your identity to continue.

---

## 5. Managing Users

Go to **Admin → 🛡️ Super Admin Panel → Users tab** or **Admin → 👤 Staff
Accounts**.

### Creating a new staff account

1. Fill in full name, email, role, and preferred language. Phone and HR
   employee link are optional.
2. Click **Create Account**.
3. Complete step-up (password + TOTP + reason).
4. A credentials panel appears showing:
   - **Temporary password** — the employee must change it on first login.
   - **Enrollment token** — required to complete TOTP setup on first login.
5. **Copy and send these credentials securely to the employee. They are shown
   exactly once.** After closing the panel they cannot be recovered from the
   UI.

### Available roles (highest → lowest)

| Role | Level | Typical use |
|---|---|---|
| `super_admin` | 100 | Resort owner / IT head — assigned only via bootstrap script |
| `admin` | 80 | Resort manager, full back-office |
| `accountant` | 70 | Finance team — mandatory 2FA |
| `hr_manager` | 70 | HR module |
| `manager` | 60 | Branch / outlet manager |
| `supervisor` | 50 | Floor supervisor |
| `receptionist` | 40 | Front desk |
| `cashier` | 40 | POS / shift cashier |
| `waiter` | 30 | Floor service, order entry |
| `chef` / `kitchen` | 30 | Kitchen display |
| `employee` | 20 | Self-service portal only |

### Changing a role

1. Find the user, click **Edit**.
2. Select the new role and confirm.
3. Complete step-up. All existing sessions for that user are revoked
   immediately — they must log in again.

### Activating / deactivating

Click **Activate** or **Deactivate**. Requires step-up. Deactivating a user
immediately invalidates all their active sessions and tokens.

---

## 6. Managing Permissions

Go to **Admin → 🛡️ Super Admin Panel → Permissions tab** or **Admin → 🔐
Permissions**.

### The three states

| State | Meaning |
|---|---|
| **Default** | Access follows the user's role level |
| **Granted** | Explicitly allowed, even if the role would not normally allow it |
| **Denied** | Explicitly blocked, even if the role would normally allow it |

### Rules

- You cannot set any override on a `super_admin` account — the server rejects
  it.
- Removing an override (resetting to Default) also requires step-up with a
  reason.
- Overrides are system-wide by default unless you specify a branch scope.
- You can only grant/deny permissions that exist in the server-side catalog.

### Workflow

1. Select an employee from the left-hand list.
2. The right panel shows all permissions grouped by module, with the current
   state highlighted.
3. Click **Grant**, **Default**, or **Deny** on any row.
4. Complete step-up.

---

## 7. Global Settings

Go to **Admin → 🛡️ Super Admin Panel → Settings tab**.

> ⚠️ Global settings affect the entire system. Change them only when you
> understand the effect. Some take effect immediately; others require a
> service restart.

### Editing a setting

1. Click **Edit** on the row.
2. Enter the new value.
3. Complete step-up (password + TOTP + reason).

### What cannot be changed here

- Keys not in the approved server-side registry are rejected.
- Read-only markers (database version, migration state) cannot be modified.
- Secret values (API keys, encryption keys, third-party credentials) are
  managed via environment variables on the server — they are never shown in
  the UI.

---

## 8. Audit Log

Go to **Admin → 🛡️ Super Admin Panel → Audit tab**.

The audit log is **read-only and append-only**. Every sensitive action is
recorded automatically. You cannot delete, modify, or suppress entries.

Each entry contains:

| Field | Description |
|---|---|
| Action | What happened (`user.role_changed`, `permission.granted`, etc.) |
| Entity | What was affected (type + ID) |
| Actor | Who performed the action (user ID) |
| Time | UTC timestamp |
| Details | Reason, step-up reference, assurance method, IP address |

Use the **Action** and **Entity** filters to narrow results. 50 entries per
page.

---

## 9. Session Management

Go to **Account → Sessions** (`/account/sessions`).

You can see all your active sessions (each device or browser where you are
logged in), including approximate start time, last activity, device, and IP.

- **Revoke a single session:** click Revoke next to it. Requires step-up.
- **Revoke all other sessions:** terminates every session except the current
  one. Requires step-up.

Revoking sessions does not affect audit history.

---

## 10. Security Rules

1. **Never share credentials or your TOTP device.** Each account must remain
   exclusively personal.
2. **Store recovery codes offline** — printed paper in a physical safe, not a
   file on the same computer.
3. **Always write a meaningful reason** when prompted. Vague entries ("test",
   "ok") make the audit log useless for incident review.
4. **Log out on shared or untrusted devices** after every session.
5. **Review your active sessions regularly** and revoke any you do not
   recognize.
6. **Maintain at least two active super-admin accounts at all times.** Do not
   deactivate one until a second is enrolled and confirmed working.
7. **Do not grant `super_admin` to operational staff.** Use explicit permission
   grants for exactly the access they need.
8. **Treat temporary credentials as single-use.** If they were shared by
   insecure means, deactivate that account and create a new one.

---

## 11. Emergency Procedures

### Lost authenticator, recovery codes available

Use a recovery code in the TOTP field at login. After accessing the account,
immediately regenerate recovery codes and re-enroll TOTP from **Account →
Security**.

### Lost authenticator, no recovery codes

Contact the second super-admin operator. They should:
1. Create a new account for you via **Staff Accounts → Create**.
2. Deactivate the locked account.

If there is no second super-admin available, recovery requires direct server
access (SSH to the VPS):

```bash
cd /opt/wegosharm/resort-os
docker compose -f docker-compose.prod.yml exec backend \
  python -m app.admin_bootstrap
```

The script creates a new super-admin account with a temporary password and
enrollment token. Use these to log in, complete TOTP setup, then deactivate
the previously locked account.

### Suspected account compromise

1. From a second super-admin account: revoke all sessions for the compromised
   account (Users tab → find user → Deactivate).
2. Review the audit log for the period in question.
3. Create a new account for the affected person only after the incident is
   understood.
4. If system-wide credentials may be exposed, rotate `SECRET_KEY` in
   `backend/.env` on the VPS and restart the backend service — this
   immediately invalidates all sessions for all users system-wide:

```bash
# On the VPS — edit .env first, then:
docker compose -f docker-compose.prod.yml restart backend celery_worker celery_beat
```

---

*Security model reference: `docs/decisions/0003-super-admin-control-plane.md`,
`docs/audits/gate-2a-super-admin-invariants.md`,
`docs/audits/gate-2b3a-step-up-control-plane.md`,
`docs/audits/gate-2b3b-auth-audit-session-defense.md`.*
