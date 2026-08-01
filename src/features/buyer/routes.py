from fastapi import APIRouter, Request, Depends, HTTPException, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_session
from src.templates_config import templates
from src.features.buyer.services import BuyerProductService, CartService
from src.features.orders.services import (
    OrderService,
    parse_selected_attributes,
    calculate_attribute_extra_price,
)
from typing import Optional, List
import re
import math
from decimal import Decimal
from sqlmodel import select
from src.features.auth.models import Seller
from src.utils.phone import validate_ethiopian_phone, normalize_phone
from src.utils.crypto import decrypt_data
from src.constants import DELIVERY_FEE

router = APIRouter()


def _calculate_checkout_totals(product, quantity, selected_attrs):
    extra_price = calculate_attribute_extra_price(product, selected_attrs)
    subtotal = (product.price + extra_price) * quantity
    attribute_total = extra_price * quantity
    total = subtotal + DELIVERY_FEE
    return extra_price, attribute_total, subtotal, total


def _calculate_line_total(product, quantity, selected_attrs):
    extra_price = calculate_attribute_extra_price(product, selected_attrs)
    line_subtotal = (product.price + extra_price) * quantity
    return extra_price, line_subtotal


async def _load_cart_items(request: Request, db: AsyncSession) -> List[dict]:
    """
    Re-fetches cart line items from the DB in a single batched query. Stale or
    unavailable products are pruned from the session so prices are always
    current and never trusted.
    """
    cart = CartService.get_cart(request)
    if not cart:
        return []

    ids = [entry.get("product_id") for entry in cart if isinstance(entry.get("product_id"), int)]
    products = await BuyerProductService.get_products_by_ids(db, ids)
    by_id = {product.id: product for product in products}

    lines = []
    valid = []
    for entry in cart:
        product = by_id.get(entry.get("product_id"))
        if not product:
            continue
        qty = max(1, int(entry.get("qty", 1)))
        attrs = entry.get("attrs")
        extra_price, line_subtotal = _calculate_line_total(product, qty, parse_selected_attributes(attrs))
        lines.append(
            {
                "index": len(valid),
                "product": product,
                "qty": qty,
                "attrs": attrs,
                "extra_price": extra_price,
                "line_subtotal": line_subtotal,
            }
        )
        valid.append(entry)

    if len(valid) != len(cart):
        request.session["cart"] = {"items": valid}
    return lines


def _cart_totals(lines: List[dict]):
    subtotal = sum(line["line_subtotal"] for line in lines)
    delivery_fee = DELIVERY_FEE if lines else Decimal("0.0")
    return subtotal, delivery_fee, subtotal + delivery_fee


async def _render_cart_content(request: Request, db: AsyncSession):
    lines = await _load_cart_items(request, db)
    subtotal, delivery_fee, total = _cart_totals(lines)
    return templates.TemplateResponse(
        request,
        "buyer/_cart_content.html",
        {
            "request": request,
            "items": lines,
            "subtotal": subtotal,
            "delivery_fee": delivery_fee,
            "total": total,
        },
    )


@router.get("/", response_class=HTMLResponse)
async def home_page(request: Request, db: AsyncSession = Depends(get_session)):
    # Fetch only latest 8 products for home page; skip the total-count query.
    products, _ = await BuyerProductService.get_all_active_products(
        db, limit=8, include_count=False
    )
    seller = (
        await db.execute(select(Seller).order_by(Seller.updated_at.desc()).limit(1))
    ).scalars().first()
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


@router.post("/cart/add/{product_id}")
async def add_to_cart(
    request: Request,
    product_id: int,
    qty: int = Form(1),
    attributes: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_session),
):
    product = await BuyerProductService.get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    CartService.add(request, product_id, qty, attributes)
    return templates.TemplateResponse(
        request,
        "buyer/_cart_badge.html",
        {"request": request, "cart_count": CartService.count(request)},
    )


@router.get("/cart", response_class=HTMLResponse)
async def cart_page(request: Request, db: AsyncSession = Depends(get_session)):
    lines = await _load_cart_items(request, db)
    subtotal, delivery_fee, total = _cart_totals(lines)
    return templates.TemplateResponse(
        request,
        "buyer_cart.html",
        {
            "request": request,
            "items": lines,
            "subtotal": subtotal,
            "delivery_fee": delivery_fee,
            "total": total,
        },
    )


@router.post("/cart/update/{index}")
async def update_cart_item(
    request: Request,
    index: int,
    qty: int = Form(1),
    db: AsyncSession = Depends(get_session),
):
    CartService.update_qty(request, index, qty)
    return await _render_cart_content(request, db)


@router.post("/cart/remove/{index}")
async def remove_cart_item(
    request: Request,
    index: int,
    db: AsyncSession = Depends(get_session),
):
    CartService.remove(request, index)
    return await _render_cart_content(request, db)


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


