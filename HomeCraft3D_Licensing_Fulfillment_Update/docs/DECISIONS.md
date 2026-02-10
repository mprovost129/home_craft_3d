# Home Craft 3D — DECISIONS

Last updated: 2026-01-31 (America/New_York)

## Data and performance
### 1) Card ratings via annotations
Decision:
- Use queryset annotations (`avg_rating`, `review_count`) for lists.
Reason:
- Avoid N+1 queries and keep pages fast.

### 2) Trending badge normalization rule
Decision:
- Templates ONLY check `p.trending_badge`.
Reason:
- Prevent drift across home/browse/detail templates.

Implementation:
- Home: `p.trending_badge = is_trending OR (id in computed_home_trending_ids)`
- Browse: `p.trending_badge` should be driven by a consistent subset rule (top N and/or score threshold), not “everything in trending sort”.

### 3) Trending computation uses engagement events
Decision:
Trending signals include:
- Paid purchases (highest weight)
- Add-to-cart (strong intent)
- Reviews (velocity)
- Views (weak, day-1 realism)
- Avg rating (quality, low weight)

Reason:
- Day-1 trending needs signals even without sales volume.

### 4) Trending tie-breakers prioritize quality
Decision:
When trending_score ties:
- sort by `avg_rating` then `created_at`
Reason:
- Trending should not promote junk when the score is tied.

### 5) Top Rated has a minimum review threshold + fallback
Decision:
- Require `MIN_REVIEWS_TOP_RATED` (currently 3).
- If none meet threshold, fall back to best early ratings and show a warning banner.
Reason:
- Prevent a single review from dominating early and keep browse pages populated.

### 6) Engagement logging is “best effort”
Decision:
- Engagement logging must never block core flows.
Reason:
- Analytics is optional; purchase flow is not.

Implementation:
- cart_add logs ADD_TO_CART inside try/except
- product_detail logs VIEW inside try/except with session throttling

# docs/DECISIONS.md

# Home Craft 3D — Decisions (Locked + Current)

Last updated: 2026-02-09

## Email verification gating (LOCKED)
- Users must verify email before: posting Q&A, starting seller Stripe onboarding, or leaving reviews.
- Unverified users can still browse the marketplace and manage their profile.

## Notifications rendering (LOCKED)
- All emails also create in-app notifications.
- Notifications are categorized by type (verification, refund, password, etc.).
- In-app notification detail should resemble the email that was sent.
- Implementation: store rendered email bodies (`Notification.email_text`, `Notification.email_html`) at send time and render an "Email view" tab when available.


## Free digital giveaways cap (LOCKED)
- Non-Stripe-ready sellers may have at most **SiteConfig.free_digital_listing_cap** active FREE digital FILE listings (default **5**).
- Enforcement occurs at **activation** time (draft-first remains soft until activation).

## Downloads counting (LOCKED)
- Downloads are counted at the **product/bundle** level via `Product.download_count`.
- Per-asset download counts may exist, but Seller Listings displays bundle-level downloads.

## Tips & Tricks content (LOCKED)
- Tips & Tricks lives under Navbar → References.
- Tips & Tricks is a static page for now; it will be migrated into the Blog later.

## Seller Listings units sold (CURRENT)
- Units sold displayed to sellers is **net**: paid quantity minus refunded physical line items (RefundRequest status=refunded).


This file records decisions that govern implementation and must not be silently changed.

---

## Payments / Money Handling

### Snapshot-based accounting (LOCKED)
- **Fees/settings are snapshotted at order creation** to preserve historical correctness.
- `Order.marketplace_sales_percent_snapshot` is the source of truth for marketplace fee rate at the time of purchase.
- `OrderItem` stores per-line ledger:
  - `marketplace_fee_cents`
  - `seller_net_cents`
- Legacy flat platform fee snapshot field remains present but is **not used** and must remain **0**.

### Stripe Connect readiness gates (LOCKED)
- A seller is “ready” only if:
  - `stripe_account_id` exists AND
  - `details_submitted`, `charges_enabled`, `payouts_enabled` are all true.
- Owner/admin bypass is treated as ready.
- Listings creation/modification is gated behind Connect readiness.

### Webhooks separation (LOCKED)
- Checkout/order webhooks (orders side) are separate from Stripe Connect account update webhooks (payments side).
- Connect webhook endpoint must use a **separate** signing secret: `STRIPE_CONNECT_WEBHOOK_SECRET`.

