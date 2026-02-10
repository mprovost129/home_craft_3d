from __future__ import annotations

"""
Central throttle policy for Home Craft 3D.

Use these rules across the app so launch-hardening changes are consistent.
The throttle fingerprint includes (best-effort) client IP, short UA prefix, and user id (if authenticated).
"""

from core.throttle import ThrottleRule

# Auth / account
AUTH_LOGIN = ThrottleRule(key_prefix="auth:login", limit=10, window_seconds=60)
AUTH_REGISTER = ThrottleRule(key_prefix="auth:register", limit=6, window_seconds=60)
AUTH_PASSWORD_RESET = ThrottleRule(key_prefix="auth:pwreset", limit=6, window_seconds=60)

# Cart / checkout
CART_MUTATE = ThrottleRule(key_prefix="cart:mutate", limit=30, window_seconds=60)
CHECKOUT_START = ThrottleRule(key_prefix="checkout:start", limit=10, window_seconds=60)

# Q&A
QA_THREAD_CREATE = ThrottleRule(key_prefix="qa:thread:create", limit=12, window_seconds=60)
QA_MESSAGE_REPLY = ThrottleRule(key_prefix="qa:reply", limit=20, window_seconds=60)
QA_REPORT = ThrottleRule(key_prefix="qa:report", limit=10, window_seconds=60)
QA_DELETE = ThrottleRule(key_prefix="qa:delete", limit=15, window_seconds=60)

# Reviews
REVIEW_CREATE = ThrottleRule(key_prefix="reviews:create", limit=8, window_seconds=60)
REVIEW_REPLY = ThrottleRule(key_prefix="reviews:reply", limit=20, window_seconds=60)

# Refunds / sensitive actions
REFUND_REQUEST = ThrottleRule(key_prefix="refunds:request", limit=6, window_seconds=60)
REFUND_TRIGGER = ThrottleRule(key_prefix="refunds:trigger", limit=6, window_seconds=60)

# Seller listing mutations (activate/publish/upload)
SELLER_MUTATE = ThrottleRule(key_prefix="seller:mutate", limit=25, window_seconds=60)

# Downloads (GET endpoints) – keep modest to avoid scraping
DOWNLOAD = ThrottleRule(key_prefix="downloads:get", limit=30, window_seconds=60)

# Category dependent dropdown / lookup
CATEGORY_LOOKUP = ThrottleRule(key_prefix="category:lookup", limit=120, window_seconds=60)

# Refund decisions (approve/decline)
REFUND_DECIDE = ThrottleRule(key_prefix="refunds:decide", limit=15, window_seconds=60)
