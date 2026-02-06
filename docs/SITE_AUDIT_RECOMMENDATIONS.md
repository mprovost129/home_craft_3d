# Home Craft 3D — Site Audit & Recommendations (Feb 5, 2026)

## Scope
High‑level UX, content, and technical review across major user flows (buyer, seller, admin, legal, payments).

---
## Global UI/UX
- Establish a single primary CTA per page (avoid competing actions).
- Normalize heading hierarchy (one H1 per page; section headers H2/H3).
- Reduce card metadata density (seller + category + badges + ratings is heavy).
- Ensure consistent button hierarchy (primary/danger/secondary usage).

## Home Page
- Hero: one primary CTA (Browse All or Start Selling) and a smaller secondary.
- Add short value proposition under hero (“3D prints & digital files from vetted makers”).
- Trending/Just Added/Featured: add category filter chips for quick discovery.
- Top Sellers: replace generic link with seller cards (avatar, rating, sales count).
- Ensure above‑the‑fold content shows 1–2 real products with ratings to build trust.

## Product Listing Pages (All Products / Models / Files)
- Add “Ships from” for physical models (if data exists) and lead time.
- Add sort rationale tooltips (Trending vs Top Rated).

## Product Detail Page
- Add a clear “What you get” section (files list + license summary).
- Include a sticky purchase panel for desktop.
- Surface seller response time or fulfillment expectations.
- Add a mini FAQ accordion under specs.
- Show related items by same seller and same category.

## Cart
- Show a summary of digital license type and file formats inline.
- Show fee breakdown (platform fee visible to seller only).

## Checkout
- Add order preview with thumbnails.
- Clarify that digital downloads are delivered instantly post‑payment.

## Buyer Orders / Purchases
## Buyer Orders / Purchases

## Seller Dashboard / Listings
## Seller Dashboard / Listings
- Add a progress checklist per listing (Images ✓, Specs ✓, Assets ✓, Active ✓).
- Add bulk actions for activate/deactivate.

## Seller Orders / Fulfillment
## Payments / Stripe Payouts
- Add a plain‑language summary: “You can sell when all three are green.”
- Display last payout date if available.

## Legal
- Fees & payouts now mention 7.5%. Consider adding a separate “Seller Fees” page with examples.
- Add plain‑language TL;DR at top of Terms and Refund.

## Performance & Technical
- Ensure images are WebP where possible and lazy‑load below the fold.
- Add CDN cache headers for static images/assets.
- Consider server‑side caching for home page sections.

## Accessibility
- Ensure all icon‑only buttons have aria‑labels.
- Maintain color contrast for badges and small text.
- Add focus outlines for interactive elements.

---
## Priority (Next 2–4 weeks)
1) Home hero CTA clarity + Top Sellers real cards
2) Product detail “What you get” + license clarity
3) Seller listing checklist
4) Cart/checkout clarity for digital delivery

---
## Optional Enhancements
- Add “Collections” and “Bundles” browsing.
- Seller storefront customization (banner + featured items).
- Reviews: highlight photo reviews or “verified purchase” badges.