---

## Orders / Access Control

### Guest checkout access (LOCKED)
- Guest orders are accessed by token query string `?t=<order_token>`.
- Guest download links and guest refund detail access must validate token against `order.order_token`.

### Guest paid email with digital downloads (CURRENT)
- On `Order.mark_paid()`, if order is guest and has digital items, send a best-effort email that includes:
  - tokenized order detail link
  - tokenized download links per digital asset
- Email send failures are non-fatal (best-effort).

---

## Refunds (LOCKED)

### Refund scope
- Refund requests are **physical-only**.
- Refunds are **full refunds per physical line item** only.
- Digital products are **not refundable** in v1.

### Allocation rules (CURRENT)
- Tax is allocated proportionally across all order items by `line_total_cents`.
- Shipping is allocated proportionally across shippable items (`requires_shipping=True`) by `line_total_cents`.
- Refund amount is stored as snapshots on `RefundRequest` at creation and becomes the source of truth.

### Refund authority
- Buyer/guest may create a request (subject to permissions).
- Seller decides approve/decline.
- Seller triggers Stripe refund after approval.
- Staff has a safety-valve endpoint and admin action to trigger refunds (dangerous).

### Stripe refunds mechanism (CURRENT)
- Refunds are created via Stripe Refund API referencing `order.stripe_payment_intent_id`.
- Idempotency key: `refundreq-<refund_request_uuid>`.
- Free checkouts (`payment_intent_id == "FREE"`) cannot be refunded via Stripe.

---

## Site settings rule (LOCKED)
- Any “setting” that affects behavior must be DB-backed via SiteConfig and snapshotted on Orders at creation (as applicable).
  - (This slice uses order snapshots; Connect uses env secrets; future fee/tax settings must follow this rule.)

---

# Home Craft 3D – Decisions (Locked + Active)

## Accounting & Historical Correctness
- Fee and payout logic must be historically correct:
  - Fee percent is snapshotted on the `Order` at creation time.
  - Seller identity is snapshotted on each `OrderItem`.
  - Do not recompute old orders using live settings.

## Stripe Connect Readiness
- Seller readiness is determined by `SellerStripeAccount.is_ready` property.
- Owner/admin bypass is treated as ready for gating and UX flows.
- Do not filter in the DB on `is_ready` because it is not a field.

## Refunds (Locked Requirements)
- Refunds are allowed only for PHYSICAL products in v1.
- Refund requests are FULL refunds per physical line item only.
- Digital products are never refundable in v1.
- Guest refund requests require:
  - tokenized order access (`?t=<order_token>`)
  - email confirmation equals `order.guest_email`

## Idempotency & Safety
- Refunds:
  - Stripe refund call uses idempotency key `refundreq-<refund_request_id>`.
  - Refund amount is strictly `RefundRequest.total_refund_cents_snapshot`.

## Code Organization
- Canonical seller gating decorator lives in `payments.decorators`.
- `payments.permissions` exists only as a backwards-compatible re-export to prevent import breakage.

## Favorites & Wishlist
- Favorites and Wishlist are separate models/entities.
- Both are shown on a single combined page for UX simplicity.
- Favorites/Wishlist require login AND verified email (unverified users have limited access).

## Notifications parity with email (locked)
- All user-facing emails that are sent to a **registered user** MUST also create an in-app `Notification`.
- `notifications.services.notify_email_and_in_app(...)` is the single choke point for creating the notification and sending the email.
- If an email has no explicit plaintext template, plaintext is derived from the HTML template via `strip_tags(...)`.

## Reviews (locked)
- Reviews are only by verified purchasers.
- Sellers may post a public reply to a product review (one reply per review in v1).

## Digital download metrics (locked)
- Digital download metrics are tracked and displayed at the **product (bundle)** level.
- Seller Listings for FILE products show:
  - **Unique downloaders** = distinct registered users + distinct guest sessions.
  - **Total download clicks** = `Product.download_count`.
- Guest uniqueness excludes blank session keys so missing sessions cannot inflate unique counts.
- Both free and paid download endpoints increment these metrics (best-effort; never block downloads).

## Trending badge membership (computed)
- Decision: Trending badge is limited to manual `Product.is_trending` plus computed Top N by `trending_score` where `trending_score > 0`.
- Computed membership is cached (15 min) and reused across Home and Browse for consistency.


