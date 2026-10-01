"""
delete_prefix matches directories, so it silently does nothing when handed a
filename stem. Reprocessing must remove stale variant files explicitly, or an
upscaled 800w file survives after the no-upscale rule stops referencing it.
"""
import pytest

from src.utils.storage import LocalStorage


def _storage(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.storage.settings.MEDIA_ROOT", str(tmp_path), raising=False)
    return LocalStorage()


def test_delete_prefix_ignores_a_filename_stem(tmp_path, monkeypatch):
    storage = _storage(tmp_path, monkeypatch)
    storage.write("processed/products/abc_800w.webp", b"stale")

    # The prefix here is a stem, not a directory, so nothing is removed.
    assert storage.delete_prefix("processed/products/abc") == 0
    assert storage.object_exists("processed/products/abc_800w.webp")


def test_delete_removes_a_single_stale_variant(tmp_path, monkeypatch):
    storage = _storage(tmp_path, monkeypatch)
    storage.write("processed/products/abc_160w.webp", b"a")
    storage.write("processed/products/abc_400w.webp", b"b")
    storage.write("processed/products/abc_800w.webp", b"c")

    assert storage.delete("processed/products/abc_800w.webp") is True

    assert storage.object_exists("processed/products/abc_160w.webp")
    assert storage.object_exists("processed/products/abc_400w.webp")
    assert not storage.object_exists("processed/products/abc_800w.webp")


def test_delete_missing_file_is_false(tmp_path, monkeypatch):
    storage = _storage(tmp_path, monkeypatch)
    assert storage.delete("processed/products/nope_800w.webp") is False
