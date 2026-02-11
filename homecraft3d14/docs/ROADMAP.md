# Home Craft 3D — ROADMAP

Last updated: 2026-02-10 (America/New_York)

This roadmap is a living doc: completed items stay visible, and the next
phase is always explicit.

---

## Recently completed (2026-02-09)

### Trust & access
✅ Email verification gating across registered-only features
✅ Email → in-app notification parity (user-facing emails create Notifications)

### Marketplace mechanics
✅ Favorites & Wishlist split (single combined UX page)
✅ Free digital listing cap (SiteConfig-managed) enforced server-side
✅ Seller replies to product reviews (one reply per review in v1)

### Seller listings stability
✅ Template crash fixed: no template access to private (_underscore) attributes
✅ Seller Listings publish checklist exposed as `p.publish_ok` / `p.publish_missing`

### Digital download metrics (bundle-level)
✅ Bundle-level download counter: `Product.download_count`
✅ Paid + free downloads increment:
  - `DigitalAsset.download_count`
  - `Product.download_count` (bundle-level)
✅ Unique downloaders tracking:
  - New `ProductDownloadEvent` model (user + guest session)
  - Seller Listings shows **unique / total** for FILE products
✅ Seller Listings metrics polish: unique downloaders excludes blank guest sessions; physical listings show NET units sold.

## Recently completed (2026-02-10)

### Seller Listings stability
✅ Fixed Seller Listings template/context mismatch (template iterates Product instances directly).
✅ Digital listings show bundle-level total downloads via `Product.download_count`.

### Deployment readiness
✅ Added Render deployment playbook (`docs/DEPLOY_RENDER.md`).
✅ Added post-deploy verification checklist (`docs/POST_DEPLOY_CHECKLIST.md`).

---

## Phase 1 — Storefront credibility (DONE)
✅ Add-to-cart buttons on home cards with Stripe readiness gating (`p.can_buy`)
✅ Trending computation on home (manual override + computed fill)
✅ Trending score includes purchases + reviews + engagement events
✅ Rating on cards across home + browse + “more like this” using annotations
✅ Browse sort controls (New / Trending / Top Rated)
✅ Top Rated threshold with fallback + warning banner

## Phase 2 — Engagement signals v1 (DONE)
✅ `ProductEngagementEvent` (VIEW, ADD_TO_CART, CLICK)
✅ Throttled VIEW logging on product detail
✅ Best-effort ADD_TO_CART logging on cart add

## Phase 3 — Badge membership rules (DONE)
- [x] Ensure browse “🔥 Trending” badge applies only to a meaningful subset:
  - badge if in computed Top N AND `trending_score > 0` (with manual override)
- [x] Keep badge rule consistent between home + browse

## Phase 4 — Seller analytics (DONE)
- [x] Seller analytics summary page:
  - views / clicks / add-to-cart
  - net units sold
  - downloads (unique / total)
- [x] Time-window filters (7/30/90 days)

## Phase 5 — Messaging & moderation polish (DONE)
- [x] Staff moderation queue for reported Q&A messages
  - reports filter (open/resolved/all)
  - actions: resolve / remove message / suspend user
- [x] Audit trail for staff actions (`core.StaffActionLog`)
- [x] Staff-only visibility aids
  - product Q&A tab open-report badge
  - per-message open-report count badges
- [x] Suspensions review + unsuspend action

## Phase 6 — Launch hardening
- [ ] Rate limiting / abuse controls review
- [ ] Observability and error reporting
- [ ] Backups and performance tuning

### Launch hardening (DONE)
- Request IDs + log context filter (rid/user/path)
- Throttle GET download endpoints (paid + free)
- Add lightweight audit/operational log lines for moderation + downloads

### Migration stability (DONE)
- Align ops/logging models to their migrations (no PK-type flips).
- If local DB migration history becomes inconsistent, recover by dropping/recreating the local DB and rerunning `migrate`.

### Next: Ops + launch readiness
- Add admin reconciliation page per-order (ledger totals vs transfers) + export.
- Expand Admin Ops with: failed emails panel, payout/backlog summary, webhook latency histogram.
- Add staff tooling for manual reprocessing of a Stripe event **only** via a guarded, audited workflow (v2).

## 2026-02-10 — Launch hardening: analytics migration
- Confirm Render environment variables: `GOOGLE_MEASUREMENT_ID` (required) and optional GA4 Data API vars (`GOOGLE_ANALYTICS_PROPERTY_ID`, `GOOGLE_ANALYTICS_CREDENTIALS_JSON` or `GOOGLE_ANALYTICS_CREDENTIALS_FILE`).
- Verify GA events are firing on production and real-time reports populate.
- Remove Plausible-specific UI remnants once GA is confirmed stable (optional cleanup).


## Completed
- Native analytics: server-side pageview capture + admin dashboard panel + retention pruning + range filters (today/7d/30d/custom).

## Next
- Add rate limiting for cart/checkout/Q&A/reviews.
- Seller payout reconciliation UI (pending vs available).
- References pages (Help/FAQ/Tips & Tricks).

- ✅ Seller payouts reconciliation page (available vs pending, pending items, ledger table)
- ✅ Abuse control: throttled review create/reply endpoints


### 2026-02-10
- [x] Admin dashboard: Google Analytics link visible (SiteConfig URL).
- [x] References: About page (static v1) + sitemap entries.
- [ ] References: polish Help/FAQ/Tips content.
- [ ] Launch hardening: reCAPTCHA v3 wiring on public write actions.


### Launch Hardening (current)

- [x] Native analytics dashboard filters (today/7d/30d/custom)
- [x] Centralized throttle policy + throttle logging to native analytics
- [x] Admin "Abuse signals" panel (24h/7d + top rules)
- [ ] Expand throttling to login/register (already present), and add per-endpoint tuning after observing real traffic
- [ ] Add reCAPTCHA v3 on public write actions (register, reviews, Q&A)


### Legal / Licensing (next)

- [x] Add versioned licensing documents (Digital License, Seller Agreement, Physical Policy)
- [ ] Wire Seller Agreement acceptance into seller onboarding (explicit checkbox + acceptance record)
- [ ] Wire Digital License acknowledgment into digital checkout/download flows where appropriate
- [ ] Add admin UI shortcut to publish/clone legal docs and preview rendering


## 2026-02-10 — Next steps
- Add seller fulfillment queue filters (Pending only toggle, search by order/product).
- Add notifications UI badge counts for open fulfillment tasks (optional).
- Add order fulfillment SLA reminders (optional scheduled email) and export packing slips (PDF).

- [x] Free digital listings cap enforcement (email verification + Stripe onboarding beyond cap) (2026-02-10)

## Next — Seller Fulfillment UX polish
- Add bulk actions (mark all shipped / exported packing slip).
- Add buyer messaging from order detail.
- Add optional carrier presets and printable label links.
