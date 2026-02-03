# Home Craft 3D — ROADMAP

Last updated: 2026-01-31 (America/New_York)

## Phase 1 — Storefront credibility (DONE / IN PROGRESS)
✅ Add-to-cart buttons on home cards with Stripe readiness gating (`p.can_buy`)  
✅ Trending computation on home (manual override + computed fill)  
✅ Trending score includes purchases + reviews + engagement events  
✅ Trending tie-breakers include quality (`avg_rating`) and recency  
✅ Browse sort controls (New / Trending / Top Rated)  
✅ Top Rated minimum review threshold with fallback + warning banner  
✅ Rating on cards across home + browse + “more like this” using annotations  
✅ Trending badge normalization (`p.trending_badge` only)

## Phase 2 — Engagement events v1 (DONE)
✅ Model: ProductEngagementEvent (VIEW, ADD_TO_CART)  
✅ Logging:
- ✅ VIEW on product detail (throttled)
- ✅ ADD_TO_CART on cart add (best-effort)

## Phase 3 — Fix + harden badge membership rules (NEXT)
- [ ] Ensure browse “🔥 Trending” badge applies only to a meaningful subset:
  - (Option A) Top N results in trending sort (e.g., top 12)
  - (Option B) Score threshold (e.g., trending_score >= 2)
  - (Recommended) Both: badge if in top N AND score > 0
- [ ] Optional: make “Trending” badge rules identical on home and browse

## Phase 4 — Conversion + trust (UP NEXT)
- [ ] Server-side enforcement of can_buy gating (prevent direct POST add-to-cart for non-ready sellers)
- [ ] Better “More like this” relevance (category + tags later)
- [ ] Product detail enhancements (license display, physical specs, shipping info)
- [ ] Reviews UX polish

## Phase 5 — Seller growth
- [ ] Seller listing workflow polish (drafts, validation, media requirements)
- [ ] Seller analytics dashboard (views, add-to-cart, purchases)

## Phase 6 — Launch hardening
- [ ] Rate limiting / abuse controls
- [ ] Observability and error reporting
- [ ] Backups and performance tuning


# docs/ROADMAP.md

# Home Craft 3D — Roadmap

Last updated: 2026-02-03

This file is a forward plan from the current authoritative state.

---

## Now Completed (Orders + Payments + Refunds)

### Orders
- Buyer + guest checkout support (buyer nullable + guest_email).
- Token-based guest access (`order_token` + `?t=`).
- Order + line item snapshot ledger fields for marketplace fee and seller net.
- Events and webhook idempotency model in place.

### Payments
- Stripe Connect Express onboarding flow:
  - start, return, refresh, sync
- Connect readiness computed via `SellerStripeAccount.is_ready`.
- Connect webhook handler for `account.updated` using `STRIPE_CONNECT_WEBHOOK_SECRET`.
- Seller ledger models (`SellerBalanceEntry`) and seller payouts dashboard with filters.
- Global template context processor for seller Stripe status.

### Refunds
- RefundRequest model with:
  - one-per-line (OneToOne)
  - snapshot allocation fields (tax/shipping)
  - status flow + decision + refunded tracking
- Service layer implemented:
  - allocation rules
  - create request
  - seller decision
  - trigger Stripe refund
- Buyer/seller/staff views implemented.
- Admin implemented with a guarded “trigger refund” action.

---

## Next Up (High Priority)

### 1) Remove duplication / enforce single-source modules
- Delete or stop using `payments/permissions.py` (duplicate of `payments/decorators.py`) OR make it a thin import wrapper:
  - preferred: keep **one** decorator module and import from it everywhere.
- Ensure only one `payments/services.py` exists and is imported consistently.

### 2) Templates & UX polishing (if not already in repo)
- Payments:
  - `payments/connect_status.html`
  - `payments/payouts_dashboard.html`
- Refunds:
  - `refunds/request_create.html`
  - `refunds/buyer_list.html`
  - `refunds/buyer_detail.html`
  - `refunds/seller_queue.html`
  - `refunds/seller_detail.html`
  - `refunds/staff_queue.html`
- Add consistent badges:
  - Connect ready / not ready
  - Refund status chips (requested/approved/declined/refunded)

### 3) Accounting integration for refunds into seller ledger (expected next)
- When a refund is processed, ensure seller balance reflects it:
  - Create a `SellerBalanceEntry` with reason `REFUND` and correct signed amount.
- Decide whether this entry is written:
  - immediately in `refunds.services.trigger_refund`, OR
  - in Stripe webhook handling of refund events (preferred if you want Stripe to be the trigger).
- Whichever is chosen, document in DECISIONS and keep it consistent.

### 4) Chargebacks (minimal v1 handling)
- Add modeling and ledger impact for chargebacks/disputes:
  - new `SellerBalanceEntry` reason `CHARGEBACK`
  - admin/staff visibility
- Decide webhook handling and idempotency scheme.

---

## Medium Priority

### Seller reconciliation UI
- Seller “payout history” page (transfers + payouts) and per-order breakdown using snapshots.
- Admin reconciliation view:
  - order → items → seller net → transfers; plus refunds/chargebacks.

### Operational hardening
- Rate limiting for refund create endpoint.
- Better error logging around Stripe Connect webhook + refund creation failures.
- Add audit logs for staff actions (refund trigger, manual adjustments).

---

## Later
- Partial refunds (NOT in locked spec for v1; would be a v2 change requiring decision update).
- Refund cancellation workflow (buyer cancels request before decision).
- Buyer/seller messaging around refund lifecycle (email notifications).

---

# Home Craft 3D – Roadmap

## Now (Next Up)
1) Templates / UI polish
- payments:
  - `payments/connect_status.html`
  - `payments/payouts_dashboard.html`
- refunds:
  - buyer list/detail templates
  - seller queue/detail templates
  - request create template

2) Stripe event reconciliation
- Ensure the Orders Stripe webhook (checkout/refunds/chargebacks) creates:
  - `OrderEvent` records
  - `SellerBalanceEntry` entries (refund/chargeback debits, payout credits)
- Keep all ledger postings snapshot-driven (use Order/OrderItem snapshot fields only).

3) Admin reconciliation screens (minimal)
- Orders admin:
  - show snapshot fee percent
  - show per-line ledger (marketplace_fee, seller_net)
  - show payout/transfer/refund events
- RefundRequest admin already has safety valve action; add guardrails in UI text.

## Soon
4) Tests (high value)
- Refund allocation math:
  - multi-line orders with mixed shippable/digital
  - rounding behavior and invariants
- Permissions:
  - guest token access
  - buyer access
  - seller-only queue

5) Guard rails
- Prevent refund request creation for non-paid orders
- Prevent duplicate refund requests per OrderItem (already enforced via OneToOne)

## Later
6) Chargebacks
- Track disputes and apply seller debits through ledger entries.
- Add staff queue for disputes if needed (v2).
