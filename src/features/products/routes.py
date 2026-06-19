from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_session
from src.templates_config import templates
from .services import ProductService
from src.features.auth.models import Seller
from src.utils.storage import CloudinaryService
from sqlmodel import select

router = APIRouter()

async def get_current_seller_id(request: Request):
    seller_id = request.session.get("seller_id")
    if not seller_id:
        raise HTTPException(status_code=303, headers={"Location": "/auth/login"})
    return seller_id

@router.get("/")
async def list_products(
    request: Request, 
    db: AsyncSession = Depends(get_session),
    seller_id: int = Depends(get_current_seller_id)
):
    products = await ProductService.get_seller_products(db, seller_id)
    
    # Fetch seller for sidebar context
    statement = select(Seller).where(Seller.id == seller_id)
    result = await db.execute(statement)
    seller = result.scalar_one_or_none()

    return templates.TemplateResponse(
        request,
        "products/list.html", 
        {
            "request": request, 
            "products": products,
            "seller_name": f"{seller.first_name} {seller.last_name}",
            "store_name": seller.store_name
        }
    )

@router.get("/add")
async def add_product_form(
    request: Request,
    db: AsyncSession = Depends(get_session),
    seller_id: int = Depends(get_current_seller_id)
):
    statement = select(Seller).where(Seller.id == seller_id)
    result = await db.execute(statement)
    seller = result.scalar_one_or_none()

    return templates.TemplateResponse(
        request,
        "products/form.html", 
        {
            "request": request,
            "seller_name": f"{seller.first_name} {seller.last_name}",
            "store_name": seller.store_name
        }
    )

