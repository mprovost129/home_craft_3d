# Home Craft 3D — MEMORY

Last updated: 2026-02-10 (America/New_York)

## 2026-02-10 — Native analytics dashboard filters
- Admin Dashboard native analytics panel now supports range filters: **Today**, **Last 7 days**, **Last 30 days**, and **Custom date range**.
- Server-side aggregation functions accept explicit start/end datetimes (end is exclusive) for consistent reporting.


## 2026-02-10 — Local DB + migration recovery (launch hardening)
- Fixed schema drift for `orders.StripeWebhookDelivery` by aligning the **model** to the already-created migration/table shape:
  - UUID primary key
  - `received_at` timestamp (not `created_at`)
  - indexes on `(status, -received_at)` and `(event_type, -received_at)`
- Cleaned up `refunds` migration history to eliminate UUID↔bigint cast failures during local resets:
  - Removed the churny RefundAttempt create/delete/recreate chain
  - Replaced with a single `refunds.0002_refundattempt` creating `RefundAttempt` with BigAuto PK
- If local `django_migrations` becomes inconsistent (e.g., `payments.0002` applied before `orders.0002`), the supported recovery path is: **drop/recreate local DB** and re-run `migrate`.

## Goal
A working marketplace for:
- Physical 3D printed models (shipped by sellers)
- Digital 3D print files (downloadable assets)

References / support content:
- Navbar includes a "References" dropdown with Help, FAQs, and Tips & Tricks.
- Tips & Tricks is a static page for now (it will become the Blog later).

Logged-out users can browse. Users have public usernames.

---

## Storefront buckets (Home page)
Home page shows 4 buckets, each capped at HOME_BUCKET_SIZE (currently 8):
- Featured: manual flag `Product.is_featured`
- New: most recent active listings
- Trending: manual override `Product.is_trending` + computed fill
- Misc: active products not already shown above

Home uses:
- `_annotate_rating()` so rating + review count display on every home card without per-card DB queries.
- `p.can_buy` flag to enable/disable Add to cart on home cards depending on seller Stripe readiness (or owner override).
- `p.trending_badge` as the single template rule for showing 🔥 Trending.

---

## Browse pages (Products list)
Browse supports:
- Search (`q`)
- Kind filtering (MODEL / FILE) via route lock or query param on the “all products” page
- Sort control:
  - new (default)
  - trending
  - top (Top Rated)

Browse cards display:
- 🔥 Trending badge when `p.trending_badge` is true
- rating summary (`avg_rating`, `review_count`) without extra queries

Browse behavior includes early-stage warnings:
- Top Rated fallback banner if no products meet `MIN_REVIEWS_TOP_RATED` yet
- Trending fallback banner when there’s no meaningful trending signal yet

---

## Ratings (no N+1)
We annotate list querysets once per request:
- `avg_rating` = AVG(reviews.rating) default 0.0
- `review_count` = COUNT(reviews) default 0

Templates should never aggregate reviews per product card.

---

## Trending (computed + day-1 realism)
Trending uses a rolling window (TRENDING_WINDOW_DAYS, currently 30 days) and mixes:
- recent paid purchases (strongest)
- recent add-to-cart events (strong intent)
- recent reviews (velocity)
- recent views (weak, but helps day-1)
- avg_rating (quality, lower weight)

Trending sort tie-breakers:
- trending_score DESC
- avg_rating DESC
- created_at DESC

Home Trending:
- manual trending products first (`is_trending=True`)
- remaining slots filled by highest computed trending_score

Badge normalization:
- templates check only `p.trending_badge`
- views set `p.trending_badge = is_trending OR computed-trending-membership`

---

## Engagement events (v1)
Added model:
- `ProductEngagementEvent` with event_type:
  - VIEW
  - ADD_TO_CART

Logging implemented:
- Product detail logs VIEW (throttled per session per product)
- Cart add logs ADD_TO_CART (best-effort, never breaks checkout)

Purpose:
- Provide “real” trending signals on day 1, even before sales volume exists.

---

## Files touched recently (high-level)
- core.views:
  - rating annotations on base queryset
  - trending computation includes purchases + reviews + engagement events
  - home buckets computed and flags applied to card objects
- products.views:
  - browse sorting modes (new / trending / top)
  - rating/trending annotations for lists
  - throttled VIEW logging in product_detail
  - “more like this” annotated for ratings
