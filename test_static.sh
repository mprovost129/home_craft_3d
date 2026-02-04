#!/bin/bash
# Test static files in production-like mode (Windows: use in Git Bash or WSL)

echo "=== Static Files Production Test ==="
echo ""

# Step 1: Collect static files
echo "Step 1: Collecting static files..."
python manage.py collectstatic --noinput --clear
if [ $? -ne 0 ]; then
    echo "ERROR: collectstatic failed"
    exit 1
fi
echo "✓ Static files collected to staticfiles/"
echo ""

# Step 2: Warn about DEBUG setting
echo "Step 2: Testing with DEBUG=False"
echo "⚠️  Make sure DEBUG=False is set in your .env file"
echo "   Current DEBUG setting will be used from .env"
echo ""

# Step 3: Start gunicorn
echo "Step 3: Starting gunicorn on http://127.0.0.1:8000"
echo "   Press Ctrl+C to stop"
echo ""
echo "=== MANUAL TESTING CHECKLIST ==="
echo "1. Open http://127.0.0.1:8000 in browser"
echo "2. Check CSS loads (colors, layout correct)"
echo "3. Click theme toggle (dark/light mode)"
echo "4. Check navbar icons load"
echo "5. Check product images load"
echo "6. Check Bootstrap JS works (dropdowns, collapse)"
echo "7. Open browser DevTools (F12) → Network tab"
echo "8. Verify no 404s for CSS/JS/images"
echo ""

# Start gunicorn
gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 2 --timeout 60
