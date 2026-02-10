# core/storage_backends.py
from __future__ import annotations

from django.conf import settings
from django.core.files.storage import FileSystemStorage

try:
    from storages.backends.s3boto3 import S3Boto3Storage
except Exception:  # pragma: no cover
    S3Boto3Storage = None  # type: ignore


class MediaStorage(S3Boto3Storage):  # type: ignore[misc]
    """
    Media bucket storage (images, avatars, etc).

    Reads from Django settings to properly inherit AWS config.
    """
    @property
    def bucket_name(self):
        return getattr(settings, "AWS_S3_MEDIA_BUCKET", "")
    
    @property
    def access_key(self):
        return getattr(settings, "AWS_ACCESS_KEY_ID", "")
    
    @property
    def secret_key(self):
        return getattr(settings, "AWS_SECRET_ACCESS_KEY", "")
    
    @property
    def region_name(self):
        return getattr(settings, "AWS_S3_REGION_NAME", "us-east-2")
    
    default_acl = None
    file_overwrite = False
    location = "media"


class DownloadsStorage(S3Boto3Storage):  # type: ignore[misc]
    """
    Private downloads bucket storage for paid digital assets.

    Always uses signed URLs.
    """
    @property
    def bucket_name(self):
        return getattr(settings, "AWS_S3_DOWNLOADS_BUCKET", "")
    
    @property
    def access_key(self):
        return getattr(settings, "AWS_ACCESS_KEY_ID", "")
    
    @property
    def secret_key(self):
        return getattr(settings, "AWS_SECRET_ACCESS_KEY", "")
    
    @property
    def region_name(self):
        return getattr(settings, "AWS_S3_REGION_NAME", "us-east-2")
    
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
