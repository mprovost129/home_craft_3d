# S3 Image Upload Flow - Diagnostic Guide

## Expected Flow

When a seller uploads an image through `/products/seller/{id}/images/`:

1. **Form Submission** → `products/views_seller.py:seller_product_images()`
2. **Form Processing** → `ProductImageUploadForm` validates the image
3. **Save to Storage** → `ProductImage.image.save()` is called
4. **Storage Backend** → Django's STORAGES["default"] is used
5. **S3 Upload** → `core.storage_backends.MediaStorage` uploads to S3

## Configuration Checklist

### ✅ .env File (Production)
```env
USE_S3=True
AWS_ACCESS_KEY_ID=<your-access-key-id>
AWS_SECRET_ACCESS_KEY=<your-secret-access-key>
AWS_S3_REGION_NAME=us-east-2
AWS_S3_MEDIA_BUCKET=homecraft3d-media
AWS_S3_DOWNLOADS_BUCKET=homecraft3d-downloads
```

**Note**: Never commit `.env` to git. These values should only be in your environment variables.

### ✅ config/settings/base.py
```python
if USE_S3:
    # ... AWS settings loaded from env ...
    STORAGES = {
        "default": {"BACKEND": "core.storage_backends.MediaStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }
```

### ✅ core/storage_backends.py
```python
class MediaStorage(S3Boto3Storage):
    # Uses @property to read from Django settings at runtime
    @property
    def bucket_name(self):
        return getattr(settings, "AWS_S3_MEDIA_BUCKET", "")
    # ... etc
```

### ✅ products/models.py
```python
class ProductImage(models.Model):
    image = models.ImageField(upload_to="product_images/")
    # ^ Uses Django's default storage (STORAGES["default"])
```

## Testing on Production

Run this on your production server:
```bash
python manage.py shell < test_s3_upload.py
```

This will show:
- If USE_S3 is True
- If AWS credentials are loaded
- What storage backend is being used
- If MediaStorage can access the bucket

## Common Issues

### Issue: "Still uploading to server"
**Cause**: STORAGES not configured or USE_S3=False
**Fix**: Ensure .env has USE_S3=True and restart server

### Issue: "Files uploaded but URLs don't work"
**Cause**: Bucket is private and images need signed URLs
**Fix**: Either make bucket public (for product images) or ensure templates use signed URLs

### Issue: "Slow uploads"
**Cause**: Large image files or slow connection to S3
**Fix**: 
- Add client-side image compression
- Use CloudFront CDN
- Resize images before upload

## Verification Steps

1. Upload an image through seller panel
2. Check `/products/seller/{id}/images/` - image should appear
3. Check S3 console: bucket `homecraft3d-media` → folder `media/product_images/`
4. File should be there with path like: `media/product_images/image_abc123.jpg`

## Current Status

Based on code review:
- ✅ Settings configured correctly
- ✅ Storage backend uses properties (reads from Django settings)
- ✅ STORAGES points to MediaStorage
- ✅ .env has USE_S3=True

**Next Step**: Run `test_s3_upload.py` on production to confirm runtime config.
