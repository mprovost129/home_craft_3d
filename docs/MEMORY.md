# Home Craft 3D — MEMORY

Last updated: 2026-01-31 (America/New_York)

## Goal
A working marketplace for:
- Physical 3D printed models (shipped by sellers)
- Digital 3D print files (downloadable assets)

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
