## Authentication
- Use **Django default User model**
- Username-based login (no email login)
- Public usernames

## Authorization Model
- Roles implemented as **capabilities**, not separate user tables
- Owner/Admin override permissions across all dashboards
- Implement roles via `accounts.Profile`:
  - `is_seller`
  - `is_owner`
  - plus `user.is_staff` / `user.is_superuser`

## Accounts MVP (Implemented)
- `accounts.Profile` extends default User via OneToOne
- Profile stores:
  - contact fields (email, phones, address)
  - avatar
  - role flags
  - Stripe onboarding placeholders (`stripe_account_id`, `stripe_onboarding_complete`)

## Product Architecture
- Two distinct product types:
  1. PhysicalModelProduct – printed & shipped by seller
  2. DigitalFileProduct – downloadable files
- Shared abstract/base product fields where appropriate

## Categories (Implemented)
- Use a single `catalog.Category` model with:
  - `type` to separate trees (`MODEL` vs `FILE`)
  - `parent` self-FK for hierarchy
  - `sort_order` for sidebar ordering
- Provide category trees to templates using a context processor:
  - `catalog.context_processors.sidebar_categories`

## Payments
- Stripe Checkout for purchases
- Mandatory Stripe onboarding for sellers
- Platform does not print or ship products itself

## Admin Strategy
- Primary admin control via **custom web admin dashboard**
- Django admin used only as backup/emergency
- Web admin mirrors and controls site-wide settings

## Public Pages
- Public-facing pages live in a dedicated `core` app
- Root URL (`/`) renders a logged-out home/landing page
- Authenticated users may still access public pages

## Documentation Rule (Enforced)
- After **every code change**, update:
  - docs/MEMORY.md
  - docs/DECISIONS.md
  - docs/ROADMAP.md
