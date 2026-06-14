from fastapi import APIRouter, Request, Depends, HTTPException, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_session
from src.templates_config import templates
from src.features.buyer.services import BuyerProductService
from src.features.orders.services import OrderService
from typing import Optional, List
import re

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def homepage(request: Request, db: AsyncSession = Depends(get_session)):
    products = await BuyerProductService.get_all_active_products(db)
    return templates.TemplateResponse(request, "buyer_product_list.html", {"request": request, "products": products})

@router.get("/product/{product_id}", response_class=HTMLResponse)
async def product_detail(request: Request, product_id: int, db: AsyncSession = Depends(get_session)):
    product = await BuyerProductService.get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return templates.TemplateResponse(request, "buyer_product_detail.html", {"request": request, "product": product})

@router.get("/checkout/{product_id}", response_class=HTMLResponse)
async def checkout_page(
    request: Request, 
    product_id: int, 
    qty: int = 1,
    attrs: str | None = Query(None),
    db: AsyncSession = Depends(get_session)
):
    product = await BuyerProductService.get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Simple summary calculations
    delivery_fee = 150
    subtotal = product.price * qty
    total = subtotal + delivery_fee
    
    return templates.TemplateResponse(
        request, 
        "buyer_checkout.html", 
        {
            "request": request, 
            "product": product,
            "quantity": qty,
            "attributes": attrs,
            "subtotal": subtotal,
            "delivery_fee": delivery_fee,
            "total": total
        }
    )

@router.post("/checkout/{product_id}")
async def process_checkout(
    request: Request,
    product_id: int,
    buyer_name: str = Form(...),
    buyer_phone: str = Form(...),
    delivery_address: str = Form(...),
    quantity: int = Form(1),
    attributes: str | None = Form(None),
    db: AsyncSession = Depends(get_session)
):
    product = await BuyerProductService.get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Validation: Phone Number
    from src.utils.phone import validate_ethiopian_phone, normalize_phone
    if not validate_ethiopian_phone(buyer_phone):
        return templates.TemplateResponse(
            request, 
            "buyer_checkout.html", 
            {
                "request": request, 
                "product": product,
                "quantity": quantity,
                "attributes": attributes,
                "error": "Phone number must be a valid Ethiopian number (e.g., 0912345678 or 912345678)",
                "subtotal": product.price * quantity,
                "delivery_fee": 150,
                "total": (product.price * quantity) + 150
            }
        )
    
    # Normalize phone to 9-digit format before saving
    normalized_phone = normalize_phone(buyer_phone)
    
    order = await OrderService.create_order(
        db,
        product=product,
        buyer_name=buyer_name,
        buyer_phone=normalized_phone,
        delivery_address=delivery_address,
        quantity=quantity,
        attributes_selected=attributes
    )
    
    return RedirectResponse(url=f"/order-confirmation/{order.order_id}", status_code=303)

@router.get("/order-confirmation/{order_reference}", response_class=HTMLResponse)
async def order_confirmation(request: Request, order_reference: str, db: AsyncSession = Depends(get_session)):
    order = await OrderService.get_order_by_reference(db, order_reference)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Decrypt sensitive data for display
    from src.utils.crypto import decrypt_data
    order.buyer_phone = decrypt_data(order.buyer_phone)
    order.delivery_address = decrypt_data(order.delivery_address)
    
    # Fetch seller info
    from src.features.auth.models import Seller
    seller = await db.get(Seller, order.seller_id)
    if seller:
        seller.phone = decrypt_data(seller.phone)
    
    return templates.TemplateResponse(
        request, 
        "buyer_confirmation.html", 
        {"request": request, "order": order, "seller": seller}
    )
