from __future__ import annotations

from django import forms

from .models import Review


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ["rating", "title", "body"]
        widgets = {
            "rating": forms.Select(
                choices=[(i, f"{i} Star{'s' if i != 1 else ''}") for i in range(5, 0, -1)],
                attrs={"class": "form-select"},
            ),
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional title"}),
            "body": forms.Textarea(attrs={"class": "form-control", "rows": 5, "placeholder": "Optional review text"}),
        }
