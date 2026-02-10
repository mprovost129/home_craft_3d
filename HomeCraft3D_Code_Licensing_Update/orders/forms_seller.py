# orders/forms_seller.py
from __future__ import annotations

from django import forms


class MarkShippedForm(forms.Form):
    tracking_number = forms.CharField(required=False, max_length=80)
    carrier = forms.CharField(required=False, max_length=40)
