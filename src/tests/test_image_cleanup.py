"""
A seed reset must remove image files, not just the rows referencing them.

Nothing else maps a file on disk back to the row that owned it, so deleting
the rows alone orphans every original and variant permanently.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.utils.storage import LocalStorage


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.utils.storage.settings.MEDIA_ROOT", str(tmp_path), raising=False
    )
    return LocalStorage()


def _image(storage, *, variants=True):
    """
    Create an original plus its variant files and return a row-like object.

    LocalStorage.save() picks its own uuid filename, so the variant keys have
    to be derived from the returned object_name rather than assumed.
    """
    from src.constants import VARIANT_PREFIX
    from src.scripts.process_images import SIZES

    original = storage.save(b"original-bytes", "seed.jpg", folder="products")
    stem = Path(original).stem
    processed = None
    if variants:
        processed = {
            name: storage.write(f"{VARIANT_PREFIX}/{stem}_{w}w.webp", b"webp")
            for name, w in SIZES.items()
        }
    return SimpleNamespace(id=1, object_name=original, processed_urls=processed)


def test_delete_image_files_removes_original_and_variants(storage):
    from src.features.products.services import delete_image_files

    image = _image(storage)
    assert storage.object_exists(image.object_name)
    assert all(storage.object_exists(k) for k in image.processed_urls.values())

    delete_image_files(image)

    assert not storage.object_exists(image.object_name)
    for key in image.processed_urls.values():
        assert not storage.object_exists(key), f"{key} was left behind"


def test_delete_image_files_falls_back_to_key_pattern_when_urls_absent(storage):
    """
    If processed_urls was never written, the variant files may still exist
    from an earlier run. They are addressed by the width in their key, so
    they must still be unlinked; delete_prefix matches directories and this
    prefix is a filename stem, so it silently does nothing.
    """
    from src.features.products.services import delete_image_files

    image = _image(storage)
    written = list(image.processed_urls.values())
    image.processed_urls = None
    assert all(storage.object_exists(k) for k in written)

    delete_image_files(image)

    assert not storage.object_exists(image.object_name)
    for key in written:
        assert not storage.object_exists(key), f"{key} survived the fallback"


def test_delete_image_files_is_idempotent(storage):
    """Product delete retries should not raise on a missing file."""
    from src.features.products.services import delete_image_files

    image = _image(storage)
    delete_image_files(image)
    delete_image_files(image)  # must not raise


def test_delete_image_files_tolerates_missing_object_name(storage):
    from src.features.products.services import delete_image_files

    image = SimpleNamespace(id=1, object_name="", processed_urls=None)
    delete_image_files(image)  # must not raise
