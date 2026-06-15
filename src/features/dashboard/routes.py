from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_session
from src.templates_config import templates
from src.features.auth.models import Seller
from src.features.orders.models import Order
from src.features.orders.services import OrderService
from src.features.products.models import Product
from src.utils.crypto import decrypt_data
from src.utils.datetime import utc_now
from src.utils.phone import validate_ethiopian_phone, normalize_phone
from sqlmodel import select, func, desc
from decimal import Decimal

router = APIRouter()

async def get_current_seller(request: Request, db: AsyncSession):
    seller_id = request.session.get("seller_id")
    if not seller_id:
        return None
    result = await db.execute(select(Seller).where(Seller.id == int(seller_id)))
    return result.scalar_one_or_none()

@router.get("/")
async def get_dashboard(request: Request, db: AsyncSession = Depends(get_session)):
    seller = await get_current_seller(request, db)
    if not seller:
        return RedirectResponse(url="/auth/login")

    # Calculate Stats
    # 1. Total Orders
    total_orders_stmt = select(func.count(Order.id)).where(Order.seller_id == seller.id)
    total_orders = (await db.execute(total_orders_stmt)).scalar() or 0

    # 2. Total Sales (Completed only)
    total_sales_stmt = select(func.sum(Order.total_amount)).where(
        Order.seller_id == seller.id, 
        Order.status == "completed"
    )
    total_sales = (await db.execute(total_sales_stmt)).scalar() or Decimal("0.0")

    # 3. Pending Orders
    pending_orders_stmt = select(func.count(Order.id)).where(
        Order.seller_id == seller.id, 
        Order.status == "pending"
    )
    pending_orders = (await db.execute(pending_orders_stmt)).scalar() or 0

    # 4. Active Products (Items currently marked as in stock)
    active_products_stmt = select(func.count(Product.id)).where(
        Product.seller_id == seller.id,
        Product.in_stock == True
    )
    active_products_count = (await db.execute(active_products_stmt)).scalar() or 0

    # Recent Orders
    recent_orders_stmt = select(Order).where(Order.seller_id == seller.id).order_by(desc(Order.created_at)).limit(5)
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
    db: AsyncSession = Depends(get_session)
):
    seller = await get_current_seller(request, db)
    if not seller:
        return RedirectResponse(url="/auth/login")
    
    statement = select(Order).where(Order.seller_id == seller.id)
    if status:
        statement = statement.where(Order.status == status)
    
    statement = statement.order_by(desc(Order.created_at))
    result = await db.execute(statement)
    orders = result.scalars().all()

    return templates.TemplateResponse(
        request,
        "dashboard/orders_list.html",
        {
            "request": request,
            "orders": orders,
            "current_status": status,
            "seller_name": f"{seller.first_name} {seller.last_name}",
            "store_name": seller.store_name
        }
    )

@router.get("/orders/{order_id}", response_class=HTMLResponse)
async def order_detail(
    order_id: int,
    request: Request,
    db: AsyncSession = Depends(get_session)
):
    seller = await get_current_seller(request, db)
    if not seller:
        return RedirectResponse(url="/auth/login")
    
    order = await db.get(Order, order_id)
    if not order or order.seller_id != seller.id:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Decrypt sensitive data for display
    order.buyer_phone = decrypt_data(order.buyer_phone)
    order.delivery_address = decrypt_data(order.delivery_address)
    
    # Fetch audit logs
    logs_stmt = select(OrderStatusLog).where(OrderStatusLog.order_id == order_id).order_by(OrderStatusLog.changed_at)
    logs = (await db.execute(logs_stmt)).scalars().all()
    
    return templates.TemplateResponse(
        request,
        "dashboard/order_detail.html",
        {
            "request": request,
            "order": order,
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
    db: AsyncSession = Depends(get_session)
):
    seller = await get_current_seller(request, db)
    if not seller:
        raise HTTPException(status_code=401)
    
    try:
        await OrderService.update_order_status(db, order_id, new_status, changed_by="seller", context=context)
        return RedirectResponse(url=f"/dashboard/orders/{order_id}", status_code=303)
    except ValueError as e:
        # Handle invalid transitions
        order = await db.get(Order, order_id)
        order.buyer_phone = decrypt_data(order.buyer_phone)
        order.delivery_address = decrypt_data(order.delivery_address)
        
        # Fetch audit logs
        logs_stmt = select(OrderStatusLog).where(OrderStatusLog.order_id == order_id).order_by(OrderStatusLog.changed_at)
        logs = (await db.execute(logs_stmt)).scalars().all()
        
        return templates.TemplateResponse(
            request,
            "dashboard/order_detail.html",
            {
                "request": request,
                "order": order,
                "logs": logs,
                "error": str(e),
                "seller_name": f"{seller.first_name} {seller.last_name}",
                "store_name": seller.store_name
            }
        )

@router.get("/profile", response_class=HTMLResponse)
async def get_profile(
    request: Request,
    db: AsyncSession = Depends(get_session)
):
    seller = await get_current_seller(request, db)
    if not seller:
        return RedirectResponse(url="/auth/login")
    
    # Decrypt phone number for display
    seller.phone = f"+251{decrypt_data(seller.phone)}"
    
    return templates.TemplateResponse(
        request,
        "dashboard/profile.html",
        {
            "request": request,
            "seller": seller,
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
    db: AsyncSession = Depends(get_session)
):
    seller = await get_current_seller(request, db)
    if not seller:
        raise HTTPException(status_code=401)
    
    # Validate business contact number if provided
    normalized_contact = None
    if business_contact_number:
        if not validate_ethiopian_phone(business_contact_number):
            seller.phone = f"+251{decrypt_data(seller.phone)}"
            return templates.TemplateResponse(
                request,
                "dashboard/profile.html",
                {
                    "request": request,
                    "seller": seller,
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
            # Error handling in template (re-displaying)
            seller.phone = f"+251{decrypt_data(seller.phone)}"
            return templates.TemplateResponse(
                request,
                "dashboard/profile.html",
                {
                    "request": request,
                    "seller": seller,
                    "seller_name": f"{seller.first_name} {seller.last_name}",
                    "store_name": seller.store_name,
                    "error": "Store name already exists."
                }
            )

    seller.first_name = first_name
    seller.last_name = last_name
    seller.store_name = store_name
    seller.business_email = business_email
    seller.business_address = business_address
    seller.telegram_username = telegram_username
    seller.business_contact_number = normalized_contact
    seller.updated_at = utc_now()
    
    db.add(seller)
    await db.commit()
    await db.refresh(seller)
    
    # Prepare decrypted phone for re-display
    seller.phone = f"+251{decrypt_data(seller.phone)}"
    # Do NOT prepend 251 to business_contact_number; it is already normalized and the UI handles the label.
    
    return templates.TemplateResponse(
        request,
        "dashboard/profile.html",
        {
            "request": request,
            "seller": seller,
            "seller_name": f"{seller.first_name} {seller.last_name}",
            "store_name": seller.store_name,
            "message": "Profile updated successfully!"
        }
    )