@router.get("/checkout", response_class=HTMLResponse)
async def cart_checkout_page(request: Request, db: AsyncSession = Depends(get_session)):
    lines = await _load_cart_items(request, db)
    if not lines:
        return RedirectResponse(url="/cart", status_code=303)

    subtotal, delivery_fee, total = _cart_totals(lines)
    return templates.TemplateResponse(
        request,
        "buyer_checkout.html",
        {
            "request": request,
            "items": lines,
            "cart_mode": True,
            "subtotal": subtotal,
            "delivery_fee": delivery_fee,
            "total": total,
        },
    )


@router.post("/checkout")
async def process_cart_checkout(
    request: Request,
    buyer_name: str = Form(...),
    buyer_phone: str = Form(...),
    delivery_address: str = Form(...),
    db: AsyncSession = Depends(get_session),
):
    lines = await _load_cart_items(request, db)
    if not lines:
        return RedirectResponse(url="/cart", status_code=303)

    subtotal, delivery_fee, total = _cart_totals(lines)

    # Validation: Phone Number
    if not validate_ethiopian_phone(buyer_phone):
        return templates.TemplateResponse(
            request,
            "buyer_checkout.html",
            {
                "request": request,
                "items": lines,
                "cart_mode": True,
                "subtotal": subtotal,
                "delivery_fee": delivery_fee,
                "total": total,
                "error": "Phone number must be a valid Ethiopian number (e.g., 0912345678 or 912345678)",
            },
        )

    # Normalize phone to 9-digit format before saving
    normalized_phone = normalize_phone(buyer_phone)

    # Truncate long inputs
    buyer_name = buyer_name[:100]
    delivery_address = delivery_address[:1000]

    cart_lines = [(line["product"], line["qty"], line["attrs"]) for line in lines]
    order = await OrderService.create_order_from_cart(
        db,
        items=cart_lines,
        buyer_name=buyer_name,
        buyer_phone=normalized_phone,
        delivery_address=delivery_address,
        store_prefix=lines[0]["product"].seller.store_prefix,
    )

    # Clear the cart after successful order placement
    CartService.clear(request)

    # Store order ID in session for IDOR protection on confirmation page
    recent_orders = request.session.get("recent_orders", [])
    recent_orders.append(order.order_id)
    request.session["recent_orders"] = recent_orders[-10:]  # keep last 10

    return RedirectResponse(
        url=f"/order-confirmation/{order.order_id}", status_code=303
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
    selected_attrs = parse_selected_attributes(attrs)
    extra_price, attribute_total, subtotal, total = _calculate_checkout_totals(product, qty, selected_attrs)

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
            "delivery_fee": DELIVERY_FEE,
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
    if not validate_ethiopian_phone(buyer_phone):
        selected_attrs = parse_selected_attributes(attributes)
        extra_price, attribute_total, subtotal, total = _calculate_checkout_totals(product, quantity, selected_attrs)
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
                "delivery_fee": DELIVERY_FEE,
                "total": total,
            },
        )

    # Normalize phone to 9-digit format before saving
    normalized_phone = normalize_phone(buyer_phone)

    # Truncate long inputs
    buyer_name = buyer_name[:100]
    delivery_address = delivery_address[:1000]
    if quantity < 1:
        quantity = 1
    if quantity > 100:
        quantity = 100

    order = await OrderService.create_order(
        db,
        product=product,
        buyer_name=buyer_name,
        buyer_phone=normalized_phone,
        delivery_address=delivery_address,
        quantity=quantity,
        attributes_selected=attributes,
        store_prefix=product.seller.store_prefix,
    )

    # Store order ID in session for IDOR protection on confirmation page
    recent_orders = request.session.get("recent_orders", [])
    recent_orders.append(order.order_id)
    request.session["recent_orders"] = recent_orders[-10:]  # keep last 10

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

    # IDOR protection: only allow access if this order was placed in current session
    recent_orders = request.session.get("recent_orders", [])
    if order.order_id not in recent_orders:
        raise HTTPException(status_code=403, detail="Access denied")

    # Decrypt sensitive data for display (separate variables — DON'T mutate ORM)
    try:
        buyer_phone = decrypt_data(order.buyer_phone)
        delivery_address = decrypt_data(order.delivery_address)
    except ValueError:
        buyer_phone = "Unable to decrypt"
        delivery_address = "Unable to decrypt"

    # Fetch seller info
    seller = await db.get(Seller, order.seller_id)
    try:
        seller_phone = decrypt_data(seller.phone) if seller else None
    except ValueError:
        seller_phone = None

    return templates.TemplateResponse(
        request,
        "buyer_confirmation.html",
        {
            "request": request,
            "order": order,
            "buyer_phone": buyer_phone,
            "delivery_address": delivery_address,
            "seller": seller,
            "seller_phone": seller_phone,
        },
    )
