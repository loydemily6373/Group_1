import os
import magic
from django.core.exceptions import ValidationError

ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png']
ALLOWED_MIME_TYPES = ['image/jpeg', 'image/png']

def validate_image_file(file):
    ext = os.path.splitext(file.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(f"Unsupported extension: {ext}. Use .jpg or .png")

    file.seek(0)
    mime = magic.from_buffer(file.read(2048), mime=True)
    file.seek(0)

    if mime not in ALLOWED_MIME_TYPES:
        raise ValidationError(f"File content is not a valid image (got {mime})")