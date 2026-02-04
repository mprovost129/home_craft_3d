"""Views for two-factor authentication management."""
import io
import qrcode
from base64 import b64encode
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.util import random_hex
from .forms_2fa import TOTPVerificationForm, RecoveryCodeForm, Disable2FAForm


@login_required
@require_http_methods(['GET', 'POST'])
def setup_2fa(request):
    """
    Setup two-factor authentication for the current user.
    GET: Display QR code and recovery codes
    POST: Verify TOTP token to enable 2FA
    """
    user = request.user
    
    # Check if user already has 2FA enabled
    if user.totpdevice_set.filter(confirmed=True).exists():
        messages.info(request, '2FA is already enabled for your account.')
        return redirect('view_2fa_status')
    
    if request.method == 'GET':
        # Generate new device if not exists or not confirmed
        device, created = TOTPDevice.objects.get_or_create(
            user=user,
            name='default',
            defaults={'confirmed': False}
        )
        
        # Generate secret key if not exists
        if not device.key:
            device.key = random_hex(20)
            device.save()
        
        # Generate or reuse backup codes
        recovery_device, _ = StaticDevice.objects.get_or_create(
            user=user,
            name='recovery'
        )
        backup_codes = list(recovery_device.token_set.all().values_list('token', flat=True))
        if not backup_codes:
            for i in range(10):
                token = StaticToken.random_token()
                StaticToken.objects.create(device=recovery_device, token=token)
                backup_codes.append(token)
        
        # Generate QR code
        totp_string = device.config_url
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(totp_string)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        qr_code_base64 = b64encode(buffer.getvalue()).decode()
        
        context = {
            'device': device,
            'qr_code': qr_code_base64,
            'backup_codes': backup_codes,
            'totp_url': totp_string,
        }
        return render(request, 'accounts/setup_2fa.html', context)
    
    elif request.method == 'POST':
        form = TOTPVerificationForm(request.POST)
        if form.is_valid():
            token = form.cleaned_data['token']
            device = TOTPDevice.objects.get(user=user, name='default')
            
            # Verify token
            if device.verify_token(token):
                device.confirmed = True
                device.save()
                messages.success(request, '2FA has been successfully enabled!')
                return redirect('view_2fa_status')
            else:
                messages.error(request, 'Invalid code. Please try again.')
                return redirect('setup_2fa')
    
    return render(request, 'accounts/verify_2fa_token.html', {
        'form': TOTPVerificationForm(),
        'step': 'verify'
    })


@login_required
@require_http_methods(['GET'])
def view_2fa_status(request):
    """Display current 2FA status and options."""
    user = request.user
    device = TOTPDevice.objects.filter(user=user, name='default').first()
    is_enabled = device and device.confirmed
    
    context = {
        'is_2fa_enabled': is_enabled,
        'device': device,
    }
    return render(request, 'accounts/2fa_status.html', context)


@login_required
@require_http_methods(['POST'])
def disable_2fa(request):
    """Disable 2FA for the current user."""
    user = request.user
    form = Disable2FAForm(user=user, data=request.POST)
    
    if form.is_valid():
        # Delete all OTP devices
        TOTPDevice.objects.filter(user=user).delete()
        StaticDevice.objects.filter(user=user).delete()
        messages.success(request, '2FA has been disabled.')
        return redirect('view_2fa_status')
    
    return render(request, 'accounts/disable_2fa.html', {
        'form': form,
        'errors': form.errors
    })


@login_required
@require_http_methods(['GET'])
def show_recovery_codes(request):
    """Show recovery codes for the current user."""
    user = request.user
    device = TOTPDevice.objects.filter(user=user, name='default').first()
    
    if not device or not device.confirmed:
        messages.error(request, '2FA must be enabled first.')
        return redirect('view_2fa_status')
    
    # Get existing tokens
    recovery_device = StaticDevice.objects.filter(user=user, name='recovery').first()
    codes = list(recovery_device.token_set.all().values_list('token', flat=True)) if recovery_device else []
    
    context = {
        'codes': codes,
    }
    return render(request, 'accounts/recovery_codes.html', context)


@login_required
@require_http_methods(['POST'])
def regenerate_recovery_codes(request):
    """Regenerate recovery codes."""
    user = request.user
    device = TOTPDevice.objects.filter(user=user, name='default').first()
    
    if not device or not device.confirmed:
        return JsonResponse({'error': '2FA must be enabled'}, status=400)
    
    # Delete old tokens
    recovery_device = StaticDevice.objects.filter(user=user, name='recovery').first()
    if not recovery_device:
        recovery_device = StaticDevice.objects.create(user=user, name='recovery')

    StaticToken.objects.filter(device=recovery_device).delete()
    
    # Generate new tokens
    new_codes = []
    for i in range(10):
        token = StaticToken.random_token()
        StaticToken.objects.create(device=recovery_device, token=token)
        new_codes.append(token)
    
    messages.success(request, 'Recovery codes have been regenerated.')
    
    context = {
        'codes': new_codes,
    }
    return render(request, 'accounts/recovery_codes.html', context)
