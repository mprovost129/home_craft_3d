from __future__ import annotations

from django import forms

from .models import RefundRequest


class RefundRequestCreateForm(forms.Form):
    reason = forms.ChoiceField(
        choices=RefundRequest.Reason.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Optional details (recommended)",
            }
        ),
    )

    # Used only for guest confirmation in the create view
    guest_email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "you@example.com"}),
    )


class SellerDecisionForm(forms.Form):
    decision_note = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Optional note to buyer",
            }
        ),
    )
