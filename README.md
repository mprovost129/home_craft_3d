# Home Craft 3D

A Django-based marketplace for 3D printing enthusiasts to buy and sell 3D models and physical prints.

## Features

- **Multi-role system**: Buyers, Sellers, and Admins
- **Product types**: Digital files (STL, etc.) and physical 3D prints
- **Stripe Connect**: Seller payouts via Stripe Express accounts
- **Reviews & Ratings**: Product reviews with seller responses
- **Q&A System**: Product questions and answers
- **Refund Management**: Structured refund request and approval workflow
- **Legal Documents**: Versioned Terms, Privacy, Refund, and Content policies
- **Dashboard**: Role-specific dashboards for buyers, sellers, and admins
- **Shopping Cart**: Session-based cart with checkout flow

## Tech Stack

- **Django 5.1.15**
- **PostgreSQL** for database
- **Stripe** for payments and Connect
- **WhiteNoise** for static file serving
- **Gunicorn** for production WSGI server
- **Bootstrap 5** for frontend (via CDN)

## Project Structure

```
home_craft_3d/
├── accounts/         # User authentication, profiles, registration
├── cart/            # Shopping cart functionality
├── catalog/         # Product categories
├── config/          # Django settings and main URLs
├── core/            # Core app with homepage, settings, middleware
├── dashboards/      # Role-based dashboards
├── legal/           # Legal documents (terms, privacy, etc.)
├── orders/          # Order processing and management
├── payments/        # Stripe integration and Connect onboarding
├── products/        # Product listings, images, assets
├── qa/              # Q&A system for products
├── refunds/         # Refund request management
├── reviews/         # Product reviews and ratings
├── static/          # Static assets (CSS, JS, images)
├── templates/       # Base templates
└── manage.py        # Django management script
```

## Setup

### 1. Clone and Install

```bash
git clone https://github.com/mprovost129/home_craft_3d.git
cd home_craft_3d
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

**Required variables:**
- `DJANGO_SECRET_KEY` - Generate with `python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'`
- `STRIPE_SECRET_KEY` - Get from https://dashboard.stripe.com/test/apikeys
- `STRIPE_PUBLIC_KEY` - Get from https://dashboard.stripe.com/test/apikeys
- `SITE_BASE_URL` - Your site URL (e.g., `http://127.0.0.1:8000` for local)

**Database (PostgreSQL):**
- `POSTGRES_DB=home_craft_3d`
- `POSTGRES_USER=hc3user`
- `POSTGRES_PASSWORD=homecraftpass!`
- `POSTGRES_HOST=localhost`
- `POSTGRES_PORT=5432`

### 3. Database Setup

```bash
# Create PostgreSQL database
createdb home_craft_3d

# Run migrations
python manage.py makemigrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser
```

### 4. Run Development Server

```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000`

## Deployment (Render)

### Environment Variables on Render

Set these in your Render dashboard:

```
DJANGO_SECRET_KEY=<your-secret-key>
DEBUG=False
ALLOWED_HOSTS=homecraft3d.onrender.com,your-custom-domain.com
CSRF_TRUSTED_ORIGINS=https://homecraft3d.onrender.com,https://your-custom-domain.com
DATABASE_URL=<postgres-connection-string>
STRIPE_SECRET_KEY=<your-live-stripe-secret-key>
STRIPE_PUBLIC_KEY=<your-live-stripe-public-key>
STRIPE_WEBHOOK_SECRET=<your-webhook-secret>
STRIPE_CONNECT_WEBHOOK_SECRET=<your-connect-webhook-secret>
SITE_BASE_URL=https://homecraft3d.onrender.com
```

### Build Command

```bash
pip install -r requirements.txt && python manage.py collectstatic --no-input && python manage.py migrate
```

### Start Command

```bash
gunicorn config.wsgi:application
```

## Key Workflows

### Seller Onboarding

1. User registers with "Register as seller" checkbox checked
2. System redirects to Stripe Connect onboarding
3. User completes Stripe Express account setup
4. Returns to platform, ready to sell

### Product Listing

1. Seller creates product with details, pricing
2. Uploads images and digital assets (if applicable)
3. Sets product as active
4. Product appears in marketplace

### Checkout Flow

1. Buyer adds products to cart
2. Proceeds to checkout
3. Stripe Payment Intent created
4. Payment processed
5. Order created, digital downloads available
6. Seller receives notification

### Refund Process

1. Buyer requests refund from order page
2. Seller reviews and approves/denies
3. If approved, Stripe refund processed
4. Buyer and seller balances updated

## Admin Tasks

```bash
# Seed demo products (for testing)
python manage.py seed_demo_products

# Prune old engagement events
python manage.py prune_engagement_events --days=90
```

## Testing

```bash
# Run tests
python manage.py test

# Run specific app tests
python manage.py test accounts
python manage.py test products
```

## Security Notes

- ✅ HTTPS enforced in production via `SECURE_SSL_REDIRECT`
- ✅ HSTS headers enabled with 1-year duration
- ✅ CSRF protection enabled
- ✅ Secure cookies in production
- ✅ WhiteNoise for secure static file serving
- ✅ User passwords hashed with Django's default (PBKDF2)
- ⚠️ **Never commit `.env` file or secrets to git**
- ⚠️ **Use test Stripe keys for development**

## License

Proprietary - All rights reserved

## Support

For questions or issues, contact: mprovost129@gmail.com
