/**
 * parseApiTimestamp — safely parses a `datetime` string coming back from the
 * backend into a real UTC instant.
 *
 * ⚠️ Real bug found live (2026-07-05) via the restaurant KDS screens: every
 * backend timestamp column uses `TIMESTAMP` (no timezone) + `func.now()`
 * (Postgres server default, itself UTC), so the DB value is always a naive
 * UTC instant — but FastAPI/Pydantic serializes a naive `datetime` to JSON
 * *without* a "Z"/offset suffix (e.g. `"2026-07-05T15:12:27.504258"`).
 * Per the JS Date spec, an ISO date-*time* string with no timezone
 * designator is parsed as **local time**, not UTC. On a server/browser set
 * to Africa/Cairo (UTC+2/+3 — this resort's own timezone, see
 * `settings.TIMEZONE`), `new Date(apiTimestamp)` was therefore always ~2-3
 * hours ahead of the real elapsed time. Concretely: a ticket created seconds
 * ago in KitchenDisplayView/BarDisplayView showed "180 minutes elapsed" and
 * rendered as "urgent" (red, pulsing) the instant it appeared — defeating
 * the entire point of the urgency indicator for kitchen/bar staff.
 *
 * Fix: treat any timezone-less API timestamp as UTC explicitly by appending
 * "Z" before handing it to `Date`, instead of trusting the ambiguous
 * ECMAScript local-time fallback.
 */
export function parseApiTimestamp(value: string): Date {
  const hasTimezone = /Z$|[+-]\d{2}:?\d{2}$/.test(value)
  return new Date(hasTimezone ? value : `${value}Z`)
}
