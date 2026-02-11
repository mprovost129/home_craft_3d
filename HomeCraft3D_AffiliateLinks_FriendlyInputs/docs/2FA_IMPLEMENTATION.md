# Admin 2FA Security Implementation Guide

## Overview
This document describes the implementation of Two-Factor Authentication (2FA) for admin/superuser accounts using django-otp with TOTP (Time-based One-Time Password).

## Architecture

### Components
1. **django-otp**: Provides TOTP device management and token verification
2. **qrcode**: Generates QR codes for easy authenticator app setup
3. **StaticDevice**: Stores the TOTP secret key and tracks confirmation status
4. **StaticToken**: Stores recovery codes for account recovery
5. **OTPMiddleware**: Injects OTP device info into requests for decorator validation

### Security Features
- ✅ TOTP-based authentication (30-second time windows)
- ✅ 10 recovery codes per user (single-use)
- ✅ Backup code generation and display
- ✅ QR code scanning for easy setup
- ✅ Recovery code regeneration capability
- ✅ Password confirmation for 2FA disabling
- ✅ Device confirmation (2FA only active after token verification)

## Implementation Details

### Database Schema
```
StaticDevice (django_otp)
├── user (FK to User)
├── name (CharField: 'default')
├── key (CharField: 20 hex chars - the secret)
├── confirmed (Boolean: True after first login)
└── created (DateTime)

StaticToken (django_otp)
├── device (FK to StaticDevice)
└── token (CharField: recovery code)
```

### Configuration
**config/settings/base.py**
```python
INSTALLED_APPS += [
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
]

MIDDLEWARE.insert(
    MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware") + 1,
    "django_otp.middleware.OTPMiddleware",
)
```

### Views & URLs
**accounts/urls.py**
```
/accounts/2fa/setup/              - Setup wizard with QR code and recovery codes
/accounts/2fa/status/             - View current 2FA status
/accounts/2fa/disable/            - Disable 2FA (requires password)
/accounts/2fa/recovery-codes/     - Show existing recovery codes
/accounts/2fa/regenerate-codes/   - Generate new recovery codes
```

### Templates
1. **setup_2fa.html** - Step-by-step setup with QR code display and backup code storage
2. **2fa_status.html** - Dashboard showing 2FA status and options
3. **recovery_codes.html** - List and management of recovery codes
4. **disable_2fa.html** - Confirmation form for disabling 2FA

## Usage

### For Users

#### Enable 2FA
1. Visit `/accounts/2fa/status/`
2. Click "Enable 2FA Now"
3. Scan QR code with authenticator app (Google Authenticator, Microsoft Authenticator, Authy, etc.)
4. Save recovery codes in secure location
5. Enter 6-digit code to confirm
6. 2FA is now active

#### Recovery
1. Visit `/accounts/2fa/recovery-codes/` (while logged in)
2. Use one of the recovery codes to regain access if authenticator is lost
3. Each code can only be used once

#### Disable 2FA
1. Visit `/accounts/2fa/status/`
2. Click "Disable 2FA"
3. Confirm password
4. 2FA is disabled (not recommended)

### For Admins

#### Initialize 2FA for All Superusers
```bash
python manage.py enable_admin_2fa
```

Output includes:
- Secret key for manual entry
- QR code (as base64 data URI)
- 10 recovery codes
- Setup instructions

#### Initialize 2FA for Specific User
```bash
python manage.py enable_admin_2fa username
```

#### Force Regeneration
```bash
python manage.py enable_admin_2fa --force
```
(Regenerates new secret and recovery codes)

#### Generate QR Code for Display
```bash
python manage.py enable_admin_2fa username | grep "data:image"
```

## Security Considerations

### Strengths
1. **Time-based tokens**: Not based on SMS (vulnerable to SIM swap)
2. **Recovery codes**: 10 codes provide fallback access
3. **Single-use tokens**: Each recovery code used only once
4. **Device confirmation**: 2FA only active after verification
5. **Offline-capable**: No internet required after app setup
6. **Standard protocol**: TOTP is RFC 6238 compliant, supported by all major authenticator apps

### Limitations
1. **Token expiry**: TOTP tokens valid for 30 seconds only
2. **Backup codes must be secure**: If lost, user loses account recovery option
3. **Authenticator app loss**: User must use recovery codes or admin reset
4. **No SMS/Email fallback**: This is intentional (more secure but less flexible)

### Recommended Policies
- ✅ Require 2FA for all admin/superuser accounts
- ✅ Require users to save recovery codes during setup
- ✅ Periodically regenerate recovery codes
- ✅ Disable 2FA only with manual admin intervention
- ✅ Log all 2FA changes to audit trail
- ✅ Store recovery codes in secure password manager

