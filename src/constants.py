from decimal import Decimal

MAX_IMAGE_SIZE = 5 * 1024 * 1024

DELIVERY_FEE = Decimal("150.0")

# Where the background worker stores generated WebP variants, relative to
# MEDIA_ROOT. Originals live under products/originals/<uuid>.<ext>.
VARIANT_PREFIX = "processed/products"

# Seller banner variants. Kept apart from VARIANT_PREFIX because they are not
# product images and share no lifecycle: prune_orphans must not treat one as
# the other, and a seller banner is never enqueued through the RQ queue.
BANNER_PREFIX = "processed/sellers"

# Key under which a seller banner variant is stored, in
# sellers.featured_image_variants. Declared here so the writer (process_images)
# and the template reader (templates_config) share one definition; a mismatch
# would silently fall back to the 304 KB original.
BANNER_VARIANT_NAME = "banner"
