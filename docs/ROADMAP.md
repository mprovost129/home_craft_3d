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
