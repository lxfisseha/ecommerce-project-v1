from decimal import Decimal

MAX_IMAGE_SIZE = 5 * 1024 * 1024

DELIVERY_FEE = Decimal("150.0")

# Storefront name. Defined once because it appears in ~26 places: every page
# title, both header wordmarks, the packing slip, SMS bodies and the FastAPI
# app title. It was previously a literal in each of them, so a rename was a
# find-and-replace across 21 files and any miss showed up as a live page still
# carrying the old brand.
#
# Exposed to templates as the `site_name` global by templates_config.
SITE_NAME = "MAHI`S Sportwear"

# Support contact addresses shown on /support. Kept next to SITE_NAME so a
# rebrand updates them in the same place; both must be real, deliverable
# addresses or the page is worse than having none.
SITE_SUPPORT_EMAIL = "support@mahis-sportwear.et"
SITE_TELEGRAM_HANDLE = "@MahisSportwear"

# Fallback SMS sender ID. Deliberately NOT SITE_NAME: the brand contains a
# backtick and a space, and AfroMessage sender IDs must be the short
# alphanumeric string registered with them. Production sets
# AFROMESSAGES_SENDER in .env, which takes precedence over this.
SITE_SMS_SENDER = "MahisSportwear"

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

# Width of the generated seller banner, in pixels. Declared here rather than
# read from src.scripts.process_images so templates can declare a matching
# intrinsic size without importing Pillow on the request path. process_images
# defines the same number for generation; the two must agree or the browser
# reserves the wrong box before the banner loads.
BANNER_WIDTH = 1200
