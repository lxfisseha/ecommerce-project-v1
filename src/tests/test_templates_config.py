from src.templates_config import cloudinary_url

CLOUDINARY_URL = "https://res.cloudinary.com/dpimwr1pr/image/upload/v123/products/img.png"


class TestCloudinaryUrlFilter:

    def test_width_only(self):
        result = cloudinary_url(CLOUDINARY_URL, width=400)
        expected = "https://res.cloudinary.com/dpimwr1pr/image/upload/f_auto,q_auto:eco,w_400/v123/products/img.png"
        assert result == expected

    def test_width_and_height(self):
        result = cloudinary_url(CLOUDINARY_URL, width=160, height=160)
        expected = "https://res.cloudinary.com/dpimwr1pr/image/upload/f_auto,q_auto:eco,w_160,h_160,c_fill/v123/products/img.png"
        assert result == expected

    def test_custom_quality(self):
        result = cloudinary_url(CLOUDINARY_URL, width=800, quality="80")
        expected = "https://res.cloudinary.com/dpimwr1pr/image/upload/f_auto,q_80,w_800/v123/products/img.png"
        assert result == expected

    def test_no_width(self):
        result = cloudinary_url(CLOUDINARY_URL)
        expected = "https://res.cloudinary.com/dpimwr1pr/image/upload/f_auto,q_auto:eco/v123/products/img.png"
        assert result == expected

    def test_non_cloudinary_url(self):
        url = "https://example.com/img.jpg"
        result = cloudinary_url(url, width=400)
        assert result == url

    def test_url_without_upload(self):
        url = "https://res.cloudinary.com/dpimwr1pr/image/private/v123/img.png"
        result = cloudinary_url(url, width=200)
        assert result == url

    def test_empty_url(self):
        result = cloudinary_url("", width=400)
        assert result == ""
