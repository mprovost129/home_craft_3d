# Home Craft 3D — MEMORY

Last updated: 2026-01-31 (America/New_York)

## What the app is
Home Craft 3D is a marketplace for:
- **Physical 3D printed models** (shipped by sellers)
- **Digital 3D print files** (downloadable assets)

Users have public usernames. Logged-out users can browse. Registration supports consumer or seller roles. Owner/admin can access all areas.

## Storefront UX structure (current)
Public home page shows 4 buckets:
- **Featured** (manual flag: `Product.is_featured`)
- **New** (most recent active)
- **Trending** (manual override + computed fill)
- **Misc** (everything else not shown above)

Browse pages:
- Browse Products (all)
- Browse 3D Models (physical)
- Browse 3D Files (digital)

## “Credibility signals” added
### Ratings on cards (no per-card DB queries)
We annotate product querysets with:
- `avg_rating`
- `review_count`

Templates render these on:
- Home cards
- Browse product cards
- “More like this” cards on product detail

### Trending badge normalization
Templates only check:
- `p.trending_badge`

Views set:
- badge True if `product.is_trending` OR product in computed-trending set.

### Browse sort controls
Browse includes sort mode:
- `new` (default)
- `trending`
- `top` (Top Rated)

Browse shows banners for early-stage behavior:
- Trending fallback banner when signal is weak
- Top Rated fallback banner when min review threshold can’t be met

## Trending computation (current)
Trending uses signals within a rolling window (default 30 days):
- Recent paid purchases
- Recent reviews
- Engagement events: recent views + add-to-cart
- Avg rating (low weight)

Tie-breakers:
- trending_score DESC
- avg_rating DESC
- created_at DESC

Manual override:
- `Product.is_trending=True` forces inclusion on home Trending bucket.
Computed fills remaining slots.

## Engagement events (v1) — IMPLEMENTED
Model:
- `ProductEngagementEvent` with:
  - `VIEW`
  - `ADD_TO_CART`

Logging:
- Product detail logs `VIEW` (throttled per session per product)
- Cart add logs `ADD_TO_CART` (best-effort; won’t break cart)

Purpose:
- Make Trending feel “real” on day 1 even with low sales volume.

## Stripe readiness gating on home
Home cards have `p.can_buy`:
- True if seller Stripe account is ready, OR owner user

Used to disable Add-to-cart buttons for sellers not onboarded.
Note: server-side enforcement can be added later in cart/checkout.

## Templates touched recently
- `templates/core/home.html`: Trending badge + rating display + can_buy gating
- `templates/products/product_list.html`: sort controls, badge, rating display, early-signal notices
- `templates/products/product_detail.html`: rating header, reviews, “more like this” shows badges + rating

## Known constraints / principles
- Avoid N+1 queries in templates: prefer queryset annotations + prefetch/select_related.
- Prefer unified template rules (e.g., `p.trending_badge`) to prevent drift across templates.
- Day-1 “realness”: trending/top-rated should not look empty even with low data.
