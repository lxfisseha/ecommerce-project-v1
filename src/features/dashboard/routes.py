from fastapi import APIRouter, Request, Depends, HTTPException, Form, UploadFile, File
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_session
from src.dependencies import require_current_seller
from src.templates_config import templates
from src.features.auth.models import Seller
from src.features.orders.models import Order, OrderStatusLog
from src.features.orders.services import OrderService
from src.features.products.models import Product
from src.utils.crypto import decrypt_data
from src.utils.datetime import utc_now
from src.utils.phone import validate_ethiopian_phone, normalize_phone
from src.utils.storage import CloudinaryService
from src.constants import MAX_IMAGE_SIZE
from sqlmodel import select, func, desc
from decimal import Decimal

router = APIRouter()

def _safe_decrypt(data):
    try:
        return decrypt_data(data)
    except ValueError:
        return "Unable to decrypt"

@router.get("/")
async def get_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_session),
    seller: Seller = Depends(require_current_seller)
):
    # Calculate Stats
    # 1. Total Orders
    total_orders_stmt = select(func.count(Order.id))
    total_orders = (await db.execute(total_orders_stmt)).scalar() or 0

    # 2. Total Sales (Completed only)
    total_sales_stmt = select(func.sum(Order.total_amount)).where(Order.status == "completed")
    total_sales = (await db.execute(total_sales_stmt)).scalar() or Decimal("0.0")

    # 3. Pending Orders
    pending_orders_stmt = select(func.count(Order.id)).where(Order.status == "pending")
    pending_orders = (await db.execute(pending_orders_stmt)).scalar() or 0

    # 4. Active Products (Items currently marked as in stock)
    active_products_stmt = select(func.count(Product.id)).where(Product.in_stock == True)
    active_products_count = (await db.execute(active_products_stmt)).scalar() or 0

    # Recent Orders
    recent_orders_stmt = select(Order).order_by(desc(Order.created_at)).limit(5)
    recent_orders = (await db.execute(recent_orders_stmt)).scalars().all()

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "request": request,
            "seller_name": f"{seller.first_name} {seller.last_name}",
            "store_name": seller.store_name,
            "total_orders": total_orders,
            "total_sales": total_sales,
            "pending_orders": pending_orders,
            "active_products_count": active_products_count,
            "recent_orders": recent_orders
        },
    )

@router.get("/orders", response_class=HTMLResponse)
async def list_orders(
    request: Request,
    status: str | None = None,
    page: int = 1,
    db: AsyncSession = Depends(get_session),
    seller: Seller = Depends(require_current_seller)
):
    
    per_page = 20
    offset = (page - 1) * per_page

    # Count query
    count_stmt = select(func.count(Order.id))
    if status:
        count_stmt = count_stmt.where(Order.status == status)
    total_orders = (await db.execute(count_stmt)).scalar() or 0
    total_pages = (total_orders + per_page - 1) // per_page

    # Data query
    statement = select(Order)
    if status:
        statement = statement.where(Order.status == status)
    
    statement = statement.order_by(desc(Order.created_at)).offset(offset).limit(per_page)
    result = await db.execute(statement)
    orders = result.scalars().all()

    return templates.TemplateResponse(
        request,
        "dashboard/orders_list.html",
        {
            "request": request,
            "orders": orders,
            "current_status": status,
            "current_page": page,
            "total_pages": total_pages,
            "seller_name": f"{seller.first_name} {seller.last_name}",
            "store_name": seller.store_name
        }
    )

