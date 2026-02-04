# Refund Flow — Manual Testing Guide

## Prerequisites
- Development server running (`python manage.py runserver`)
- Test database with data
- Stripe test mode keys in `.env`
- Two test user accounts (one buyer, one seller)

---

## Test Scenario 1: Buyer Creates Refund Request (Authenticated)

### Setup
1. Create two test users:
   ```bash
   python manage.py createsuperuser
   # username: testbuyer, email: buyer@test.local, password: testpass123
   
   python manage.py shell
   >>> from django.contrib.auth import get_user_model
   >>> User = get_user_model()
   >>> seller = User.objects.create_user(username='testseller', email='seller@test.local', password='testpass123')
   >>> # Make seller a seller
   >>> from products.permissions import make_seller
   >>> make_seller(seller)
   ```

2. Create a test order with a **physical product**:
   ```bash
   python manage.py shell
   >>> from django.contrib.auth import get_user_model
   >>> from products.models import Product, DigitalAsset
   >>> from orders.models import Order, OrderItem
   >>> from decimal import Decimal
   >>> 
   >>> User = get_user_model()
   >>> buyer = User.objects.get(username='testbuyer')
   >>> seller = User.objects.get(username='testseller')
   >>> 
   >>> # Create physical product
   >>> product = Product.objects.create(
   ...     title="Test 3D Model",
   ...     kind=Product.Kind.PHYSICAL,  # PHYSICAL, not FILE
   ...     price_cents=10000,  # $100.00
   ...     seller=seller,
   ...     requires_shipping=True
   ... )
   >>> 
   >>> # Create order with physical item
   >>> order = Order.objects.create(
   ...     buyer=buyer,
   ...     status=Order.Status.COMPLETED,
   ...     subtotal_cents=10000,
   ...     tax_cents=800,  # $8 tax
   ...     shipping_cents=1000,  # $10 shipping
   ...     total_cents=11800
   ... )
   >>> 
   >>> # Create order item
   >>> item = OrderItem.objects.create(
   ...     order=order,
   ...     product=product,
   ...     seller=seller,
   ...     quantity=1,
   ...     unit_price_cents=10000,
   ...     line_total_cents=10000,
   ...     requires_shipping=True,
   ...     is_digital=False
   ... )
   >>> 
   >>> # Add Stripe payment info
   >>> order.stripe_payment_intent_id = "pi_test_physical_order"
   >>> order.save()
   ```

### Test Steps

**Step 1: Navigate to Order Detail**
- Go to: `http://localhost:8000/orders/{order_id}/`
- Login as buyer (testbuyer / testpass123)
- Should see order with physical product
- Should see "Request Refund" button on the item

**Step 2: Click "Request Refund"**
- Click button → redirects to `/orders/refunds/new/{order_id}/{item_id}/`
- Form should show:
  - **Reason dropdown**: select "Item arrived damaged"
  - **Notes field**: enter "The print quality was poor"
  - (no guest email field since authenticated)
- Click "Submit" button

**Verify:**
- ✅ Redirects back to order detail
- ✅ Success message: "Refund request submitted."
- ✅ RefundRequest created with status=`requested`
- ✅ Check admin: `/admin/refunds/refundrequest/` → see request in list

---

## Test Scenario 2: Guest Creates Refund Request

### Setup
Create an order **without a buyer** (or use guest checkout):

```bash
python manage.py shell
>>> from products.models import Product
>>> from orders.models import Order, OrderItem
>>> 
>>> seller = User.objects.get(username='testseller')
>>> 
>>> # Create guest order (no buyer)
>>> order = Order.objects.create(
...     buyer=None,  # No buyer → guest
...     status=Order.Status.COMPLETED,
...     subtotal_cents=15000,
...     tax_cents=1200,
...     shipping_cents=500,
...     total_cents=16700
... )
>>> 
>>> product = Product.objects.create(
...     title="Guest Purchase Test",
...     kind=Product.Kind.PHYSICAL,
...     price_cents=15000,
...     seller=seller,
...     requires_shipping=True
... )
>>> 
>>> item = OrderItem.objects.create(
...     order=order,
...     product=product,
...     seller=seller,
...     quantity=1,
...     unit_price_cents=15000,
...     line_total_cents=15000,
...     requires_shipping=True,
...     is_digital=False
... )
>>> order.stripe_payment_intent_id = "pi_test_guest_order"
>>> order.save()
```

### Test Steps

**Step 1: Access via Guest Token**
- Go to: `http://localhost:8000/orders/{guest_order_id}/?token={order_token}`
  - *(order_token should be in order.guest_access_token if exists)*
- Or just visit without login: `/orders/{order_id}/`

**Step 2: Request Refund as Guest**
- Click "Request Refund" button
- Form should show:
  - **Guest Email field** (required): enter "guest@example.com"
  - **Reason**: select "Not as described"
  - **Notes**: "Doesn't match product photos"