- templates:
  - home cards: add-to-cart button + rating + 🔥 badge
  - product list cards: sort controls + rating + 🔥 badge
  - product detail “more like this”: rating + 🔥 badge

---

## Current known risk / reminder
Trending badge membership on browse needs a strict rule:
- avoid marking *every* item as “Trending” when sort=trending
- badge should represent a subset (top N or score threshold), not “everything in the list”

---

## Digital download metrics (bundle-level)

LOCKED (Updated Platform Outline, Feb 2026):
- Seller Listings for digital products display **unique downloaders** and **total download clicks**.
- Counts are tracked at the **product/bundle level** (not per-asset) for seller-facing metrics.

Implementation (current):
- `Product.download_count` stores total download clicks (bundle-level).
- `products.ProductDownloadEvent` records each download action with:
  - optional `user` (logged-in)
  - `session_key` for guest uniqueness approximation
- Free downloads (`products:free_asset_download`) and paid downloads (`orders:download_asset`, `orders:download_all_assets`) both:
  - increment `DigitalAsset.download_count` (per-asset display)
  - increment `Product.download_count` (bundle-level)
  - create `ProductDownloadEvent` (best-effort; never blocks downloads)

Seller Listings metrics:
- Physical products show **net units sold** (PAID minus refunded).
- Digital products show **unique_downloaders / total_downloads**.


## 2026-02-09 — Change Pack: Email Verification Gating
- Added Profile email verification fields (email_verified, email_verification_token, email_verification_sent_at).
- Added /accounts/verify/ status page + resend flow; verification link sets email_verified true.
- Gated actions behind verified email: Stripe Connect onboarding, Q&A posting/report/delete, and review creation.


## 2026-02-09 — Change Pack: Free Digital Cap + Downloads + Seller Listings
- Added **SiteConfig.free_digital_listing_cap** (default 5) and wired it into the dashboard settings form.
- Enforced **free digital activation cap** for non-Stripe-ready sellers (cap blocks activation beyond limit; redirects to Stripe status).
- Added **Product.download_count** for bundle-level download tracking; Seller Listings uses this as `total_downloads`.
- Seller Listings now computes **net units sold** as paid quantity minus refunded physical line items (RefundRequest status=refunded).


This file is the “what exists right now” ledger. It should match the codebase.

---

## Current State Summary (Orders + Payments + Refunds)

### Orders (app: `orders`)
- Orders are **financially snapshotted** at creation time to preserve historical correctness.
- Supports **registered buyers** and **guest checkout**.
- Guest access is **tokenized** via `order.order_token` and `?t=<token>` query string for order/detail/download access and guest refund access.
- Digital downloads for guests are emailed on payment (best-effort) and include tokenized links.

**Key models**
- `Order`
  - Identity: UUID primary key.
  - Parties:
    - `buyer` nullable (registered user).
    - `guest_email` used when buyer is null.
    - Validation: order must have **buyer OR guest_email**; if buyer present, guest_email is cleared.
  - Access:
    - `order_token` UUID (db indexed), used for guest order access and guest downloads/refund access.
  - Totals: `subtotal_cents`, `tax_cents`, `shipping_cents`, `total_cents`.
  - Snapshots:
    - `marketplace_sales_percent_snapshot` (Decimal % captured at creation).
    - `platform_fee_cents_snapshot` retained for legacy compatibility but must remain **0** (not used).
  - Stripe tracking:
    - `stripe_session_id` (indexed)
    - `stripe_payment_intent_id`
    - `paid_at`
  - Shipping snapshot fields stored on `Order` for physical shipping labels / fulfillment:
    - name/phone/address fields.
  - Helpers:
    - `requires_shipping` uses `Order.items.requires_shipping`.
    - `recompute_totals()` derives subtotal/total and sets `kind` (digital/physical/mixed).
    - `mark_paid()` sets status/paid_at, captures stripe ids, records event, and emails guest downloads.

- `OrderItem` (alias `LineItem`)
  - Seller is **snapshotted** on the line: `seller` FK to user (PROTECT).
  - Line flags:
    - `is_digital`
    - `requires_shipping`
  - Ledger snapshot on each line:
    - `marketplace_fee_cents`
    - `seller_net_cents`

- `OrderEvent`
  - Order audit trail: created/session created/paid/canceled/refunded/transfer created/warning.

- `StripeWebhookEvent`
  - Stores processed `stripe_event_id` for strict webhook idempotency.

