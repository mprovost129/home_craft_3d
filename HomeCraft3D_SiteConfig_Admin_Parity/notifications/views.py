# notifications/views.py
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import email_verified_required

from .models import Notification


@login_required
@email_verified_required
def inbox(request: HttpRequest) -> HttpResponse:
    qs = Notification.objects.filter(user=request.user).order_by("-created_at")

    kind = (request.GET.get("kind") or "").strip()
    if kind:
        qs = qs.filter(kind=kind)

    status = (request.GET.get("status") or "").strip().lower()
    if status == "unread":
        qs = qs.filter(is_read=False)
    elif status == "read":
        qs = qs.filter(is_read=True)

    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get("page") or 1)

    counts = {
        "all": Notification.objects.filter(user=request.user).count(),
        "unread": Notification.objects.filter(user=request.user, is_read=False).count(),
    }

    kinds = list(Notification.Kind.choices)

    return render(
        request,
        "notifications/inbox.html",
        {
            "page": page,
            "counts": counts,
            "kinds": kinds,
            "active_kind": kind,
            "active_status": status,
        },
    )


@login_required
@email_verified_required
def detail(request: HttpRequest, pk: int) -> HttpResponse:
    n = get_object_or_404(Notification, pk=pk, user=request.user)

    # Mark read on view
    n.mark_read(save=True)

    return render(
        request,
        "notifications/detail.html",
        {"n": n},
    )


@login_required
@email_verified_required
def mark_read(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != "POST":
        raise Http404
    n = get_object_or_404(Notification, pk=pk, user=request.user)
    n.mark_read(save=True)
    return redirect("notifications:inbox")


@login_required
@email_verified_required
def mark_unread(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != "POST":
        raise Http404
    n = get_object_or_404(Notification, pk=pk, user=request.user)
    n.mark_unread(save=True)
    return redirect("notifications:inbox")


@login_required
@email_verified_required
def clear_all_read(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        raise Http404
    Notification.objects.filter(user=request.user, is_read=True).delete()
    return redirect("notifications:inbox")