- Click "Submit"

**Verify:**
- ✅ RefundRequest created with `buyer=None` and `requester_email='guest@example.com'`
- ✅ Can view at `/orders/refunds/{refund_id}/` without login (token verified)

---

## Test Scenario 3: Seller Reviews & Approves Refund

### Test Steps

**Step 1: Seller Views Queue**
- Login as seller (testseller / testpass123)
- Go to: `/orders/refunds/seller/`
- Should see list of pending refund requests with:
  - Product title
  - Status: "Requested"
  - Reason
  - Order number
  - Total amount

**Step 2: Click Into Refund Request**
- Click on the refund → `/orders/refunds/{refund_id}/`
- Should see:
  - Product details
  - Buyer info (or "Guest")
  - Reason and buyer notes
  - **Refund snapshot**:
    - Line: $100.00
    - Tax: $8.00
    - Shipping: $10.00
    - **Total: $118.00**
  - **Approve/Decline buttons** with optional note field

**Step 3: Approve Refund**
- Enter optional note: "Approved - we'll send replacement"
- Click "Approve" button

**Verify:**
- ✅ Status changes to `approved`
- ✅ `seller_decided_at` timestamp set
- ✅ `seller_decision_note` saved with note text
- ✅ Page now shows "Refund in Stripe" button

---

## Test Scenario 4: Seller Triggers Stripe Refund

### Test Steps

**Step 1: Trigger Refund**
- From approved refund detail page
- Click "Refund in Stripe" button
- This calls `trigger_refund()` → creates Stripe refund

**Verify:**
- ✅ No error (check browser console & Django logs)
- ✅ Status changes to `refunded`
- ✅ `refunded_at` timestamp set
- ✅ `stripe_refund_id` populated (starts with `re_`)
- ✅ Page shows green success badge: "Refunded"
- ✅ Displays Stripe refund ID

**Check Stripe Test Dashboard:**
- Go to https://dashboard.stripe.com/test/payments
- Find the payment_intent `pi_test_physical_order`
- Click into it → Refunds tab
- Should see refund listed with amount `$118.00` and status `succeeded`

---

## Test Scenario 5: Seller Declines Refund

### Setup
Create another order + refund request (same as Scenario 1).

### Test Steps

**Step 1: Navigate to New Refund Request**
- Seller views queue again
- Clicks into new refund

**Step 2: Decline**
- Enter optional note: "Item damage was customer's fault"
- Click "Decline" button

**Verify:**
- ✅ Status changes to `declined`
- ✅ `seller_decided_at` and `seller_decision_note` set
- ✅ Page shows info banner (no more action buttons)
- ✅ Buyer can view reason when they check refund status

---

## Test Scenario 6: Digital Product Blocked

### Setup
Create a physical order, then test refund request for a **digital product**.

```bash
python manage.py shell
>>> from products.models import Product, DigitalAsset
>>> from orders.models import Order, OrderItem
>>> 
>>> seller = User.objects.get(username='testseller')
>>> buyer = User.objects.get(username='testbuyer')
>>> 
>>> # Create DIGITAL product
>>> digital_product = Product.objects.create(
...     title="Test STL Model",
...     kind=Product.Kind.FILE,  # DIGITAL
...     price_cents=5000,
...     seller=seller,
...     requires_shipping=False
... )
>>> 
>>> # Add digital asset
>>> asset = DigitalAsset.objects.create(
...     product=digital_product,
...     file=... # set to actual file
... )
>>> 
>>> # Create order
>>> order = Order.objects.create(
...     buyer=buyer,
...     status=Order.Status.COMPLETED,
...     subtotal_cents=5000,
...     tax_cents=0,
...     shipping_cents=0,
...     total_cents=5000
... )
>>> 
>>> item = OrderItem.objects.create(
...     order=order,
...     product=digital_product,
...     seller=seller,
...     quantity=1,
...     unit_price_cents=5000,
...     line_total_cents=5000,
...     requires_shipping=False,
...     is_digital=True
... )
>>> order.stripe_payment_intent_id = "pi_test_digital_order"
>>> order.save()
```

### Test Steps

**Step 1: Try to Request Refund on Digital Item**
- Go to: `/orders/{digital_order_id}/`
- Look for physical items (digital item should NOT have refund button)
- Or try direct URL: `/orders/refunds/new/{digital_order_id}/{digital_item_id}/`

**Verify:**
- ✅ No refund button shown for digital item
- ✅ If accessed directly → error: "Refund requests are only allowed for physical items."

---

## Test Scenario 7: Multi-Item Order Allocation

### Setup
Create an order with **multiple physical items** to test tax/shipping allocation.

