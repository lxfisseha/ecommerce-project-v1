from fastapi import APIRouter, Request, Depends, HTTPException, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_session
from src.templates_config import templates
from src.features.buyer.services import BuyerProductService
from src.features.orders.services import (
    OrderService,
    parse_selected_attributes,
    calculate_attribute_extra_price,
)
from typing import Optional, List
import re

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home_page(request: Request, db: AsyncSession = Depends(get_session)):
    from src.features.auth.models import Seller
    from sqlmodel import select
    # Fetch only latest 8 products for home page
    products, _ = await BuyerProductService.get_all_active_products(db, limit=8)
    seller = (await db.execute(select(Seller))).scalars().first()
    return templates.TemplateResponse(
        request, "buyer_home.html", {"request": request, "products": products, "seller": seller}
    )


@router.get("/shop", response_class=HTMLResponse)
async def shop_page(
    request: Request,
    q: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_session),
):
    per_page = 12
    offset = (page - 1) * per_page

    products, total_count = await BuyerProductService.get_all_active_products(
        db, search=q, sort_by=sort_by, tag_slug=tag, limit=per_page, offset=offset
    )

    active_tags = await BuyerProductService.get_all_active_tags(db)

    import math

    total_pages = math.ceil(total_count / per_page) if total_count > 0 else 1

    context = {
        "request": request,
        "products": products,
        "tags": active_tags,
        "current_tag": tag,
        "search_query": q,
        "current_sort": sort_by,
        "current_page": page,
        "total_pages": total_pages,
        "total_count": total_count,
    }

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "buyer/_shop_content.html", context)

    return templates.TemplateResponse(request, "buyer_shop.html", context)


@router.get("/support", response_class=HTMLResponse)
async def support_page(request: Request):
    return templates.TemplateResponse(request, "support.html", {"request": request})


@router.get("/product/{product_id}", response_class=HTMLResponse)
async def product_detail(
    request: Request, product_id: int, db: AsyncSession = Depends(get_session)
):
    product = await BuyerProductService.get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return templates.TemplateResponse(
        request, "buyer_product_detail.html", {"request": request, "product": product}
    )


@router.get("/checkout/{product_id}", response_class=HTMLResponse)
async def checkout_page(
    request: Request,
    product_id: int,
    qty: int = 1,
    attrs: str | None = Query(None),
    db: AsyncSession = Depends(get_session),
):
    product = await BuyerProductService.get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Simple summary calculations with attribute extra pricing
    delivery_fee = 150
    selected_attrs = parse_selected_attributes(attrs)
    extra_price = calculate_attribute_extra_price(product, selected_attrs)
    subtotal = (product.price + extra_price) * qty
    attribute_total = extra_price * qty
    total = subtotal + delivery_fee

    return templates.TemplateResponse(
        request,
        "buyer_checkout.html",
        {
            "request": request,
            "product": product,
            "quantity": qty,
            "attributes": attrs,
            "extra_price": extra_price,
            "attribute_total": attribute_total,
            "subtotal": subtotal,
            "delivery_fee": delivery_fee,
            "total": total,
        },
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
    db: AsyncSession = Depends(get_session),
):
    product = await BuyerProductService.get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Validation: Phone Number
    from src.utils.phone import validate_ethiopian_phone, normalize_phone

    if not validate_ethiopian_phone(buyer_phone):
        selected_attrs = parse_selected_attributes(attributes)
        extra_price = calculate_attribute_extra_price(product, selected_attrs)
        subtotal = (product.price + extra_price) * quantity
        attribute_total = extra_price * quantity
        return templates.TemplateResponse(
            request,
            "buyer_checkout.html",
            {
                "request": request,
                "product": product,
                "quantity": quantity,
                "attributes": attributes,
                "error": "Phone number must be a valid Ethiopian number (e.g., 0912345678 or 912345678)",
                "extra_price": extra_price,
                "attribute_total": attribute_total,
                "subtotal": subtotal,
                "delivery_fee": 150,
                "total": subtotal + 150,
            },
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
        attributes_selected=attributes,
    )

    return RedirectResponse(
        url=f"/order-confirmation/{order.order_id}", status_code=303
    )


@router.get("/order-confirmation/{order_reference}", response_class=HTMLResponse)
async def order_confirmation(
    request: Request, order_reference: str, db: AsyncSession = Depends(get_session)
):
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
        {"request": request, "order": order, "seller": seller},
    )
