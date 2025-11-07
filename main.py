import os
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from .database import Base, engine, get_db
from .models import MenuItem, Order, OrderItem
from .schemas import (
    MenuItemCreate, MenuItemUpdate, MenuItemOut,
    OrderCreate, OrderOut, OrderItemOut,
    StatusUpdate, StatusByToken
)
from .utils import generate_token, require_admin_api_key

app = FastAPI(title="Smart Canteen Backend", version="1.0.0")

# CORS: allow everything for demo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create tables on startup
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

@app.get("/health")
def health():
    return {"status": "ok"}

# ---------- MENU ----------
@app.get("/menu", response_model=List[MenuItemOut])
def list_menu(available_only: bool = Query(default=False), db: Session = Depends(get_db)):
    stmt = select(MenuItem)
    if available_only:
        stmt = stmt.where(MenuItem.is_available == True)  # noqa: E712
    return db.execute(stmt.order_by(MenuItem.id)).scalars().all()

@app.post("/menu", response_model=MenuItemOut, dependencies=[Depends(require_admin_api_key)])
def create_menu_item(payload: MenuItemCreate, db: Session = Depends(get_db)):
    item = MenuItem(**payload.dict())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item

@app.put("/menu/{item_id}", response_model=MenuItemOut, dependencies=[Depends(require_admin_api_key)])
def update_menu_item(item_id: int, payload: MenuItemUpdate, db: Session = Depends(get_db)):
    item = db.get(MenuItem, item_id)
    if not item:
        raise HTTPException(404, "Menu item not found")
    for k, v in payload.dict(exclude_unset=True).items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    return item

@app.delete("/menu/{item_id}", dependencies=[Depends(require_admin_api_key)])
def delete_menu_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(MenuItem, item_id)
    if not item:
        raise HTTPException(404, "Menu item not found")
    db.delete(item)
    db.commit()
    return {"deleted": True, "id": item_id}

# ---------- ORDERS ----------
@app.post("/orders", response_model=OrderOut)
def create_order(payload: OrderCreate, db: Session = Depends(get_db)):
    if not payload.items:
        raise HTTPException(400, "Order must contain at least one item")

    # validate items and compute total
    menu_map = {m.id: m for m in db.execute(select(MenuItem)).scalars().all()}
    total = 0.0
    order_items: list[OrderItem] = []
    for it in payload.items:
        if it.item_id not in menu_map:
            raise HTTPException(404, f"Menu item {it.item_id} not found")
        m = menu_map[it.item_id]
        if not m.is_available:
            raise HTTPException(400, f"Item '{m.name}' is not available")
        line_total = m.price * it.quantity
        total += line_total
        order_items.append(OrderItem(item_id=m.id, quantity=it.quantity, price_at_purchase=m.price))

    token = generate_token(6)
    order = Order(token=token, customer_name=payload.customer_name, phone=payload.phone, total_amount=round(total, 2))
    db.add(order)
    db.flush()  # get order.id
    for oi in order_items:
        oi.order_id = order.id
        db.add(oi)
    db.commit()
    db.refresh(order)
    return order

@app.get("/orders", response_model=List[OrderOut], dependencies=[Depends(require_admin_api_key)])
def list_orders(status: Optional[str] = None, db: Session = Depends(get_db)):
    stmt = select(Order)
    if status:
        stmt = stmt.where(Order.status == status)
    orders = db.execute(stmt.order_by(Order.created_at)).scalars().all()
    # items lazy-loaded, but FastAPI will access them on serialization
    return orders

@app.get("/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    return order

@app.patch("/orders/{order_id}/status", response_model=OrderOut, dependencies=[Depends(require_admin_api_key)])
def update_status(order_id: int, payload: StatusUpdate, db: Session = Depends(get_db)):
    allowed = {"placed", "preparing", "ready", "completed", "cancelled"}
    if payload.status not in allowed:
        raise HTTPException(400, f"Invalid status. Allowed: {sorted(allowed)}")
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    order.status = payload.status
    db.commit()
    db.refresh(order)
    return order

@app.get("/status/{token}", response_model=StatusByToken)
def status_by_token(token: str, db: Session = Depends(get_db)):
    stmt = select(Order).where(Order.token == token)
    order = db.execute(stmt).scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Invalid token")
    if order.status in {"ready", "completed", "cancelled"}:
        queue_pos = 0
    else:
        # count orders placed before this one that are still active
        active = {"placed", "preparing"}
        count_stmt = (
            select(func.count())
            .select_from(Order)
            .where(Order.created_at <= order.created_at)
            .where(Order.status.in_(active))
        )
        queue_pos = db.execute(count_stmt).scalar_one()
    return {"order_id": order.id, "token": order.token, "status": order.status, "queue_position": int(queue_pos)}