## Testing

### Automated Test
```bash
python manage.py shell < test_2fa_flow.py
```

Tests:
- ✓ Device creation and configuration
- ✓ Recovery code generation
- ✓ TOTP token generation
- ✓ Token verification
- ✓ 2FA enable/disable flow
- ✓ Recovery code validation
- ✓ Endpoint accessibility

### Manual Testing
1. **Setup**: Visit `/accounts/2fa/setup/` as a user
2. **Scan QR Code**: Use authenticator app to scan QR code
3. **Verify Token**: Enter 6-digit token from app
4. **Login**: Use recovery code to test fallback access
5. **Disable**: Follow disable flow with password confirmation

## Production Deployment

### Pre-Launch Checklist
- [ ] Run migrations: `python manage.py migrate`
- [ ] Install dependencies: `pip install -r requirements.txt`
- [ ] Test 2FA setup flow with real authenticator app
- [ ] Initialize 2FA for all admin accounts: `python manage.py enable_admin_2fa`
- [ ] Store recovery codes in secure location (password manager or safe)
- [ ] Document 2FA procedures for team
- [ ] Add 2FA status to admin onboarding docs
- [ ] Test account recovery with recovery codes
- [ ] Backup recovery codes before going live

### Configuration
```python
# settings/prod.py
# OTP settings (optional, defaults are secure)
OTP_TOTP_ISSUER = "Home Craft 3D"  # Shows in authenticator app
```

### Optional Enhancements
1. **Require 2FA for all staff**: Use `@otp_required` decorator on admin views
2. **Email notifications**: Send emails when 2FA is enabled/disabled
3. **Audit logging**: Log all 2FA changes with timestamps and IPs
4. **Recovery code email**: Email recovery codes instead of displaying
5. **Backup codes in database**: Store encrypted recovery codes

## Troubleshooting

### "Invalid Token" After Setup
- Ensure device clock is synchronized
- Check that token isn't expired (valid for 30 seconds only)
- Verify correct secret key is used in authenticator app
- Clear browser cache and try again

### Lost Recovery Codes
- Admin can regenerate: `python manage.py enable_admin_2fa username --force`
- User can regenerate in `/accounts/2fa/regenerate-codes/` (if logged in)
- Last resort: Admin manually deletes device in admin panel

### Lost Authenticator App
- Use recovery codes to login
- Visit `/accounts/2fa/setup/` to add new authenticator app
- Generate new recovery codes

### Token Won't Verify
- Check that TOTP window tolerance is correct (default ±1 window)
- Verify `TIME_STEP` is 30 seconds (standard)
- Check server time synchronization with NTP

## Dependencies Added

```requirements.txt
django-otp>=1.3,<2          # 2FA device and token management
qrcode[pil]>=8.1,<9         # QR code generation for authenticator setup
```

## Files Modified/Created

### Modified
- `config/settings/base.py` - Added django_otp apps and middleware
- `requirements.txt` - Added django-otp and qrcode dependencies
- `accounts/urls.py` - Added 2FA URL routes

### Created
- `accounts/views_2fa.py` - 2FA setup, status, and management views
- `accounts/forms_2fa.py` - TOTP verification and disable forms
- `accounts/templates/accounts/setup_2fa.html` - QR code and backup codes
- `accounts/templates/accounts/2fa_status.html` - 2FA status dashboard
- `accounts/templates/accounts/recovery_codes.html` - Recovery code display
- `accounts/templates/accounts/disable_2fa.html` - 2FA disable form
- `accounts/management/commands/enable_admin_2fa.py` - Admin 2FA setup command
- `test_2fa_flow.py` - Comprehensive 2FA test script

## Next Steps

1. **Run migrations**: `python manage.py migrate` (creates django_otp tables)
2. **Setup admin 2FA**: `python manage.py enable_admin_2fa`
3. **Test flow**: `python manage.py shell < test_2fa_flow.py`
4. **Update profile page**: Add link to 2FA management from user profile
5. **Document**: Add 2FA instructions to user documentation
6. **Require 2FA**: (Optional) Use `@otp_required` decorator to enforce 2FA on admin views

## Additional Resources

- [django-otp documentation](https://django-otp-official.readthedocs.io/)
- [TOTP RFC 6238](https://tools.ietf.org/html/rfc6238)
- [Authenticator Apps](https://en.wikipedia.org/wiki/Time-based_one-time_password#Applications)
