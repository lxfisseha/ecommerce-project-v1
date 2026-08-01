import math
import anyio
from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_session
from src.templates_config import templates
from .services import ProductService
from .models import ProductImage
from src.dependencies import require_seller_id
from src.utils.storage import CloudinaryService
from src.constants import MAX_IMAGE_SIZE
from sqlmodel import select

router = APIRouter()

EAGER = [
    {"width": 160, "height": 160, "crop": "fill", "quality": "auto:eco", "fetch_format": "auto"},
    {"width": 400, "height": 400, "crop": "fill", "quality": "auto:eco", "fetch_format": "auto"},
    {"width": 800, "height": 800, "crop": "fill", "quality": "auto:eco", "fetch_format": "auto"},
]


def _form_response(request, error=None, seller_name="Seller", store_name="Store", **extra):
    ctx = {"request": request, "seller_name": seller_name, "store_name": store_name}
    if error:
        ctx["error"] = error
    ctx.update(extra)
    return templates.TemplateResponse(request, "products/form.html", ctx)


@router.get("/")
async def list_products(
    request: Request, 
    search: str = Query(None),
    page: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_session),
    seller_id: int = Depends(require_seller_id)
):
    if search and len(search) > 100:
        search = search[:100]

    per_page = 12
    offset = (page - 1) * per_page

    if search:
        products, total_count = await ProductService.search_products_paginated(db, search, limit=per_page, offset=offset)
    else:
        products, total_count = await ProductService.get_products_paginated(db, limit=per_page, offset=offset)
    
    total_pages = math.ceil(total_count / per_page) if total_count > 0 else 1

    context = {
        "request": request, 
        "products": products,
        "search": search,
        "current_page": page,
        "total_pages": total_pages,
        "seller_name": request.session.get("seller_name", "Seller"),
        "store_name": request.session.get("store_name", "Store")
    }

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "products/_product_list_content.html", context)

    return templates.TemplateResponse(request, "products/list.html", context)

@router.get("/add")
async def add_product_form(
    request: Request,
    db: AsyncSession = Depends(get_session),
    seller_id: int = Depends(require_seller_id)
):
    return templates.TemplateResponse(
        request,
        "products/form.html", 
        {
            "request": request,
            "seller_name": request.session.get("seller_name", "Seller"),
            "store_name": request.session.get("store_name", "Store")
        }
    )

@router.post("/add")
async def add_product(
    request: Request,
    db: AsyncSession = Depends(get_session),
    seller_id: int = Depends(require_seller_id)
):
    form = getattr(request.state, "form_data", None) or await request.form()
    name = form.get("name")
    description = form.get("description")
    price = form.get("price")
    in_stock = form.get("in_stock") == "on"
    
    # Handle multiple images and tags
    images = form.getlist("image")
    valid_images = [img for img in images if hasattr(img, "filename") and img.filename]
    
    # Process image tags from the form
    image_tags = {k: v for k, v in form.items() if k.startswith("image_tag_")}

    seller_name = request.session.get("seller_name", "Seller")
    store_name = request.session.get("store_name", "Store")

    # Validation: Must have at least one image and one must be 'main'
    if not valid_images:
        return _form_response(request, "Please upload at least one image.", seller_name, store_name)

    if "main" not in image_tags.values():
        return _form_response(request, "At least one image must be tagged as 'main'.", seller_name, store_name)

    if not name or not price:
        return _form_response(request, "Product name and price are required.", seller_name, store_name)

    image_data = []

    ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

    for i, img in enumerate(valid_images):
        if img.content_type not in ALLOWED_IMAGE_TYPES:
            return _form_response(request, f"Image {img.filename} has invalid type ({img.content_type}). Allowed: JPEG, PNG, WebP, GIF.", seller_name, store_name)
        content = await img.read()
        if len(content) > MAX_IMAGE_SIZE:
            return _form_response(request, f"Image {img.filename} exceeds 5MB limit.", seller_name, store_name)
        
        tag = image_tags.get(f"image_tag_{i}", "main" if i == 0 else "gallery")
        image_data.append((content, tag))

    try:
        product = await ProductService.create_product(
            db, seller_id, name, description, float(price), in_stock
        )
        
        # Process and save dynamic attributes
        attr_types = form.getlist("attr_type[]")
        attr_values = form.getlist("attr_value[]")
        attr_prices = form.getlist("attr_price[]")
        
        attributes_to_save = []
        for i in range(len(attr_types)):
            if attr_types[i] and attr_values[i]:
                for val in attr_values[i].split(","):
                    trimmed_val = val.strip()
                    if trimmed_val:
                        attributes_to_save.append({
                            "type": attr_types[i],
                            "value": trimmed_val,
                            "extra_price": float(attr_prices[i]) if attr_prices[i] else 0.0
                        })
        
        if attributes_to_save:
            await ProductService.update_product_attributes(db, product.id, attributes_to_save)

        # Process and save tags
        tags_string = form.get("tags", "")
        await ProductService.sync_product_tags(db, product, tags_string)

    except Exception as e:
        await db.rollback()
        return _form_response(request, f"Failed to create product: {str(e)}", seller_name, store_name)
    
    try:
        for content, tag in image_data:
            image_url = await anyio.to_thread.run_sync(
                lambda: CloudinaryService.upload_image(content, eager=EAGER)
            )
            new_image = ProductImage(product_id=product.id, image_url=image_url, image_tag=tag)
            db.add(new_image)
        
        await db.commit()
    except Exception as e:
        await db.rollback()
        return _form_response(request, f"Failed to upload images: {str(e)}. Please try again.", seller_name, store_name)

    return RedirectResponse(url="/dashboard/products", status_code=303)