```bash
python manage.py shell
>>> from products.models import Product
>>> from orders.models import Order, OrderItem
>>> 
>>> seller = User.objects.get(username='testseller')
>>> buyer = User.objects.get(username='testbuyer')
>>> 
>>> # Create order with 2 items
>>> order = Order.objects.create(
...     buyer=buyer,
...     status=Order.Status.COMPLETED,
...     subtotal_cents=20000,  # $100 item1 + $100 item2
...     tax_cents=1600,        # 8% tax on $200
...     shipping_cents=1000,   # $10 flat
...     total_cents=22600
... )
>>> 
>>> product1 = Product.objects.create(
...     title="Model A",
...     kind=Product.Kind.PHYSICAL,
...     price_cents=10000,
...     seller=seller,
...     requires_shipping=True
... )
>>> 
>>> product2 = Product.objects.create(
...     title="Model B",
...     kind=Product.Kind.PHYSICAL,
...     price_cents=10000,
...     seller=seller,
...     requires_shipping=True
... )
>>> 
>>> item1 = OrderItem.objects.create(
...     order=order,
...     product=product1,
...     seller=seller,
...     quantity=1,
...     unit_price_cents=10000,
...     line_total_cents=10000,
...     requires_shipping=True,
...     is_digital=False
... )
>>> 
>>> item2 = OrderItem.objects.create(
...     order=order,
...     product=product2,
...     seller=seller,
...     quantity=1,
...     unit_price_cents=10000,
...     line_total_cents=10000,
...     requires_shipping=True,
...     is_digital=False
... )
>>> 
>>> order.stripe_payment_intent_id = "pi_test_multi_order"
>>> order.save()
```

### Test Steps

**Step 1: Request Refund for Item 1**
- Go to order detail
- Click refund on **Item A** only
- Submit refund request

**Verify Allocation:**
- ✅ Snapshot shows:
  - Line: $100.00 (full item price)
  - Tax: $8.00 (50% of total tax, since item is 50% of order)
  - Shipping: $5.00 (50% of shipping)
  - **Total: $113.00**

**Step 2: Seller Approves & Refunds**
- Approve refund
- Trigger Stripe refund
- Verify Stripe receives `amount=11300` (cents)

---

## Test Scenario 8: Staff Safety Valve

### Setup
- Create a refund request that's approved but not yet refunded
- Create a staff user:
  ```bash
  python manage.py shell
  >>> User = get_user_model()
  >>> staff = User.objects.create_user(
  ...     username='teststaff',
  ...     email='staff@test.local',
  ...     password='testpass123',
  ...     is_staff=True
  ... )
  ```

### Test Steps

**Step 1: Staff Views Queue**
- Login as staff (teststaff / testpass123)
- Go to: `/orders/refunds/staff/`
- Should see list of refunds (all statuses, last 500)

**Step 2: Force-Trigger Refund**
- Find an approved but unrefunded request
- Click "Refund in Stripe" button

**Verify:**
- ✅ Refund processes even though seller didn't trigger
- ✅ `stripe_refund_id` populated
- ✅ Status → `refunded`

**Alternative: Admin Action**
- Go to `/admin/refunds/refundrequest/`
- Filter by status=`approved`
- Select checkbox for one refund
- Action dropdown → "Trigger Stripe refund (DANGEROUS)"
- Click "Go"

**Verify:**
- ✅ Refund processed
- ✅ Success message shown

---

## Troubleshooting

| Issue | Check |
|-------|-------|
| "Refund requests are only allowed for physical items" | Ensure `requires_shipping=True` and `is_digital=False` on OrderItem |
| "Order has no Stripe payment intent id" | Set `order.stripe_payment_intent_id = "pi_test_..."` in shell |
| Buyer can't see refund button | Order status must be `COMPLETED`; item must be physical |
| Seller doesn't see queue | Ensure user is marked as seller via `make_seller()` |
| Stripe refund fails | Check Stripe test mode keys in `.env`; check payment_intent exists in Stripe dashboard |
| Allocation math wrong | Review allocation formula in [refunds/services.py#L22-L88](refunds/services.py#L22-L88) |

---

## Success Criteria

After testing all scenarios, you should have verified:

- ✅ Buyer can create refund request (authenticated)
- ✅ Guest can create refund request (with email confirmation)
- ✅ Seller receives and views requests in queue
- ✅ Seller can approve/decline with optional notes
- ✅ Seller can trigger Stripe refund after approval
- ✅ Refund snapshot amounts calculated correctly
- ✅ Tax/shipping allocated proportionally in multi-item orders
- ✅ Digital products blocked from refunds
- ✅ Stripe refund created with idempotency key
- ✅ Status transitions: requested → approved → refunded
- ✅ Staff can override via safety-valve
- ✅ Admin action works for force-triggering

Once all pass, refund flow is **production-ready** ✅
