from __future__ import annotations

# payments/permissions.py
#
# Backwards-compatible re-export.
# Canonical implementation lives in payments.decorators.

from .decorators import stripe_ready_required

__all__ = ["stripe_ready_required"]