@router.post("/add")
async def add_product(
    request: Request,
    db: AsyncSession = Depends(get_session),
    seller_id: int = Depends(get_current_seller_id)
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

    # Validation: Must have at least one image and one must be 'main'
    if not valid_images:
        statement = select(Seller).where(Seller.id == seller_id)
        result = await db.execute(statement)
        seller = result.scalar_one_or_none()
        return templates.TemplateResponse(
            request,
            "products/form.html",
            {
                "request": request,
                "error": "Please upload at least one image.",
                "seller_name": f"{seller.first_name} {seller.last_name}",
                "store_name": seller.store_name
            }
        )
    
    if "main" not in image_tags.values():
        statement = select(Seller).where(Seller.id == seller_id)
        result = await db.execute(statement)
        seller = result.scalar_one_or_none()
        return templates.TemplateResponse(
            request,
            "products/form.html",
            {
                "request": request,
                "error": "At least one image must be tagged as 'main'.",
                "seller_name": f"{seller.first_name} {seller.last_name}",
                "store_name": seller.store_name
            }
        )

    if not name or not price:
        # Fetch seller for sidebar context
        statement = select(Seller).where(Seller.id == seller_id)
        result = await db.execute(statement)
        seller = result.scalar_one_or_none()
        return templates.TemplateResponse(
            request,
            "products/form.html",
            {
                "request": request,
                "error": "Product name and price are required.",
                "seller_name": f"{seller.first_name} {seller.last_name}",
                "store_name": seller.store_name
            }
        )

    # Image Size Validation (5MB limit)
    MAX_SIZE = 5 * 1024 * 1024
    image_data = []

    for i, img in enumerate(valid_images):
        content = await img.read()
        if len(content) > MAX_SIZE:
            statement = select(Seller).where(Seller.id == seller_id)
            result = await db.execute(statement)
            seller = result.scalar_one_or_none()
            return templates.TemplateResponse(
                request,
                "products/form.html",
                {
                    "request": request,
                    "error": f"Image {img.filename} exceeds 5MB limit.",
                    "seller_name": f"{seller.first_name} {seller.last_name}",
                    "store_name": seller.store_name
                }
            )
        
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
                attributes_to_save.append({
                    "type": attr_types[i],
                    "value": attr_values[i],
                    "extra_price": float(attr_prices[i]) if attr_prices[i] else 0.0
                })
        
        if attributes_to_save:
            await ProductService.update_product_attributes(db, product.id, attributes_to_save)

    except Exception as e:
        await db.rollback()
        # Fetch seller for sidebar context
        statement = select(Seller).where(Seller.id == seller_id)
        result = await db.execute(statement)
        seller = result.scalar_one_or_none()
        return templates.TemplateResponse(
            request,
            "products/form.html",
            {
                "request": request,
                "error": f"Failed to create product: {str(e)}",
                "seller_name": f"{seller.first_name} {seller.last_name}",
                "store_name": seller.store_name
            }
        )
    
    from .models import ProductImage
    for content, tag in image_data:
        image_url = CloudinaryService.upload_image(content)
        new_image = ProductImage(product_id=product.id, image_url=image_url, image_tag=tag)
        db.add(new_image)
    
    await db.commit()

    return RedirectResponse(url="/dashboard/products", status_code=303)

@router.get("/edit/{product_id}")
async def edit_product_form(
    product_id: int,
    request: Request,
    db: AsyncSession = Depends(get_session),
    seller_id: int = Depends(get_current_seller_id)
):
    product = await ProductService.get_product_by_id(db, product_id)
    if not product or product.seller_id != seller_id:
        raise HTTPException(status_code=404, detail="Product not found")
    
    statement = select(Seller).where(Seller.id == seller_id)
    result = await db.execute(statement)
    seller = result.scalar_one_or_none()

    return templates.TemplateResponse(
        request,
        "products/form.html", 
        {
            "request": request, 
            "product": product,
            "seller_name": f"{seller.first_name} {seller.last_name}",
            "store_name": seller.store_name
        }
    )

@router.post("/edit/{product_id}")
async def edit_product(
    product_id: int,
    request: Request,
    db: AsyncSession = Depends(get_session),
    seller_id: int = Depends(get_current_seller_id)
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
    if not product or product.seller_id != seller_id:
        raise HTTPException(status_code=404, detail="Product not found")
    
    if not name or not price:
        return templates.TemplateResponse(
            request,
            "products/form.html",
            {
                "request": request,
                "product": product,
                "error": "Product name and price are required."
            }
        )

    # 1. Update Tags for existing images
    for i, img in enumerate(product.images):
        new_tag = image_tags.get(f"image_tag_{i}")
        if new_tag:
            img.image_tag = new_tag
            db.add(img)

    # 2. Handle New Image Uploads (if any)
    MAX_SIZE = 5 * 1024 * 1024
    if valid_images:
        # Clear existing images - cascade="all, delete-orphan" handles deletion
        product.images.clear()
            
        for i, img in enumerate(valid_images):
            content = await img.read()
            if len(content) > MAX_SIZE:
                return templates.TemplateResponse(
                    request,
                    "products/form.html",
                    {
                        "request": request,
                        "product": product,
                        "error": f"Image {img.filename} exceeds 5MB limit."
                    }
                )
            image_url = CloudinaryService.upload_image(content)
            # Use new index starting from 0 since we cleared existing images
            tag = image_tags.get(f"image_tag_{i}", "main" if i == 0 else "gallery")
            from .models import ProductImage
            new_image = ProductImage(product_id=product.id, image_url=image_url, image_tag=tag)
            product.images.append(new_image)

    # 3. Process and save attributes
    attr_types = form.getlist("attr_type[]")
    attr_values = form.getlist("attr_value[]")
    attr_prices = form.getlist("attr_price[]")
    
    attributes_to_save = []
    for i in range(len(attr_types)):
        if attr_types[i] and attr_values[i]:
            attributes_to_save.append({
                "type": attr_types[i],
                "value": attr_values[i],
                "extra_price": float(attr_prices[i]) if attr_prices[i] else 0.0
            })
    
    if attributes_to_save:
        await ProductService.update_product_attributes(db, product.id, attributes_to_save)
    else:
        # If no attributes in form, clear existing ones
        product.attributes.clear()
        db.add(product)

    await ProductService.update_product(
        db, product_id, name=name, description=description, price=float(price), in_stock=in_stock
    )
    await db.commit()

    return RedirectResponse(url="/dashboard/products", status_code=303)

@router.delete("/{product_id}")
async def delete_product(
    product_id: int,
    db: AsyncSession = Depends(get_session),
    seller_id: int = Depends(get_current_seller_id)
):
    product = await ProductService.get_product_by_id(db, product_id)
    if not product or product.seller_id != seller_id:
        raise HTTPException(status_code=404, detail="Product not found")
    
    await ProductService.delete_product(db, product_id)
    return HTMLResponse(content="")

@router.post("/{product_id}/toggle-stock")
async def toggle_stock(
    product_id: int,
    request: Request,
    db: AsyncSession = Depends(get_session),
    seller_id: int = Depends(get_current_seller_id)
):
    product = await ProductService.get_product_by_id(db, product_id)
    if not product or product.seller_id != seller_id:
        raise HTTPException(status_code=404, detail="Product not found")
    
    new_status = not product.in_stock
    product = await ProductService.update_product(db, product_id, in_stock=new_status)
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found after update")
    
    return templates.TemplateResponse(
        request,
        "products/_stock_toggle.html",
        {"product": product}
    )
