from __future__ import annotations

from django import forms

from .models import ProductQuestionReport


class ThreadCreateForm(forms.Form):
    subject = forms.CharField(
        required=False,
        max_length=180,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional subject"}),
    )
    body = forms.CharField(
        required=True,
        widget=forms.Textarea(
            attrs={"class": "form-control", "rows": 3, "placeholder": "Ask a question…"}
        ),
    )


class ReplyForm(forms.Form):
    body = forms.CharField(
        required=True,
        widget=forms.Textarea(
            attrs={"class": "form-control", "rows": 2, "placeholder": "Write a reply…"}
        ),
    )


class ReportForm(forms.Form):
    reason = forms.ChoiceField(
        choices=ProductQuestionReport.Reason.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    details = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={"class": "form-control", "rows": 2, "placeholder": "Optional details (recommended)"}
        ),
    )