---

### Payments (app: `payments`)
Payments owns Stripe Connect onboarding state + seller ledger models + seller payout/ledger UI + connect webhook syncing.

**Key models**
- `SellerStripeAccount`
  - OneToOne: `user` with related name `stripe_connect`.
  - Fields:
    - `stripe_account_id` (indexed)
    - `details_submitted`, `charges_enabled`, `payouts_enabled`
    - `onboarding_started_at`, `onboarding_completed_at`
  - `is_ready` property: account id present AND all three booleans true.
  - Methods: mark onboarding started / mark completed if ready.

- `SellerBalanceEntry`
  - Append-only ledger of seller balance deltas.
  - `amount_cents` signed:
    - positive => platform owes seller
    - negative => seller owes platform
  - Links:
    - optional `order` and `order_item` references.
  - Reasons: payout/refund/chargeback/adjustment.

**Views / flows**
- Connect onboarding:
  - `connect_status` shows current connect status and optionally refreshes status.
  - `connect_start` creates Express account if needed then redirects to Stripe-hosted onboarding link.
  - `connect_sync` is a manual refresh button for status.
  - `connect_refresh` and `connect_return` handle Stripe redirect UX.
- Payouts / ledger:
  - `payouts_dashboard` shows signed balance + paginated ledger with filters.
- Connect webhook:
  - `stripe_connect_webhook` handles `account.updated` and updates local booleans.
  - Uses **dedicated secret** `STRIPE_CONNECT_WEBHOOK_SECRET`.

**Global template context**
- `payments.context_processors.seller_stripe_status`
  - `seller_stripe_ready`: True/False/None (None means not a seller)
  - `has_connect_sync`: whether route exists
  - `user_is_owner`, `user_is_seller`
  - Avoids templates touching profile relations directly.

**Decorator**
- `payments.decorators.stripe_ready_required` gates seller publishing/modifying listings until Connect is ready (owner bypass).

---

### Refunds (app: `refunds`)
Refunds is implemented and wired as a full feature.

**Locked policy implemented**
- Refund requests are **physical-only** and **full refund per physical line item**.
- Digital products are **non-refundable** (v1).

**Model**
- `RefundRequest`
  - One refund request per order line item:
    - `order_item` is OneToOne with related name `refund_request`.
  - Denormalized parties:
    - `seller` snapshot (from order item)
    - `buyer` nullable
    - `requester_email` for guest
  - Status flow:
    - requested → approved/declined → refunded
    - canceled exists for future UI, but not central in current flows.
  - Snapshot amounts at creation (source of truth):
    - line subtotal
    - allocated tax
    - allocated shipping (allocated across shippable lines)
    - total refund
  - Stripe tracking:
    - `stripe_refund_id`, `refunded_at`
  - Seller decision tracking:
    - `seller_decided_at`, `seller_decision_note`

**Services**
- Allocation:
  - Tax allocated across all lines proportionally by `line_total_cents`.
  - Shipping allocated across **requires_shipping=True** lines proportionally by `line_total_cents`.
- Creation:
  - Only allowed on PAID orders and physical line items.
  - Enforces one request per item.
  - Writes `OrderEvent` WARNING for audit.
- Decision:
  - Seller/owner/staff can approve/decline.
  - Writes `OrderEvent` WARNING for audit.
- Trigger refund:
  - Allowed only after approval and if not already refunded.
  - Uses Stripe Refund API against `order.stripe_payment_intent_id`.
  - Uses `rr.total_refund_cents_snapshot` as the source of truth.
  - Writes `OrderEvent` REFUNDED for audit.

**Views**
- Buyer list (logged-in buyers).
- Buyer detail supports:
  - buyer
  - staff
  - guest access via valid underlying order token.
- Buyer/guest create request:
  - Guest must confirm checkout email matches `order.guest_email`.
  - Token is preserved through redirects.
- Seller queue/detail/actions:
  - Seller sees their requests; owner/staff can see all.
  - Approve/decline, then trigger Stripe refund.
- Staff queue + refund trigger safety valve.

**Admin**
- `RefundRequestAdmin` provides:
  - quick links to Order and OrderItem
  - read-only snapshot display
  - **dangerous** “admin_trigger_refund” action for APPROVED + not-yet-refunded requests

---

