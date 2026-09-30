"""
Background image processing worker.
Uses RQ (Redis Queue) for job management and Pillow for image processing.
Generates 3 WebP variants: thumb (160w), medium (400w), large (800w).
"""
import os
import sys
import uuid
import io
import logging
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from minio import Minio
from minio.error import S3Error
from PIL import Image
import redis
from rq import Queue, Worker
from src.config import settings
from src.database import init_db, async_session_maker
from src.features.products.models import ProductImage
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.utils.storage import MinioStorage
from src.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Image size variants (width in pixels)
SIZES = {
    "thumb": 160,
    "medium": 400,
    "large": 800,
}

OUTPUT_FORMAT = "WEBP"
OUTPUT_QUALITY = 80


def get_minio_client() -> "Minio":
    """Get MinIO client instance."""
    from minio import Minio
    from minio.error import S3Error
    from src.config import settings
    
    return Minio(
        endpoint=settings.MINIO_ENDPOINT.replace("http://", "").replace("https://", ""),
        access_key=settings.MINIO_ACCESS_KEY or settings.MINIO_ROOT_USER,
        secret_key=settings.MINIO_SECRET_KEY or settings.MINIO_ROOT_PASSWORD,
        secure=settings.MINIO_ENDPOINT.startswith("https"),
    )


def process_image_task(image_id: int) -> dict:
    """
    Background task to process an image.
    Generates 3 WebP variants and updates the database.
    """
    # Import inside function to avoid circular imports
    import asyncio
    from sqlmodel import select
    from src.database import init_db, async_session_maker
    from src.features.products.models import ProductImage
    from sqlmodel import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from src.utils.storage import MinioStorage
    from src.config import settings
    
    async def process():
        async with async_session_maker() as session:
            # Get the image record
            result = await session.execute(
                select(ProductImage).where(ProductImage.id == image_id)
            )
            image = result.scalar_one_or_none()
            
            if not image:
                logger.error(f"Image {image_id} not found")
                return {"status": "error", "message": "Image not found"}
            
            # Check if already processed
            if image.processing_status == "completed":
                logger.info(f"Image {image_id} already processed")
                return {"status": "skipped", "message": "Already processed"}
            
            # Update status to processing
            image.processing_status = "processing"
            await session.commit()
            
            storage = MinioStorage()
            
            try:
                # Get original image from MinIO
                original_object = image.object_name
                if not original_object:
                    raise ValueError("No object_name on image record")
                
                # Download original from MinIO
                response = storage.client.get_object(
                    bucket_name=storage.bucket,
                    object_name=original_object
                )
                image_data = response.read()
                response.close()
                response.release_conn()
                
                # Open image with Pillow
                img = Image.open(io.BytesIO(image_data))
                img.load()  # Force load to catch errors early
                
                # Convert to RGB if needed (for WebP)
                if img.mode in ('RGBA', 'LA', 'P'):
                    # Create white background
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Generate variants
                variants = {}
                for size_name, width in SIZES.items():
                    # Calculate height maintaining aspect ratio
                    aspect_ratio = img.height / img.width
                    height = int(width * aspect_ratio)
                    
                    # Resize
                    resized = img.resize((width, height), Image.Resampling.LANCZOS)
                    
                    # Save to bytes
                    output = io.BytesIO()
                    resized.save(output, format=OUTPUT_FORMAT, quality=OUTPUT_QUALITY, method=6)
                    output.seek(0)
                    
                    # Upload to MinIO
                    variant_object = f"products/{original_object.split('/')[-1].split('.')[0]}_{width}w.webp"
                    storage.client.put_object(
                        bucket_name=settings.MINIO_BUCKET,
                        object_name=f"processed/{variant_object}",
                        data=output,
                        length=output.getbuffer().nbytes,
                        content_type="image/webp",
                    )
                    
                    variants[size_name] = f"processed/{variant_object}"
                
                # Update database with processed URLs
                image.processed_urls = variants
                image.processing_status = "completed"
                image.processed_at = datetime.utcnow()
                await session.commit()
                
                logger.info(f"Successfully processed image {image_id}")
                return {"status": "completed", "variants": variants}
            
            except Exception as e:
                logger.error(f"Failed to process image {image_id}: {e}")
                image.processing_status = "failed"
                image.processing_error = str(e)
                await session.commit()
                return {"status": "error", "message": str(e)}
    
    return asyncio.run(process())


def enqueue_image_processing(image_id: int) -> str:
    """Enqueue an image processing job."""
    redis_conn = redis.Redis(
        host=settings.REDIS_HOST if hasattr(settings, 'REDIS_HOST') else 'redis',
        port=settings.REDIS_PORT if hasattr(settings, 'REDIS_PORT') else 6379,
        decode_responses=True,
    )
    q = Queue(connection=redis_conn)
    job = q.enqueue(process_image_task, image_id)
    return job.id


if __name__ == "__main__":
    import io
    from datetime import datetime
    import sys
    
    # If run directly, run as worker
    redis_conn = redis.Redis(
        host=settings.REDIS_HOST if hasattr(settings, 'REDIS_HOST') else 'redis',
        port=settings.REDIS_PORT if hasattr(settings, 'REDIS_PORT') else 6379,
        decode_responses=True,
    )
    
    q = Queue(connection=redis_conn)
    
    if len(sys.argv) > 1:
        # Process a single image
        image_id = int(sys.argv[1])
        result = process_image_task(image_id)
        print(f"Result: {result}")
    else:
        # Run as worker
        logger.info("Starting RQ worker...")
        w = Worker([q], connection=redis_conn)
        w.work()