@router.get("/orders/{order_id}", response_class=HTMLResponse)
async def order_detail(
    order_id: int,
    request: Request,
    db: AsyncSession = Depends(get_session),
    seller: Seller = Depends(require_current_seller)
):
    
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Decrypt sensitive data for display (separate variables — DON'T mutate ORM)
    buyer_phone = _safe_decrypt(order.buyer_phone)
    delivery_address = _safe_decrypt(order.delivery_address)
    
    # Fetch audit logs
    logs_stmt = select(OrderStatusLog).where(OrderStatusLog.order_id == order_id).order_by(OrderStatusLog.changed_at)
    logs = (await db.execute(logs_stmt)).scalars().all()
    
    return templates.TemplateResponse(
        request,
        "dashboard/order_detail.html",
        {
            "request": request,
            "order": order,
            "buyer_phone": buyer_phone,
            "delivery_address": delivery_address,
            "logs": logs,
            "seller_name": f"{seller.first_name} {seller.last_name}",
            "store_name": seller.store_name
        }
    )

@router.post("/orders/{order_id}/status")
async def update_order_status(
    order_id: int,
    request: Request,
    new_status: str = Form(...),
    context: str = Form(None),
    db: AsyncSession = Depends(get_session),
    seller: Seller = Depends(require_current_seller)
):
    
    valid_statuses = ("pending", "shipped", "completed", "cancelled")
    if new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status: {new_status}")

    try:
        await OrderService.update_order_status(db, order_id, new_status, changed_by="seller", context=context)
        return RedirectResponse(url=f"/dashboard/orders/{order_id}", status_code=303)
    except ValueError as e:
        # Handle invalid transitions
        order = await db.get(Order, order_id)
        buyer_phone = _safe_decrypt(order.buyer_phone) if order else "Unknown"
        delivery_address = _safe_decrypt(order.delivery_address) if order else "Unknown"
        
        # Fetch audit logs
        logs_stmt = select(OrderStatusLog).where(OrderStatusLog.order_id == order_id).order_by(OrderStatusLog.changed_at)
        logs = (await db.execute(logs_stmt)).scalars().all()
        
        return templates.TemplateResponse(
            request,
            "dashboard/order_detail.html",
            {
                "request": request,
                "order": order,
                "buyer_phone": buyer_phone,
                "delivery_address": delivery_address,
                "logs": logs,
                "error": str(e),
                "seller_name": f"{seller.first_name} {seller.last_name}",
                "store_name": seller.store_name
            }
        )

@router.get("/profile", response_class=HTMLResponse)
async def get_profile(
    request: Request,
    db: AsyncSession = Depends(get_session),
    seller: Seller = Depends(require_current_seller)
):
    
    # Decrypt phone number for display (separate variable — DON'T mutate ORM)
    decrypted_phone = f"+251{_safe_decrypt(seller.phone)}"
    
    return templates.TemplateResponse(
        request,
        "dashboard/profile.html",
        {
            "request": request,
            "seller": seller,
            "decrypted_phone": decrypted_phone,
            "seller_name": f"{seller.first_name} {seller.last_name}",
            "store_name": seller.store_name
        }
    )

@router.post("/profile")
async def update_profile(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    store_name: str = Form(...),
    business_email: str = Form(None),
    business_address: str = Form(None),
    telegram_username: str = Form(None),
    business_contact_number: str = Form(None),
    featured_image: UploadFile = File(None),
    db: AsyncSession = Depends(get_session),
    seller: Seller = Depends(require_current_seller)
):
    
    # Validate business contact number if provided
    normalized_contact = None
    if business_contact_number:
        if not validate_ethiopian_phone(business_contact_number):
            decrypted_phone = f"+251{_safe_decrypt(seller.phone)}"
            return templates.TemplateResponse(
                request,
                "dashboard/profile.html",
                {
                    "request": request,
                    "seller": seller,
                    "decrypted_phone": decrypted_phone,
                    "seller_name": f"{seller.first_name} {seller.last_name}",
                    "store_name": seller.store_name,
                    "error": "Invalid business phone number format."
                }
            )
        normalized_contact = normalize_phone(business_contact_number)

    # Check store name uniqueness if it changed
    if store_name != seller.store_name:
        existing_seller = await db.execute(select(Seller).where(Seller.store_name == store_name))
        if existing_seller.scalar_one_or_none():
            decrypted_phone = f"+251{_safe_decrypt(seller.phone)}"
            return templates.TemplateResponse(
                request,
                "dashboard/profile.html",
                {
                    "request": request,
                    "seller": seller,
                    "decrypted_phone": decrypted_phone,
                    "seller_name": f"{seller.first_name} {seller.last_name}",
                    "store_name": seller.store_name,
                    "error": "Store name already exists."
                }
            )

    seller.first_name = first_name[:50]
    seller.last_name = last_name[:50]
    seller.store_name = store_name[:100]
    seller.business_email = business_email[:255] if business_email else business_email
    seller.business_address = business_address[:255] if business_address else business_address
    seller.telegram_username = telegram_username
    seller.business_contact_number = normalized_contact
    
    if featured_image and featured_image.filename:
        ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
        if featured_image.content_type not in ALLOWED_IMAGE_TYPES:
            decrypted_phone = f"+251{_safe_decrypt(seller.phone)}"
            return templates.TemplateResponse(
                request,
                "dashboard/profile.html",
                {
                    "request": request,
                    "seller": seller,
                    "decrypted_phone": decrypted_phone,
                    "seller_name": f"{seller.first_name} {seller.last_name}",
                    "store_name": seller.store_name,
                    "error": f"Invalid file type ({featured_image.content_type}). Allowed: JPEG, PNG, WebP, GIF."
                }
            )
        content = await featured_image.read()
        if len(content) > MAX_IMAGE_SIZE:
            decrypted_phone = f"+251{_safe_decrypt(seller.phone)}"
            return templates.TemplateResponse(
                request,
                "dashboard/profile.html",
                {
                    "request": request,
                    "seller": seller,
                    "decrypted_phone": decrypted_phone,
                    "seller_name": f"{seller.first_name} {seller.last_name}",
                    "store_name": seller.store_name,
                    "error": "Featured image exceeds 5MB limit."
                }
            )
        image_url = CloudinaryService.upload_image(content)
        seller.featured_image = image_url

    seller.updated_at = utc_now()
    
    db.add(seller)
    await db.commit()
    await db.refresh(seller)

    # Refresh session name fields so product routes see the update
    request.session["seller_name"] = f"{seller.first_name} {seller.last_name}"
    request.session["store_name"] = seller.store_name

    # Prepare decrypted phone for re-display
    decrypted_phone = f"+251{_safe_decrypt(seller.phone)}"
    # Do NOT prepend 251 to business_contact_number; it is already normalized and the UI handles the label.
    
    return templates.TemplateResponse(
        request,
        "dashboard/profile.html",
        {
            "request": request,
            "seller": seller,
            "decrypted_phone": decrypted_phone,
            "seller_name": f"{seller.first_name} {seller.last_name}",
            "store_name": seller.store_name,
            "message": "Profile updated successfully!"
        }
    )

