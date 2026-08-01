from fastapi import APIRouter, Request, Depends, HTTPException, Form, UploadFile, File
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
import anyio
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
from sqlalchemy.orm import selectinload
from decimal import Decimal
import time

router = APIRouter()

EAGER = [
    {"width": 800, "height": 800, "crop": "fill", "quality": "auto:eco", "fetch_format": "auto"},
    {"width": 1200, "crop": "scale", "quality": "auto:eco", "fetch_format": "auto"},
]

# Short TTL cache for the global dashboard aggregate stats. The values only
# change when new orders/products are created, so a brief cache avoids running
# 4 aggregate scans on every dashboard load. Cleared between tests via
# _reset_dashboard_stats_cache().
_STATS_CACHE_TTL = 30.0
_stats_cache: dict = {"ts": 0.0, "value": None}


def _reset_dashboard_stats_cache() -> None:
    _stats_cache["ts"] = 0.0
    _stats_cache["value"] = None


async def _get_dashboard_stats(db: AsyncSession) -> dict:
    now = time.monotonic()
    cached = _stats_cache["value"]
    if cached is not None and (now - _stats_cache["ts"]) < _STATS_CACHE_TTL:
        return cached

    total_orders = (
        await db.execute(select(func.count(Order.id)))
    ).scalar() or 0
    total_sales = (
        await db.execute(
            select(func.sum(Order.total_amount)).where(Order.status == "completed")
        )
    ).scalar() or Decimal("0.0")
    pending_orders = (
        await db.execute(select(func.count(Order.id)).where(Order.status == "pending"))
    ).scalar() or 0
    active_products_count = (
        await db.execute(select(func.count(Product.id)).where(Product.in_stock == True))
    ).scalar() or 0

    value = {
        "total_orders": total_orders,
        "total_sales": total_sales,
        "pending_orders": pending_orders,
        "active_products_count": active_products_count,
    }
    _stats_cache["ts"] = now
    _stats_cache["value"] = value
    return value

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
    # Calculate Stats (cached; recomputed when stale)
    stats = await _get_dashboard_stats(db)

    # Recent Orders
    recent_orders_stmt = select(Order).order_by(desc(Order.created_at)).limit(5).options(selectinload(Order.items))
    recent_orders = (await db.execute(recent_orders_stmt)).scalars().all()

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "request": request,
            "seller_name": f"{seller.first_name} {seller.last_name}",
            "store_name": seller.store_name,
            "total_orders": stats["total_orders"],
            "total_sales": stats["total_sales"],
            "pending_orders": stats["pending_orders"],
            "active_products_count": stats["active_products_count"],
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
    statement = statement.options(selectinload(Order.items))
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
    
    order_stmt = select(Order).where(Order.id == order_id).options(selectinload(Order.items))
    order = (await db.execute(order_stmt)).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Decrypt sensitive data for display (separate variables — DON'T mutate ORM)
    buyer_phone = _safe_decrypt(order.buyer_phone)
    delivery_address = _safe_decrypt(order.delivery_address)
    
    # Fetch audit logs
    logs_stmt = select(OrderStatusLog).where(OrderStatusLog.order_id == order_id).order_by(OrderStatusLog.changed_at).limit(100)
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
        order_stmt = select(Order).where(Order.id == order_id).options(selectinload(Order.items))
        order = (await db.execute(order_stmt)).scalar_one_or_none()
        buyer_phone = _safe_decrypt(order.buyer_phone) if order else "Unknown"
        delivery_address = _safe_decrypt(order.delivery_address) if order else "Unknown"
        
        # Fetch audit logs
        logs_stmt = select(OrderStatusLog).where(OrderStatusLog.order_id == order_id).order_by(OrderStatusLog.changed_at).limit(100)
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
        image_url = await anyio.to_thread.run_sync(lambda: CloudinaryService.upload_image(content, eager=EAGER))
        seller.featured_image = image_url

    seller.updated_at = utc_now()
    
    db.add(seller)
    await db.commit()

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

