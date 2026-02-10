"""Management command to enable 2FA for admin/superuser accounts."""
import io
import qrcode
from base64 import b64encode
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.util import random_hex


class Command(BaseCommand):
    help = 'Setup 2FA for superuser/admin accounts'

    def add_arguments(self, parser):
        parser.add_argument(
            'username',
            nargs='?',
            type=str,
            help='Username to enable 2FA for (if not provided, enables for all superusers)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force regeneration of 2FA even if already configured'
        )

    def handle(self, *args, **options):
        username = options.get('username')
        force = options.get('force', False)

        # Get users to process
        if username:
            try:
                users = [User.objects.get(username=username)]
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'User "{username}" not found'))
                return
        else:
            users = User.objects.filter(is_superuser=True)

        if not users:
            self.stdout.write(self.style.WARNING('No superusers found'))
            return

        for user in users:
            self.stdout.write(f'\nProcessing user: {user.username} ({user.email})')

            # Check if already has 2FA
            device = TOTPDevice.objects.filter(user=user, name='default').first()
            if device and device.confirmed and not force:
                self.stdout.write(self.style.WARNING('  → 2FA already enabled (use --force to regenerate)'))
                continue

            # Generate or regenerate device
            if device and force:
                device.delete()
                self.stdout.write('  → Clearing existing 2FA')

            device, created = TOTPDevice.objects.get_or_create(
                user=user,
                name='default',
                defaults={'confirmed': False}
            )

            # Generate secret key
            if not device.key or force:
                device.key = random_hex(20)
                device.save()
                self.stdout.write('  → Generated new secret key')

            # Generate backup codes
            recovery_device, _ = StaticDevice.objects.get_or_create(
                user=user,
                name='recovery'
            )
            StaticToken.objects.filter(device=recovery_device).delete()
            backup_codes = []
            for i in range(10):
                token = StaticToken.random_token()
                StaticToken.objects.create(device=recovery_device, token=token)
                backup_codes.append(token)

            self.stdout.write(self.style.SUCCESS('✓ 2FA Setup Complete'))
            self.stdout.write(f'\nAccount: {user.email}')
            self.stdout.write(f'Secret Key: {device.key}')
            self.stdout.write(f'\nSetup URL: {device.config_url}')

            # Generate and display QR code
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(device.config_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            qr_code_base64 = b64encode(buffer.getvalue()).decode()

            self.stdout.write('\n--- BACKUP RECOVERY CODES ---')
            self.stdout.write('Save these in a secure location:')
            for i, code in enumerate(backup_codes, 1):
                self.stdout.write(f'{i:2d}. {code}')

            self.stdout.write('\n--- QR CODE (Base64) ---')
            self.stdout.write(f'data:image/png;base64,{qr_code_base64}')

            self.stdout.write(f'\n--- NEXT STEPS ---')
            self.stdout.write('1. Use the above secret key or QR code with your authenticator app')
            self.stdout.write('2. Save the recovery codes in a secure location')
            self.stdout.write('3. Visit /accounts/2fa/status/ to verify setup')
            self.stdout.write('4. First login will require 2FA token verification')

        self.stdout.write(self.style.SUCCESS('\n✓ 2FA setup complete for all selected users'))
