# Home Craft 3D — DECISIONS

Last updated: 2026-01-31 (America/New_York)

## Data + performance decisions
### 1) Ratings on cards via annotations
Decision:
- Use queryset annotations for `avg_rating` and `review_count`.
Reason:
- Prevent per-card DB queries and keep lists fast.

### 2) Trending badge normalization
Decision:
- Templates only check `p.trending_badge`.
- Views set `p.trending_badge` based on manual flag OR computed-trending membership.
Reason:
- Keeps UI consistent across home/browse/detail.

### 3) Trending computation and tie-breakers
Decision:
- trending_score combines:
  - recent_purchases (high weight)
  - recent_add_to_cart (medium/high intent)
  - recent_reviews (velocity)
  - recent_views (low weight, day-1 realism)
  - avg_rating (low weight quality)
- Tie-breakers:
  - trending_score DESC
  - avg_rating DESC
  - created_at DESC
Reason:
- Purchases drive demand; add-to-cart is intent; views help early-stage; reviews add velocity; rating adds quality without dominating.

### 4) Top Rated sort with minimum review threshold + fallback
Decision:
- “Top Rated” requires `MIN_REVIEWS_TOP_RATED` (default 3).
- If nothing qualifies, fall back to best early ratings and show a UI warning.
Reason:
- Prevent 1 review from dominating and keep day-1 lists populated.

### 5) Engagement events (v1) are minimal and best-effort
Decision:
- Add lightweight `ProductEngagementEvent` model with only VIEW and ADD_TO_CART.
- Logging must never break page/cart flow (best-effort try/except).
- VIEW logging should be throttled to avoid refresh spam.
Reason:
- Early-stage stores need signal; analytics must be safe and low-risk.

## UX decisions
### 6) Early-signal banners
Decision:
- Show warning banners when:
  - Trending has weak signal (no meaningful activity yet)
  - Top Rated cannot meet min review threshold
Reason:
- Transparency builds trust and avoids “this feels broken” impressions.

### 7) Seller gating for purchases on home (UI)
Decision:
- Home cards show Add-to-cart only when seller is Stripe-ready (or owner).
Reason:
- Prevent checkout failures and customer frustration.
Note:
- Server-side enforcement can be added later in cart/checkout.
