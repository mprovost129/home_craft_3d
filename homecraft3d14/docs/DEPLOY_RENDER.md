# Home Craft 3D — Render Deployment Plan (Render-safe)

Last updated: 2026-02-10 (America/New_York)

This document is the production deployment playbook for deploying the current Home Craft 3D codebase to Render.

The project’s migration policy is **locked**:

- **Do not rewrite migrations** (production safety).
- Use additive migrations only.
- Treat production DB as the source of truth; use dry-runs and backups.

---

## 0) Preconditions

You should have:

- A clean local checkout of the same git commit you intend to deploy.
- A Render Web Service already created for the repo (or ready to create).
- A Render PostgreSQL instance provisioned.

---

## 1) Render service settings

### Build command

Use:

```
pip install -r requirements.txt
python manage.py collectstatic --noinput
```

### Start command

Typical Gunicorn example:

```
gunicorn config.wsgi:application --log-file -
```

If you already have a Render start command, keep it.

---

## 2) Environment variables (required)

Set these in Render (Dashboard → Environment):

- `DJANGO_SETTINGS_MODULE=config.settings.production`
- `SECRET_KEY=...`
- `DATABASE_URL=...` (from Render Postgres)
- `ALLOWED_HOSTS=homecraft3d.com,www.homecraft3d.com`
- `CSRF_TRUSTED_ORIGINS=https://homecraft3d.com,https://www.homecraft3d.com`
- `DEBUG=0`

### Stripe

- `STRIPE_SECRET_KEY=...`
- `STRIPE_WEBHOOK_SECRET=...`

### Email

- `DEFAULT_FROM_EMAIL=...`
- SMTP vars (whatever your stack uses in `config/settings/`)

### Storage

v1 uses local storage. Ensure `MEDIA_ROOT` and `STATIC_ROOT` are configured in production settings.

---

## 3) Render-safe migration strategy

### Why this matters

Render deploys are automated. A migration that fails can block deploy and/or leave a partial state.
This plan prioritizes:

- **Idempotency**
- **Non-destructive DB changes**
- **Rollback capability**

### Recommended approach

1) **Deploy code first** (without running migrations automatically).
2) Run migrations manually from Render Shell.
3) Verify.
4) Enable automated migrations only after first successful deploy.

#### Step A — First deploy without migrations

- Temporarily remove `python manage.py migrate` from any deploy hook.
- Deploy the web service.

#### Step B — Manual migrate

Open Render Shell → run:

```
python manage.py migrate --noinput
python manage.py check
```

If migrations fail:

- Do **not** retry blindly.
- Read the migration error, fix in a new commit, redeploy, then re-run migrate.

#### Step C — Collect static (already in build)

Confirm `collectstatic` succeeded in build logs.

---

## 4) Production verification (required)

Follow `docs/POST_DEPLOY_CHECKLIST.md`.

---

## 5) Backups and rollback

### DB backup

Before any risky change:

- Create a Render Postgres snapshot/backup.

### Rollback strategy

Rollback means:

- Deploying the last known-good commit.
- Restoring DB only if you ran destructive migrations (which you should not for v1).

---

## 6) First-live checklist summary

- [ ] Deploy web service code
- [ ] Run `migrate` manually
- [ ] Confirm site loads and core flows work
- [ ] Confirm Stripe keys/webhooks
- [ ] Confirm uploads (media) and downloads
- [ ] Confirm admin access
- [ ] Confirm seller onboarding and checkout gating
