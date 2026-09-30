from src.config import settings
import uuid
from datetime import timedelta
from pathlib import Path
import os
import shutil


class LocalStorage:
    """Local filesystem storage service for self-hosted images."""

    def __init__(self):
        self.base_path = Path(settings.MEDIA_ROOT) if hasattr(settings, 'MEDIA_ROOT') else Path("/app/media")
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save(self, file_content: bytes, filename: str, folder: str = "products") -> str:
        """
        Save file to local filesystem.
        Returns object_name (relative path from media root).
        """
        ext = filename.split(".")[-1].lower() if "." in filename else "jpg"
        unique_name = f"{uuid.uuid4()}.{ext}"
        relative_path = f"{folder}/originals/{unique_name}"
        full_path = self.base_path / relative_path
        
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(file_content)
        
        return relative_path

    def save_upload(self, upload_file, folder: str = "products") -> str:
        """
        Save UploadFile to local filesystem.
        Returns object_name (relative path from media root).
        """
        ext = "jpg"
        if hasattr(upload_file, 'filename') and upload_file.filename:
            ext = upload_file.filename.split(".")[-1].lower() if "." in upload_file.filename else "jpg"
        
        unique_name = f"{uuid.uuid4()}.{ext}"
        relative_path = f"products/originals/{unique_name}"
        full_path = self.base_path / relative_path
        
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, "wb") as f:
            content = upload_file.file.read()
            f.write(content)
        
        return relative_path

    def get_path(self, object_name: str) -> Path:
        """Get full filesystem path for an object."""
        return self.base_path / object_name

    def get_url(self, object_name: str) -> str:
        """Get local filesystem URL for an object."""
        return f"/media/{object_name}"

    def delete(self, object_name: str) -> bool:
        """Delete an object from local filesystem."""
        try:
            full_path = self.base_path / object_name
            if full_path.exists():
                full_path.unlink()
                return True
            return False
        except Exception:
            return False

    def delete_prefix(self, prefix: str) -> int:
        """Delete all objects with a given prefix. Returns count deleted."""
        try:
            prefix_path = self.base_path / prefix
            count = 0
            if prefix_path.exists():
                for file_path in prefix_path.rglob("*"):
                    if file_path.is_file():
                        file_path.unlink()
                        count += 1
                # Remove empty directories
                for dir_path in sorted(prefix_path.rglob("*"), key=lambda p: len(p.parts), reverse=True):
                    if dir_path.is_dir() and not any(dir_path.iterdir()):
                        dir_path.rmdir()
            return count
        except Exception:
            return 0

    def object_exists(self, object_name: str) -> bool:
        """Check if an object exists."""
        return (self.base_path / object_name).exists()


# Backward compatibility - CloudinaryService for gradual migration
class CloudinaryService:
    @staticmethod
    def upload_image(file_content: bytes, folder: str = "products", eager: list = None) -> str:
        raise NotImplementedError("Cloudinary is deprecated. Use LocalStorage for direct uploads.")

    @staticmethod
    def delete_image(public_id: str):
        pass  # No-op for backward compatibility