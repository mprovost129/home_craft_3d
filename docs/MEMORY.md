## Project Identity
- **Project name:** Home Craft 3D
- **Product type:** Online marketplace
- **What is sold:**
  - Physical **3D printed models** (printed & shipped by sellers)
  - **Digital 3D print files** (STL, OBJ, 3MF, etc.)

## Users & Roles
- **Logged-out users:**
  - Treated as consumers by default
  - Can browse marketplace without registering
- **Registered users:**
  - Username-based authentication
  - Usernames are public and visible across the site
- **Roles:**
  - Consumer (default)
  - Seller (requires Stripe onboarding)
  - Owner/Admin (full permissions)
- **Owner/Admin (Michael):**
  - Has access to **admin dashboard**, **seller dashboard**, and **consumer dashboard** simultaneously

## Core UX Layout
- **Global layout:**
  - Navbar (logo left, menu center, auth/profile right)
  - Sidebar (expandable categories)
  - Footer
- **Sidebar:**
  - Separate category trees for:
    - Physical models
    - Digital files
  - Expand/collapse with arrows

## Homepage
- Public landing page for all visitors
- Grid-based cards including:
  - Featured items
  - New items
  - Trending items
  - Miscellaneous / curated sections

## Profiles
- Profile fields (private unless used by system):
  - Username (public)
  - First name, last name
  - Email (used for comms)
  - Phone 1, Phone 2
  - Address 1, Address 2
  - City, State (dropdown), ZIP
  - Profile picture

## Platform Features
- Product detail pages
- Reviews & ratings
- “More like this item” recommendations
- Chat / Q&A system
- Email notifications & verification
- reCAPTCHA v3 on all forms
- Terms & Conditions
- Privacy Policy
- FAQ / Help pages
- Cart with Stripe Checkout
- Mandatory Stripe onboarding for sellers

## Current Implementation Status
- Accounts MVP implemented:
  - Registration with “register as seller” toggle
  - Username/password login/logout
  - Profile edit page with full contact fields
  - Profile auto-created via signals
- Public home page implemented:
  - Root URL `/` serves a logged-out landing page
  - Users may browse without registering
- Categories MVP implemented:
  - `catalog.Category` supports two separate trees:
    - 3D Models categories
    - 3D Files categories
  - Parent/child hierarchy supports expandable sidebar structure
  - `/catalog/` browse page exists (placeholder styling for now)
