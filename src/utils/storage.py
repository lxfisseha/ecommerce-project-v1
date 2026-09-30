from minio import Minio
from minio.error import S3Error
from src.config import settings
import uuid
from datetime import timedelta


class MinioStorage:
    """MinIO storage service for self-hosted image storage."""

    def __init__(self):
        self.client = Minio(
            endpoint=settings.MINIO_ENDPOINT.replace("http://", "").replace("https://", ""),
            access_key=settings.MINIO_ACCESS_KEY or settings.MINIO_ROOT_USER,
            secret_key=settings.MINIO_SECRET_KEY or settings.MINIO_ROOT_PASSWORD,
            secure=settings.MINIO_ENDPOINT.startswith("https"),
        )
        self.bucket = settings.MINIO_BUCKET
        self._ensure_bucket()

    def _ensure_bucket(self):
        """Create bucket if it doesn't exist."""
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
        except S3Error as e:
            # Bucket might already exist
            if e.code != "BucketAlreadyOwnedByYou":
                raise

    def presigned_put_url(self, filename: str, content_type: str, folder: str = "products") -> tuple[str, str]:
        """
        Generate a presigned PUT URL for direct browser-to-MinIO upload.
        Returns (upload_url, object_name).
        """
        ext = filename.split(".")[-1].lower() if "." in filename else "jpg"
        object_name = f"{folder}/originals/{uuid.uuid4()}.{ext}"

        url = self.client.presigned_put_object(
            bucket_name=self.bucket,
            object_name=object_name,
            expires=timedelta(hours=1),
        )
        return url, object_name

    def presigned_get_url(self, object_name: str) -> str:
        """Generate a presigned GET URL for an object."""
        return self.client.presigned_get_object(
            bucket_name=self.bucket,
            object_name=object_name,
            expires=timedelta(hours=1),
        )

    def delete(self, object_name: str) -> bool:
        """Delete an object from MinIO."""
        try:
            self.client.remove_object(self.bucket, object_name)
            return True
        except S3Error:
            return False

    def delete_prefix(self, prefix: str) -> int:
        """Delete all objects with a given prefix. Returns count deleted."""
        try:
            objects = self.client.list_objects(self.bucket, prefix=prefix, recursive=True)
            count = 0
            for obj in objects:
                self.client.remove_object(self.bucket, obj.object_name)
                count += 1
            return count
        except S3Error:
            return 0

    def object_exists(self, object_name: str) -> bool:
        """Check if an object exists."""
        try:
            self.client.stat_object(self.bucket, object_name)
            return True
        except S3Error:
            return False


# Backward compatibility - CloudinaryService for gradual migration
class CloudinaryService:
    @staticmethod
    def upload_image(file_content: bytes, folder: str = "products", eager: list = None) -> str:
        raise NotImplementedError("Cloudinary is deprecated. Use MinioStorage.presigned_put_url for direct uploads.")

    @staticmethod
    def delete_image(public_id: str):
        pass  # No-op for backward compatibility