# core/storage_backends.py
from __future__ import annotations

import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage

try:
    from storages.backends.s3boto3 import S3Boto3Storage
except Exception:  # pragma: no cover
    S3Boto3Storage = None  # type: ignore


class MediaStorage(S3Boto3Storage):  # type: ignore[misc]
    """
    Media bucket storage (images, avatars, etc).

    Bucket should be private for now; we can later make images public via CloudFront
    if you want (optional).
    """
    bucket_name = os.getenv("AWS_S3_MEDIA_BUCKET", "")
    default_acl = None
    file_overwrite = False
    location = "media"


class DownloadsStorage(S3Boto3Storage):  # type: ignore[misc]
    """
    Private downloads bucket storage for paid digital assets.

    Always uses signed URLs.
    """
    bucket_name = os.getenv("AWS_S3_DOWNLOADS_BUCKET", "")
    default_acl = None
    file_overwrite = False
    location = "downloads"
    querystring_auth = True
    custom_domain = None  # ensures signed S3 URLs


def get_media_storage():
    """
    Returns the correct storage for general media.
    - If USE_S3=True: MediaStorage (S3)
    - Else: local filesystem under MEDIA_ROOT
    """
    if getattr(settings, "USE_S3", False) and S3Boto3Storage is not None:
        return MediaStorage()
    return FileSystemStorage(location=settings.MEDIA_ROOT, base_url=settings.MEDIA_URL)


def get_downloads_storage():
    """
    Returns the correct storage for paid downloads.
    - If USE_S3=True: DownloadsStorage (S3 private bucket)
    - Else: local filesystem under MEDIA_ROOT (dev)
    """
    if getattr(settings, "USE_S3", False) and S3Boto3Storage is not None:
        return DownloadsStorage()
    return FileSystemStorage(location=settings.MEDIA_ROOT, base_url=settings.MEDIA_URL)
