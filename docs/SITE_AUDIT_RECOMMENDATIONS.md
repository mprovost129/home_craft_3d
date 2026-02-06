# Home Craft 3D — Site Audit & Recommendations (Feb 5, 2026)

## Scope
High‑level UX, content, and technical review across major user flows (buyer, seller, admin, legal, payments).

---
## Global UI/UX
- Establish a single primary CTA per page (avoid competing actions).
- Normalize heading hierarchy (one H1 per page; section headers H2/H3).
- Reduce card metadata density (seller + category + badges + ratings is heavy).
- Add trust strip site‑wide: Secure payments • Instant downloads • Buyer protection.
- Standardize empty states (e.g., “No reviews” → “New listing” or hide line).
- Ensure consistent button hierarchy (primary/danger/secondary usage).

## Home Page
- Hero: one primary CTA (Browse All or Start Selling) and a smaller secondary.
- Add short value proposition under hero (“3D prints & digital files from vetted makers”).
- Trending/Just Added/Featured: add category filter chips for quick discovery.
- Top Sellers: replace generic link with seller cards (avatar, rating, sales count).
- Ensure above‑the‑fold content shows 1–2 real products with ratings to build trust.

## Product Listing Pages (All Products / Models / Files)
- Show category hierarchy in a compact line (already implemented).
- Consider hiding seller rating line when zero (reduces noise).
- Add “License type” badge for digital files if provided.
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
- Highlight custom instructions (buyer notes) in cart line items.
- Add “Continue shopping” CTA.
- Show fee breakdown (platform fee visible to seller only).

## Checkout
- Add order preview with thumbnails.
- Clarify that digital downloads are delivered instantly post‑payment.
- Validate buyer notes length and show remaining character count.

## Buyer Orders / Purchases
- Add “Download all” button for digital orders.
- Show order status timeline for physical items.
- Provide quick contact seller option from order detail.

## Seller Dashboard / Listings
- Add a progress checklist per listing (Images ✓, Specs ✓, Assets ✓, Active ✓).
- Add “Preview listing” button.
- Add bulk actions for activate/deactivate.
- Add a warning if specs are empty when listing is active.

## Seller Orders / Fulfillment
- Surface buyer instructions more prominently (already added; consider card header).
- Add copy‑to‑clipboard for tracking number.
- Allow adding tracking carrier from a dropdown.

## Payments / Stripe Payouts
- Replace “MVP note” with “Stripe setup status” (already updated).
- Add a plain‑language summary: “You can sell when all three are green.”
- Display last payout date if available.

## Legal
- Fees & payouts now mention 7.5%. Consider adding a separate “Seller Fees” page with examples.
- Add plain‑language TL;DR at top of Terms and Refund.

## Performance & Technical
- Ensure images are WebP where possible and lazy‑load below the fold.
- Add CDN cache headers for static images/assets.
- Add category parent to select_related (already done).
- Consider server‑side caching for home page sections.

## Accessibility
- Ensure all icon‑only buttons have aria‑labels.
- Maintain color contrast for badges and small text.
- Add focus outlines for interactive elements.

---
## Priority (Next 2–4 weeks)
1) Home hero CTA clarity + Top Sellers real cards
2) Product detail “What you get” + license clarity
3) Seller listing checklist + warnings
4) Cart/checkout clarity for digital delivery

---
## Optional Enhancements
- Add “Collections” and “Bundles” browsing.
- Seller storefront customization (banner + featured items).
- Reviews: highlight photo reviews or “verified purchase” badges.
