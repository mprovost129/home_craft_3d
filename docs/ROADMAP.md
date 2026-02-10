# Home Craft 3D — ROADMAP

Last updated: 2026-02-09 (America/New_York)

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

### Next: Ops + launch readiness
- Add admin reconciliation page per-order (ledger totals vs transfers) + export.
- Expand Admin Ops with: failed emails panel, payout/backlog summary, webhook latency histogram.
- Add staff tooling for manual reprocessing of a Stripe event **only** via a guarded, audited workflow (v2).
