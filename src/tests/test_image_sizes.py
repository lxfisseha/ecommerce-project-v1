"""
Guard the `sizes` attributes on responsive images.

The bug this prevents: one copy-pasted `sizes` string applied to every
image context, so a 96px cart thumbnail claimed 800px and downloaded the
800w variant, while a full-width hero on mobile was served 160w.
"""
import pathlib
import re

import pytest

TEMPLATES = pathlib.Path(__file__).resolve().parents[1] / "templates"

# (template, expected substring of the sizes attribute)
EXPECTED = {
    "buyer/_product_grid.html": "(max-width: 767px) 45vw, (max-width: 1280px) 22vw, 286px",
    "products/_product_list_content.html": "(max-width: 640px) 90vw, (max-width: 1024px) 45vw, 300px",
    "buyer/_cart_content.html": "96px",
    "products/form.html": "(max-width: 768px) 45vw, 130px",
    "buyer_product_detail.html": "(max-width: 1024px) 100vw, 610px",
}

# Every image that offers a srcset must declare sizes; without it the browser
# assumes 100vw and picks the largest candidate.
SRCSET_TEMPLATES = [
    "buyer/_product_grid.html",
    "products/_product_list_content.html",
    "buyer/_cart_content.html",
    "products/form.html",
    "buyer_product_detail.html",
]


def read(rel: str) -> str:
    return (TEMPLATES / rel).read_text(encoding="utf-8")


@pytest.mark.parametrize("rel,expected", sorted(EXPECTED.items()))
def test_sizes_matches_layout(rel, expected):
    body = read(rel)
    assert f'sizes="{expected}"' in body, f"{rel} should declare sizes=\"{expected}\""


@pytest.mark.parametrize("rel", SRCSET_TEMPLATES)
def test_srcset_images_declare_sizes(rel):
    body = read(rel)
    sources = re.findall(r"<source\b[^>]*>", body, re.S)
    assert sources, f"{rel} is expected to contain <source srcset>"
    for tag in sources:
        assert "srcset" in tag
        assert "sizes" in tag, f"{rel}: <source> has srcset but no sizes"


def test_no_legacy_blanket_sizes_attribute():
    """The old copy-pasted string claimed 800px for every context."""
    offenders = []
    for path in TEMPLATES.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r'sizes="([^"]*)"', text):
            if m.group(1) == "(max-width: 480px) 160px, (max-width: 768px) 400px, 800px":
                offenders.append(path.relative_to(TEMPLATES).as_posix())
    assert not offenders, f"blanket 800px sizes still present in: {offenders}"


def test_cart_thumbnail_does_not_offer_800w():
    """A 96px box has no use for the 800w variant."""
    body = read("buyer/_cart_content.html")
    srcset = re.search(r"<source[^>]*srcset=\"([^\"]*)\"", body, re.S)
    assert srcset, "cart thumbnail should have a srcset"
    assert "800w" not in srcset.group(1), "cart thumbnail must not offer the 800w variant"
