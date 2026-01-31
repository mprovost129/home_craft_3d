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
