# Home Craft 3D — ROADMAP

Last updated: 2026-01-31 (America/New_York)

## Phase 1 — Storefront credibility (DONE / IN PROGRESS)
✅ Ratings on cards (home + browse + detail “more like this”) using queryset annotations  
✅ Trending sort mode + Top Rated sort mode on browse  
✅ Trending badge normalization via `p.trending_badge` rule  
✅ Trending computation on home (manual override + computed fill)  
✅ Early-signal warnings for Trending and Top Rated  
✅ Engagement model added: `ProductEngagementEvent` (VIEW, ADD_TO_CART)  
✅ Engagement logging:
- ✅ ADD_TO_CART logged in `cart.views.cart_add`
- ✅ VIEW logged in `products.views.product_detail` (throttled)

## Phase 2 — Engagement events v1 (COMPLETE once merged)
- [ ] Verify migrations applied for `ProductEngagementEvent`
- [ ] Confirm VIEW throttle works (refresh does not spam events)
- [ ] Confirm Trending changes after events accumulate

## Phase 3 — Buyer trust + conversion (NEXT)
- [ ] Category browse improvements (filters, breadcrumbs)
- [ ] Search refinements (boosting, better tokenization)
- [ ] Better “More like this” similarity (category + tags later)
- [ ] Product detail improvements (license info, file list, physical specs)
- [ ] Server-side enforcement: block add-to-cart/checkout for non-ready sellers

## Phase 4 — Seller growth
- [ ] Seller listing workflow polish (drafts, validation, media requirements)
- [ ] Seller analytics dashboard (views, add-to-cart, sales)
- [ ] Seller onboarding friction reduction

## Phase 5 — Operations + safety
- [ ] Moderation / reporting
- [ ] Audit logs
- [ ] Fraud/abuse rate limiting and anomaly detection

## Phase 6 — Launch hardening
- [ ] Observability + error reporting
- [ ] Backups
- [ ] Performance budgets
