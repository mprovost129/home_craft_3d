# cart/forms.py
from __future__ import annotations

from django import forms


class AddToCartForm(forms.Form):
    product_id = forms.IntegerField(widget=forms.HiddenInput)
    quantity = forms.IntegerField(min_value=1, initial=1, required=False)


class UpdateCartLineForm(forms.Form):
    product_id = forms.IntegerField(widget=forms.HiddenInput)
    quantity = forms.IntegerField(min_value=0, required=True)  # 0 removes
