from decimal import Decimal

MAX_IMAGE_SIZE = 5 * 1024 * 1024

DELIVERY_FEE = Decimal("150.0")

# Where the background worker stores generated WebP variants, relative to
# MEDIA_ROOT. Originals live under products/originals/<uuid>.<ext>.
VARIANT_PREFIX = "processed/products"