## Known Duplications / Cleanups Needed
- `payments.permissions.py` duplicates the decorator already in `payments.decorators.py`.
- `payments/services.py` appears duplicated twice in the pasted text (same content). In repo there should be **only one** file.

(These aren’t “broken”, but they are maintenance hazards.)

---

## What’s “Done” for this slice
- Orders: buyer/guest, token access model, snapshot accounting model, paid flow hooks, events, webhook idempotency table.
- Payments: Connect onboarding + sync + webhook, seller ledger models + dashboard, global status context.
- Refunds: full request/decision/refund flow with allocation + Stripe refund call + admin controls.

---

# Home Craft 3D – Project Memory

## Snapshot (2026-02-03) — Orders + Payments + Refunds

### Orders (source of truth: snapshots + ledger fields)
- Orders are production-grade and designed for historical correctness.
- `Order` snapshots:
  - `marketplace_sales_percent_snapshot` captures percent-based marketplace fee at order creation.
  - `platform_fee_cents_snapshot` is legacy/unused and must remain `0`.
- `OrderItem` snapshots:
  - `seller` FK snapshot (do not rely on product->seller later).
  - Per-line ledger fields: `marketplace_fee_cents`, `seller_net_cents`.
- Guest access:
  - Guest orders have `guest_email` + `order_token` and can access order/download links via `?t=<token>`.
  - Paid guest emails include tokenized order link and tokenized digital download links.
- `Order.mark_paid()`:
  - Sets paid status and `paid_at`, stores Stripe IDs once, emits `OrderEvent`.
  - Sends guest paid email with downloads when applicable.

### Payments (Stripe Connect + seller readiness + seller ledger)
- Stripe Connect Express onboarding implemented:
  - `SellerStripeAccount` (OneToOne to user) stores Connect account id and readiness flags:
    - `details_submitted`, `charges_enabled`, `payouts_enabled`, plus onboarding timestamps.
  - Ready state is `is_ready` property (do not query it as a DB field).
- Seller gating:
  - Canonical gate decorator: `payments.decorators.stripe_ready_required`
  - Back-compat shim: `payments.permissions.stripe_ready_required` re-exports decorator.
- Seller ledger:
  - `SellerBalanceEntry` is append-only signed cents ledger.
  - `payments.services.get_seller_balance_cents()` returns signed sum.
  - `payments.views.payouts_dashboard` shows balance + ledger entries with filters.
- Connect status UX:
  - `connect_status` page shows readiness + continue CTA.
  - `connect_start` creates Express account once and redirects to Stripe onboarding.
  - `connect_sync` refreshes from Stripe manually.
  - Connect webhook endpoint updates account readiness on `account.updated`.

### Refunds (locked rules: physical-only, full refund per line item)
- Refund requests are FULL refunds per PHYSICAL line item only.
- Digital products are non-refundable in v1.
- `RefundRequest` model:
  - One refund request per `OrderItem` (OneToOne).
  - Snapshots at creation:
    - `line_subtotal_cents_snapshot`
    - `tax_cents_allocated_snapshot`
    - `shipping_cents_allocated_snapshot`
    - `total_refund_cents_snapshot`
  - Tracks Stripe refund id + timestamps, seller decision fields.
- Allocation:
  - Tax allocated across ALL items by line-total proportion.
  - Shipping allocated across shippable items only by line-total proportion.
- Flow:
  - Buyer/guest creates request (guests confirm email matches checkout email).
  - Seller approves/declines; after approval seller triggers Stripe refund.
  - Staff safety-valve refund trigger exists (admin action + staff endpoint).

## Code hygiene fixes applied (2026-02-03)
- Removed duplicate `stripe_ready_required` logic by making `payments/permissions.py` a re-export.
- Removed duplicated block in `payments/services.py` (function was defined twice).

---

## Favorites & Wishlist
- Implemented as separate entities (Favorites vs WishlistItems) in new `favorites` app.
- Single combined page: `/favorites/` with tabs.
- Add/remove actions exposed on product detail pages (logged-in users).
- Linked from navbar user menu and Consumer Dashboard.

## Free digital listing cap hardening
- Enforced **SiteConfig.free_digital_listing_cap** server-side in seller **create** and **duplicate** flows (not just UI), preventing cap bypass when Stripe is not ready.

## Notifications email-like rendering
- Notifications now store rendered email bodies (`email_text`, `email_html`) at send time.
- Notification detail page renders an **Email view** tab (HTML if available) plus a **Text** tab to mirror what was sent.

