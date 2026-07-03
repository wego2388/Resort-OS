"""
app/core/kernel — Resort OS's own infrastructure kernel.

Auth, security, database session management, caching, error handling,
health checks, logging, Sentry, Celery, WhatsApp/email notifications, and
report generation — all owned directly by this project, no external
"shared kernel" package dependency. Nothing here talks to any other
WegoSharm project; changing it only ever affects resort-os.
"""
