"""Forms for two-factor authentication."""
from django import forms


class TOTPVerificationForm(forms.Form):
    """Form to verify TOTP token."""
    token = forms.CharField(
        label='6-Digit Code',
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            'class': 'form-control text-center',
            'placeholder': '000000',
            'inputmode': 'numeric',
            'autocomplete': 'off',
        }),
        help_text='Enter the 6-digit code from your authenticator app'
    )

    def clean_token(self):
        """Clean and validate token."""
        token = self.cleaned_data.get('token', '').replace(' ', '')
        if not token.isdigit():
            raise forms.ValidationError('Code must contain only digits.')
        return token


class RecoveryCodeForm(forms.Form):
    """Form to use a recovery code."""
    code = forms.CharField(
        label='Recovery Code',
        max_length=50,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your recovery code',
            'autocomplete': 'off',
        }),
        help_text='Enter one of your recovery codes if you lose access to your authenticator app'
    )


class Disable2FAForm(forms.Form):
    """Form to disable 2FA (requires password confirmation)."""
    password = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your password to disable 2FA',
        }),
        help_text='Enter your password to confirm 2FA disabling'
    )

    def __init__(self, user=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_password(self):
        """Verify password is correct."""
        password = self.cleaned_data.get('password')
        if self.user and not self.user.check_password(password):
            raise forms.ValidationError('Password is incorrect.')
        return password