## Email → In‑app notification parity (2026-02-09)
- Locked rule implemented: **user-facing emails also create an in-app Notification** with the same subject/body and an action link.
- `notifications.services.notify_email_and_in_app(...)` now supports `email_template_txt=None` and falls back to `strip_tags(html)` for plaintext.
- Wired into:
  - Welcome email (`accounts/signals.py`)
  - Order lifecycle emails (`orders/models.py`)
  - Refund lifecycle emails (registered users) (`refunds/services.py`)
  - Seller dashboard “free unlock” email (`dashboards/views.py`) + new template `templates/emails/free_unlock.html`.

## Unverified account access limits expanded (2026-02-09)
- Locked rule enforced: unverified users can sign in and access profile/basic dashboard, but **cannot use registered-only features**.
- Added email verification gating to:
  - Favorites/Wishlist (`favorites/views.py`)
  - Notifications (`notifications/views.py`)
  - Seller-only views (via `products.permissions.seller_required`)

## Seller replies to reviews (2026-02-09)
- Locked rule implemented: sellers can reply publicly to product reviews.
- Added `reviews.ReviewReply` (one reply per review) + seller-only reply endpoint.
- Seller replies are displayed under reviews on:
  - product detail Reviews tab
  - full product reviews page

## Trending badge hardening (2026-02-09)
- Locked rule enforced consistently across Home + Browse: 🔥 Trending badge shows only for:
  - manual `Product.is_trending=True`, OR
  - computed Top N by `trending_score` with `trending_score > 0` (cached).
- Home and Products list now share one computed badge-membership function (`products.services.trending.get_trending_badge_ids`).


## Seller analytics summary (2026-02-09)
- Added Seller Analytics page with 7/30/90 day windows.
- Metrics include: views/clicks/add-to-cart (ProductEngagementEvent), orders + paid units, refunded units (RefundRequest REFUNDED), net units sold, gross/net revenue, and bundle-level download metrics (unique/total via ProductDownloadEvent).
- Added dashboard sidebar link: Seller → Analytics.

## Seller listings metrics polish (2026-02-09)
- Seller Listings now strictly matches locked metric definitions:
  - Physical: **NET units sold** (paid − refunded).
  - Digital: **unique downloaders + total download clicks** at the product (bundle) level.
- Uniqueness logic excludes blank guest session keys so guest counts cannot be inflated by missing sessions.

- 2026-02-09: Added staff Q&A moderation queue actions (resolve report, remove message, suspend user) with audit trail via core.StaffActionLog. Fixed staff reports template URL name mismatch.

- 2026-02-09: Moderation UX polish: staff Q&A reports filter (open/resolved/all), product Q&A tab shows staff-only open-report count badge, added staff suspensions list page.

- 2026-02-09: Moderation UX polish: added staff unsuspend action (with StaffActionLog), and staff-only per-message open-report badges in product Q&A threads.

## 2026-02-09 — Launch hardening
- Added RequestIDMiddleware with X-Request-ID response header and request-context logging filter.
- Enhanced dev/prod LOGGING to include request_id/user_id/path and configurable LOG_LEVEL.
- Extended core throttle decorator to support GET endpoints (methods=...).
- Added throttles to digital download endpoints (paid + free) to prevent abuse/inflated counts.

## 2026-02-09 — Ops observability hardening
- Reintroduced operational models:
  - `orders.StripeWebhookDelivery` to log webhook receipt/processing/duplicates/errors (request_id, timestamps).
  - `refunds.RefundAttempt` to log each attempt to trigger a Stripe refund (success/failure, request_id).
- Stripe webhook now returns **HTTP 500 on internal processing errors** (after signature verification) so Stripe retries; status is tracked in `StripeWebhookDelivery`.
- Added **Admin Ops** dashboard (`/dashboard/admin/ops/`) showing recent webhook errors, refund failures, and order warnings.

## 2026-02-10 — Seller Listings stabilization + deploy docs
- Fixed Seller Listings rendering:
  - Template now iterates `products` as Product instances (no `row.obj` wrapper).
  - Removed non-existent template attributes (`is_digital`, `download_total`).
  - Digital metrics display uses `unique_downloaders_count` + bundle-level `Product.download_count`.
  - Physical listings display **Net units sold** label.