@router.get("/edit/{product_id}")
async def edit_product_form(
    product_id: int,
    request: Request,
    db: AsyncSession = Depends(get_session),
    seller_id: int = Depends(require_seller_id)
):
    product = await ProductService.get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    tags_string = ", ".join([tag.name for tag in product.tags])

    return templates.TemplateResponse(
        request,
        "products/form.html", 
        {
            "request": request, 
            "product": product,
            "tags_string": tags_string,
            "seller_name": request.session.get("seller_name", "Seller"),
            "store_name": request.session.get("store_name", "Store")
        }
    )

@router.post("/edit/{product_id}")
async def edit_product(
    product_id: int,
    request: Request,
    db: AsyncSession = Depends(get_session),
    seller_id: int = Depends(require_seller_id)
):
    form = getattr(request.state, "form_data", None) or await request.form()
    name = form.get("name")
    description = form.get("description")
    price = form.get("price")
    in_stock = form.get("in_stock") == "on"
    
    # Process image tags from the form
    image_tags = {k: v for k, v in form.items() if k.startswith("image_tag_")}
    
    # Handle multiple images
    images = form.getlist("image")
    valid_images = [img for img in images if hasattr(img, "filename") and img.filename]
    
    # Get existing image count for correct tag indexing
    existing_image_count = int(form.get("existing_image_count", 0))

    product = await ProductService.get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    if not name or not price:
        return _form_response(request, "Product name and price are required.", product=product)

    # 1. Update Tags for existing images
    for i, img in enumerate(product.images):
        new_tag = image_tags.get(f"image_tag_{i}")
        if new_tag:
            img.image_tag = new_tag
            db.add(img)

    # 2. Handle New Image Uploads (if any)
    if valid_images:
        # Delete old Cloudinary images before clearing
        from src.utils.storage import CloudinaryService
        for old_img in product.images:
            if old_img.image_url:
                try:
                    await anyio.to_thread.run_sync(
                        lambda: CloudinaryService.delete_image(old_img.image_url)
                    )
                except Exception:
                    pass
        product.images.clear()
            
        for i, img in enumerate(valid_images):
            content = await img.read()
            if len(content) > MAX_IMAGE_SIZE:
                return _form_response(request, f"Image {img.filename} exceeds 5MB limit.", product=product)
            try:
                image_url = await anyio.to_thread.run_sync(
                    lambda: CloudinaryService.upload_image(content, eager=EAGER)
                )
            except Exception as e:
                return _form_response(request, f"Failed to upload image {img.filename}: {str(e)}. Please try again.", product=product)
            # Use new index starting from 0 since we cleared existing images
            tag = image_tags.get(f"image_tag_{i}", "main" if i == 0 else "gallery")
            new_image = ProductImage(product_id=product.id, image_url=image_url, image_tag=tag)
            product.images.append(new_image)

    # 3. Process and save attributes
    attr_types = form.getlist("attr_type[]")
    attr_values = form.getlist("attr_value[]")
    attr_prices = form.getlist("attr_price[]")
    
    attributes_to_save = []
    for i in range(len(attr_types)):
        if attr_types[i] and attr_values[i]:
            for val in attr_values[i].split(","):
                trimmed_val = val.strip()
                if trimmed_val:
                    attributes_to_save.append({
                        "type": attr_types[i],
                        "value": trimmed_val,
                        "extra_price": float(attr_prices[i]) if attr_prices[i] else 0.0
                    })
    
    if attributes_to_save:
        await ProductService.update_product_attributes(db, product.id, attributes_to_save)
    else:
        # If no attributes in form, clear existing ones
        product.attributes.clear()
        db.add(product)

    # Sync tags
    tags_string = form.get("tags", "")
    await ProductService.sync_product_tags(db, product, tags_string)

    await ProductService.update_product(
        db, product_id, name=name, description=description, price=float(price), in_stock=in_stock
    )
    await db.commit()

    return RedirectResponse(url="/dashboard/products", status_code=303)

@router.delete("/{product_id}")
async def delete_product(
    product_id: int,
    db: AsyncSession = Depends(get_session),
    seller_id: int = Depends(require_seller_id)
):
    product = await ProductService.get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    await ProductService.delete_product(db, product_id)
    return HTMLResponse(content="")

@router.post("/{product_id}/toggle-stock")
async def toggle_stock(
    product_id: int,
    request: Request,
    db: AsyncSession = Depends(get_session),
    seller_id: int = Depends(require_seller_id)
):
    product = await ProductService.get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    new_status = not product.in_stock
    product = await ProductService.update_product(db, product_id, in_stock=new_status)
    await db.commit()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found after update")
    
    return templates.TemplateResponse(
        request,
        "products/_stock_toggle.html",
        {"product": product}
    )
