"""
Guards on the seeded sportwear catalogue and tag taxonomy.

The tag rules are substring matches over product names, which is a convenient
design that fails quietly. Two bugs motivated these tests:

- A bare "gym" keyword tagged Leather Gym Gloves, Gym Tank Top and Gym T-Shirt
  with "bags", because "gym" was listed as a synonym for "gym bag". Nothing
  errored; the shop just offered a bags filter full of unrelated products.
- Keyword ordering is load-bearing. "bag" has to be tested after "gym bag" or
  every gym bag also matches the general bag rule.
"""
import pytest

from src.scripts.seed_products import (
    PRODUCT_TEMPLATES,
    SEED_ASSET_DIR,
    UNIT_COUNTS,
    _build_unit_queue,
    _find_template,
)
from src.scripts.seed_tags import ALWAYS_TAGS, TAG_MAPPING


def tags_for(name: str) -> set[str]:
    """Tags the seeder would attach, using the same logic as seed_tags.main."""
    lowered = f"{name} #1".lower()
    tags = list(ALWAYS_TAGS)
    for keywords, matched in TAG_MAPPING.items():
        if any(kw in lowered for kw in keywords):
            tags.extend(matched)
    return set(tags)


class TestCatalogueShape:
    def test_unit_counts_match_templates(self):
        """A name in UNIT_COUNTS with no template raises; this catches the reverse."""
        template_names = {t["name"] for t in PRODUCT_TEMPLATES}
        assert set(UNIT_COUNTS) == template_names, (
            f"only in UNIT_COUNTS: {set(UNIT_COUNTS) - template_names}; "
            f"only in templates: {template_names - set(UNIT_COUNTS)}"
        )

    def test_catalogue_size(self):
        assert len(_build_unit_queue()) == 25

    def test_every_template_has_a_description_and_prices(self):
        for template in PRODUCT_TEMPLATES:
            assert template["description"].strip(), template["name"]
            assert template["prices"], template["name"]
            assert all(p > 0 for p in template["prices"]), template["name"]

    def test_every_template_has_at_least_one_image(self):
        for template in PRODUCT_TEMPLATES:
            assert template["images"], template["name"]

    def test_every_template_has_attributes(self):
        for template in PRODUCT_TEMPLATES:
            assert template["attributes"], template["name"]


class TestImagesAreNotIndexAligned:
    """
    The old seeder kept templates and images in parallel lists indexed against
    each other, so removing one entry attached the wrong photo to a product with
    no error anywhere. Images now live on the template.
    """

    def test_images_are_carried_by_the_template(self):
        for template in PRODUCT_TEMPLATES:
            assert "images" in template

    def test_remote_images_request_wide_enough_for_the_largest_variant(self):
        """
        Sources are requested at w=1200 so the stored original is at least 1.5x
        the 800w tier. A narrower source makes that tier an upscale, which costs
        bytes and adds no detail.
        """
        from src.scripts.process_images import SIZES

        widest = max(SIZES.values())
        for template in PRODUCT_TEMPLATES:
            for source in template["images"]:
                if source.startswith("local:"):
                    continue
                requested = int(source.rsplit("w=", 1)[1])
                assert requested >= widest * 1.5, (
                    f"{template['name']} requests {requested}px, too narrow for "
                    f"the {widest}w tier"
                )

    def test_local_assets_are_named_not_embedded(self):
        for template in PRODUCT_TEMPLATES:
            for source in template["images"]:
                if source.startswith("local:"):
                    assert "/" not in source, (
                        "local assets must be bare filenames so they cannot "
                        f"escape the assets directory: {source}"
                    )

    def test_seed_asset_dir_is_inside_the_package(self):
        assert SEED_ASSET_DIR.name == "seed_assets"


class TestTagTaxonomy:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("Arsenal Football Jersey", "football"),
            ("Manchester United Football Jersey", "football"),
            ("Contour Gym Bag", "bags"),
            ("Gym T-Shirt", "tops"),
            ("Gym Tank Top", "tops"),
            ("Hand Grip Strengthener", "strength"),
            ("Knee Support Sleeve", "support"),
            ("Premium Modal Underwear", "underwear"),
        ],
    )
    def test_key_products_get_their_category(self, name, expected):
        assert expected in tags_for(name)

    @pytest.mark.parametrize(
        "name",
        ["Leather Gym Gloves", "Gym Tank Top", "Gym T-Shirt"],
    )
    def test_gym_apparel_is_not_tagged_as_bags(self, name):
        """
        The regression: a bare "gym" keyword matched "gym bag" and tagged three
        apparel products as bags.
        """
        assert "bags" not in tags_for(name), f"{name} was tagged as bags"

    def test_only_actual_bags_get_the_bag_tag(self):
        for template in PRODUCT_TEMPLATES:
            tagged = "bags" in tags_for(template["name"])
            assert tagged == ("bag" in template["name"].lower()), (
                f"{template['name']} bag tag does not match its name"
            )

    def test_every_product_is_tagged(self):
        """A product with no tags is invisible to tag filtering."""
        for template in PRODUCT_TEMPLATES:
            assert tags_for(template["name"]), template["name"]

    def test_every_product_carries_the_shop_tag(self):
        for template in PRODUCT_TEMPLATES:
            assert ALWAYS_TAGS[0] in tags_for(template["name"])

    def test_specific_keywords_precede_the_general_ones(self):
        """
        Substring matching means a specific rule must be declared first, or the
        general rule it contains fires too.

        A keyword appearing in the same tuple as the general one is fine, since
        both are tried together; what matters is that the pair holding the
        specific term comes earlier in the dict than any entry that would match
        a product on the general term alone.
        """
        order = list(TAG_MAPPING)
        for specific, general in [
            ("gym bag", "bag"),
            ("gym glove", "glove"),
            ("football jersey", "jersey"),
            ("gym t-shirt", "t-shirt"),
            ("gym fit", "fit"),
        ]:
            si = next(
                (i for i, kws in enumerate(order) if specific in kws), None
            )
            assert si is not None, f'"{specific}" is not a declared keyword'

            # Entries that would match a product on the general term alone.
            general_positions = [
                i for i, kws in enumerate(order)
                if general in kws and specific not in kws
            ]
            if not general_positions:
                # No competing rule, so ordering cannot bite here. The specific
                # term simply shares its tuple with the general one.
                continue
            assert si < min(general_positions), (
                f'"{specific}" must be declared before the general '
                f'"{general}" rule at position {min(general_positions)}'
            )

    def test_no_fashion_or_ethnicity_taxonomy_remains(self):
        """The catalogue is sportwear; these rules were part of the old range."""
        blob = " ".join(
            kw for keywords in TAG_MAPPING for kw in keywords
        ).lower()
        for gone in ("dress", "kemis", "netela", "habesha", "gown", "handbag"):
            assert gone not in blob, f"{gone!r} is still a tag keyword"


class TestBackfillLookup:
    def test_finds_template_by_product_name_prefix(self):
        template = _find_template("Gym Tank Top #7")
        assert template is not None
        assert template["name"] == "Gym Tank Top"

    def test_returns_none_for_an_unknown_product(self):
        assert _find_template("Something Entirely Different") is None

    @pytest.mark.parametrize("name", [t["name"] for t in PRODUCT_TEMPLATES])
    def test_every_template_name_matches_itself(self, name):
        """Seeded names are "<template> #<n>", so the prefix must round-trip."""
        assert _find_template(f"{name} #1") is not None
