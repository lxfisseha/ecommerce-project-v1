import pytest_asyncio
from unittest.mock import patch
from io import BytesIO
from fastapi import HTTPException
from src.tests.conftest import client, get_csrf_context


class TestImageUploadFailure:

    @pytest_asyncio.fixture(autouse=True)
    async def _setup(self):
        from src.dependencies import get_current_seller_id
        from src.tests.conftest import app
        app.dependency_overrides[get_current_seller_id] = lambda: 1
        self.token, self.csrf_cookie = get_csrf_context(client)
        yield
        app.dependency_overrides.pop(get_current_seller_id, None)

    def _post(self, files, data_extra=None):
        data = {
            "name": "P", "description": "D", "price": "10", "in_stock": "on",
            "image_tag_0": "main", "csrf_token": self.token
        }
        if data_extra:
            data.update(data_extra)
        return client.post(
            "/dashboard/products/add",
            data=data, files=files,
            cookies={"csrftoken": self.csrf_cookie},
            headers={"X-CSRF-Token": self.token}
        )

    def test_cloudinary_rejects(self):
        with patch("src.utils.storage.CloudinaryService.upload_image") as mock:
            mock.side_effect = HTTPException(status_code=400, detail="Upload rejected")
            file = {"image": ("bad.jpg", BytesIO(b"data"), "image/jpeg")}
            resp = self._post(files=file)
            assert resp.status_code == 200
            assert "upload" in resp.text.lower() or "image" in resp.text.lower()

    def test_cloudinary_timeout(self):
        with patch("src.utils.storage.CloudinaryService.upload_image") as mock:
            mock.side_effect = HTTPException(status_code=504, detail="Upload timed out")
            file = {"image": ("slow.jpg", BytesIO(b"data"), "image/jpeg")}
            resp = self._post(files=file)
            assert resp.status_code == 200
            assert "upload" in resp.text.lower() or "image" in resp.text.lower()

    def test_partial_failure_multiple(self):
        call_count = [0]
        def flaky_upload(file_content: bytes, folder: str = "products") -> str:
            call_count[0] += 1
            if call_count[0] == 2:
                raise HTTPException(status_code=400, detail="Second image failed")
            from src.utils.storage import CloudinaryService
            return CloudinaryService.upload_image(file_content, folder)
        with patch("src.utils.storage.CloudinaryService.upload_image", side_effect=flaky_upload):
            files = [
                ("images", ("a.jpg", BytesIO(b"a"), "image/jpeg")),
                ("images", ("b.jpg", BytesIO(b"b"), "image/jpeg")),
            ]
            resp = self._post(files=files, data_extra={"image_tag_1": "alt"})
            assert resp.status_code == 200
            assert "upload" in resp.text.lower() or "image" in resp.text.lower()