## Seller analytics windows (7/30/90)
- Seller analytics are presented as rolling windows (last 7, 30, or 90 days).
- Refund impact for net units sold is computed using refund_request.refunded_at within the window (and paid units use order.paid_at within the window).
- Digital download analytics are counted at the product (bundle) level; unique downloaders include distinct logged-in users plus distinct guest sessions.

- Moderation actions (Q&A): reports do not auto-hide; staff resolves reports manually. Staff may remove messages (soft delete) and suspend users via moderation queue; all actions are recorded in StaffActionLog.

- Moderation UX: staff can filter Q&A reports by status (open/resolved/all). Product Q&A tab shows staff-only open reports count badge. Suspended users review list is available to staff; suspensions remain recorded in StaffActionLog.

- Moderation UX: staff can unsuspend users from the suspensions review page; unsuspension is recorded in StaffActionLog. Product Q&A threads show staff-only per-message open-report count badges.

## Launch hardening (observability + abuse controls)
- All high-value/abuse-prone GET endpoints (digital downloads) are throttled via core.throttle(throttle_rule, methods=("GET",)).
- Every request gets a request id (X-Request-ID) and logs include rid/user_id/path for traceability.

## Webhook reliability + ops visibility (2026-02-09)
- Stripe webhooks must be **idempotent** (StripeWebhookEvent) and **observable** (StripeWebhookDelivery).
- After signature verification, **internal processing exceptions return HTTP 500** so Stripe will retry. Failures are logged in StripeWebhookDelivery with request_id.
- Refund triggers must be logged with `refunds.RefundAttempt` so staff can diagnose misconfig/Stripe errors without digging through logs.

## Migration hygiene (2026-02-10)
- Do not change primary key types for already-shipped tables via migrations (UUID↔bigint casts are brittle and commonly fail).
- `orders.StripeWebhookDelivery` is treated as append-only ops logging; schema is aligned to its initial migration (UUID pk + received_at).
- If local dev migration history becomes inconsistent (e.g., a downstream app migration is marked applied before its dependency), the supported recovery is: **drop/recreate the local DB and rerun migrations**.

## 2026-02-10 — Analytics provider
- Google Analytics 4 is the active analytics provider (Plausible deprecated).
- Client-side tracking uses GA4 Measurement ID from environment variable `GOOGLE_MEASUREMENT_ID` mapped to `settings.GA_MEASUREMENT_ID`.
- Server-side dashboard reporting (optional) uses GA4 Data API with service-account credentials provided via env (`GOOGLE_ANALYTICS_*`). If not configured, admin dashboard links out to GA.


## Native analytics (v1)
- Home Craft 3D uses first-party server-side pageview analytics for in-app dashboard metrics (no external analytics required).
- Analytics stores hashed IPs (salted) and session keys; no raw IPs are persisted.
- Collection is throttled and bot-filtered; retention is configurable via SiteConfig.
- External analytics (GA) may be used optionally via outbound link, but is not required for dashboard metrics.

- Seller payout UI: "Pending pipeline" is defined as PAID order items for the seller where the order has no TRANSFER_CREATED event yet (webhook/transfer lag visibility only; ledger remains source of truth).


## 2026-02-10 — Analytics dashboard linking

- GA4 Data API service-account keys may be blocked by org policy; the app must not require GA credentials to function.
- `SiteConfig.google_analytics_dashboard_url` provides an optional **Open Google Analytics** link in the admin dashboard.


## Throttling & Abuse Visibility (v1)

- Rate limiting uses cache-based throttles with a centralized rule set (`core/throttle_rules.py`).
- Throttle hits are recorded in native analytics as `THROTTLE` events for admin visibility.
- Abuse signals are informational in v1 (no auto-blocking beyond throttle).


## Legal docs: versioned + seeded (2026-02-10)

- Legal policies are stored as versioned `LegalDocument` rows and displayed from the latest published version.
- Seeded v1 legal docs via migration to avoid blank public pages on fresh DBs.
- Only Terms/Privacy/Refund/Content are required for “accept and continue” flows; licensing pages are informational unless later required by a specific workflow (e.g., seller onboarding).



## 2026-02-10 — Seller order ops
- Sellers must be notified for ALL paid sales (digital + physical) via email + in-app notification; tips excluded.
- Physical orders create persistent SellerFulfillmentTask per seller+order; tasks close automatically when no pending shippable items remain.
- Licenses & Policies must be discoverable from global navigation (References + Footer).
