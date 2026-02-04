"""
Test S3 upload configuration
Run: python manage.py shell < test_s3_upload.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.prod')
django.setup()

from django.conf import settings
from django.core.files.base import ContentFile
from products.models import ProductImage

print("="*70)
print("S3 UPLOAD CONFIGURATION TEST")
print("="*70)

# Check USE_S3
print(f"\n✓ USE_S3: {getattr(settings, 'USE_S3', False)}")

# Check AWS settings
if hasattr(settings, 'AWS_S3_MEDIA_BUCKET'):
    print(f"✓ AWS_S3_MEDIA_BUCKET: {settings.AWS_S3_MEDIA_BUCKET}")
else:
    print("✗ AWS_S3_MEDIA_BUCKET: NOT SET")

if hasattr(settings, 'AWS_ACCESS_KEY_ID'):
    print(f"✓ AWS_ACCESS_KEY_ID: {settings.AWS_ACCESS_KEY_ID[:10]}...")
else:
    print("✗ AWS_ACCESS_KEY_ID: NOT SET")

if hasattr(settings, 'AWS_SECRET_ACCESS_KEY'):
    print(f"✓ AWS_SECRET_ACCESS_KEY: {settings.AWS_SECRET_ACCESS_KEY[:10]}...")
else:
    print("✗ AWS_SECRET_ACCESS_KEY: NOT SET")

if hasattr(settings, 'AWS_S3_REGION_NAME'):
    print(f"✓ AWS_S3_REGION_NAME: {settings.AWS_S3_REGION_NAME}")
else:
    print("✗ AWS_S3_REGION_NAME: NOT SET")

# Check STORAGES
if hasattr(settings, 'STORAGES'):
    print(f"\n✓ STORAGES configured:")
    print(f"  - default: {settings.STORAGES.get('default', {}).get('BACKEND', 'NOT SET')}")
else:
    print("\n✗ STORAGES: NOT SET")

# Check storage backend
print(f"\n✓ Checking storage backend...")
try:
    from core.storage_backends import MediaStorage
    storage = MediaStorage()
    print(f"  - MediaStorage class loaded")
    print(f"  - bucket_name property: {storage.bucket_name}")
    print(f"  - access_key property: {storage.access_key[:10] if storage.access_key else 'EMPTY'}...")
    print(f"  - region_name property: {storage.region_name}")
except Exception as e:
    print(f"  ✗ Error loading MediaStorage: {e}")

# Check image field storage
print(f"\n✓ Checking ProductImage field storage...")
from products.models import ProductImage as PI
field = PI._meta.get_field('image')
print(f"  - ImageField upload_to: {field.upload_to}")
print(f"  - ImageField storage: {field.storage}")

print("\n" + "="*70)
print("If USE_S3=True and storage shows MediaStorage, uploads should go to S3")
print("="*70)
