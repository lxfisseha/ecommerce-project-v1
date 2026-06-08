import cloudinary
import cloudinary.uploader
from src.config import settings

from urllib.parse import urlparse
import cloudinary
import cloudinary.uploader
from src.config import settings

# Initialize Cloudinary
if settings.CLOUDINARY_URL:
    url = urlparse(settings.CLOUDINARY_URL)
    cloudinary.config(
        cloud_name=url.hostname,
        api_key=url.username,
        api_secret=url.password
    )

class CloudinaryService:
    @staticmethod
    def upload_image(file_content: bytes, folder: str = "products") -> str:
        """
        Uploads an image to Cloudinary and returns the secure URL.
        """
        if not cloudinary.config().api_key:
            raise ValueError("Cloudinary is not correctly configured (missing API Key)")
            
        result = cloudinary.uploader.upload(
            file_content,
            folder=folder,
            resource_type="image"
        )
        return result.get("secure_url")

    @staticmethod
    def delete_image(public_id: str):
        """
        Deletes an image from Cloudinary.
        """
        if settings.CLOUDINARY_URL:
            cloudinary.uploader.destroy(public_id)