- Added production playbooks:
  - `docs/DEPLOY_RENDER.md` (Render-safe deployment plan)
  - `docs/POST_DEPLOY_CHECKLIST.md` (verification checklist)

## 2026-02-10 — Analytics: migrate Plausible → Google Analytics 4
- Replaced Plausible client script with GA4 `gtag.js` snippet (uses `GA_MEASUREMENT_ID` from settings/env via context processor).
- Added GA4 Data API reporting module (`dashboards/analytics_google.py`) and wrapper (`dashboards/analytics.py`) for Admin Dashboard summaries/top pages.
- Admin dashboard analytics panel updated to 'Google Analytics' (30-day summary + top pages) and optional outbound link via `SiteConfig.google_analytics_dashboard_url`.
- CSP updated to remove Plausible frame-src and allow Google Tag Manager host.


## 2026-02-10 Native analytics (server-side)


- Implemented first-party server-side pageview analytics via new `analytics` app (AnalyticsEvent + admin).
- Added `analytics.middleware.RequestAnalyticsMiddleware` to record HTML GET/HEAD pageviews (bot filtered, throttled).
- Replaced Admin Dashboard analytics panel to use native analytics (30-day summary + top pages); Google Analytics link remains optional.
- Added SiteConfig toggles: `analytics_enabled`, `analytics_retention_days` with Admin Settings form support.
- Added management command `prune_analytics_events` to enforce retention policy.

- (2026-02-10) Added seller payouts reconciliation page (available vs pending) + review throttling + sidebar link.


## 2026-02-10 — Admin dashboard polish + References/About

- Admin dashboard: fixed Analytics card layout and ensured the **Open Google Analytics** button appears when `SiteConfig.google_analytics_dashboard_url` is set.
- Added **About** page under References and included References pages in the sitemap.


## 2026-02-10 — Launch hardening: throttling policy + abuse signals

- Centralized throttle policy in `core/throttle_rules.py` and updated all endpoint throttles to use it.
- Throttle rejections are now logged into native analytics as `AnalyticsEvent(event_type=THROTTLE)` with `meta.rule`.
- Admin dashboard now shows "Abuse signals" (24h/7d throttled counts + top throttled rules) alongside native analytics.


## 2026-02-10 — Legal / Licensing documents (versioned, DB-backed)

- Extended `legal.LegalDocument` doc types to include:
  - `digital_license` (Digital Product License)
  - `seller_agreement` (Seller Agreement)
  - `physical_policy` (Physical Product Policy)
- Added public routes and templates for the new legal pages.
- Implemented a data migration to seed/publish initial v1 documents for all legal doc types.
- Legal document bodies are rendered as trusted HTML (`|safe`) since editing is admin-only.



## 2026-02-10 — Licensing nav + seller fulfillment tasks
- Added 'Licenses & Policies' landing page under legal app and linked it from Navbar → References and Footer (Support + Legal columns).
- Extended seller new order notifications to cover both physical and digital sales (email + in-app) via Order.mark_paid hook.
- Implemented persistent SellerFulfillmentTask records for paid orders with physical items; tasks remain open until seller marks items shipped/delivered.
- Seller dashboard now shows Fulfillment tasks count + preview and links to fulfillment queue.


## 2026-02-10 — Change Pack: Free digital cap verification gate
- Enforced locked policy: when a seller exceeds `SiteConfig.free_digital_listing_cap` for active FREE FILE listings, they must **verify email first** (redirect to email verification), then complete **Stripe Connect onboarding** to publish more.
- Applied to both activation toggle and listing duplication guard.

## 2026-02-10 — Fulfillment UX Pack
- Fixed seller fulfillment queue: `/orders/seller/orders/` now lists *physical* PAID line items and supports status tabs (pending/shipped/delivered/all).
- Seller dashboard now surfaces open `SellerFulfillmentTask` count + preview with per-order pending counts and links into the order detail.
- Seller dashboard net-units-sold aggregates now compute **paid qty − refunded qty** (refunds are full-line for physical items).

## 2026-02-10 — Admin Settings parity (Dashboard UI ↔ Django Admin)
- Synced `SiteConfig` fields so the **Dashboard Admin Settings** page and **Django admin SiteConfig** expose the same configuration surface.
- Added missing Django admin fieldsets for: free digital listing cap, GA dashboard URL, native analytics toggles, and legacy Plausible URL.
- Ensured affiliate links are editable consistently from the Dashboard Admin Settings page.
