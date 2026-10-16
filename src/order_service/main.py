import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, status

from order_service.models import (
    ErrorResponse,
    OrderResponse,
    OrderStatus,
    OrderUpdate,
)
from order_service.store import order_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Order Management Service starting up")
    yield
    logger.info("Order Management Service shutting down")


app = FastAPI(
    title="Order Management Service",
    description="Simulated external order management system for Relay demonstration",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "healthy", "service": "order-management"}


@app.get("/orders/{order_id}", response_model=OrderResponse, tags=["orders"])
async def get_order(order_id: str):
    order = order_store.get_order(order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorResponse(
                detail=f"Order {order_id} not found",
                error_code="ORDER_NOT_FOUND",
            ).model_dump(),
        )
    return OrderResponse.from_order(order)


@app.patch("/orders/{order_id}", response_model=OrderResponse, tags=["orders"])
async def update_order(
    order_id: str,
    update: OrderUpdate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    # Use idempotency key from header if not in body
    if idempotency_key and not update.idempotency_key:
        update.idempotency_key = idempotency_key

    order = order_store.get_order(order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorResponse(
                detail=f"Order {order_id} not found",
                error_code="ORDER_NOT_FOUND",
            ).model_dump(),
        )

    # Check if this request can be fulfilled via idempotency replay
    # before rejecting state transition
    if update.idempotency_key and order_store.has_idempotency_key(order_id, update.idempotency_key):
        replayed_order = order_store.update_order(order_id, update)
        if replayed_order:
            return OrderResponse.from_order(replayed_order)

    if order.status in (OrderStatus.SHIPPED, OrderStatus.CANCELLED, OrderStatus.DELIVERED):
        if update.delivery_date is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ErrorResponse(
                    detail=(
                        f"Cannot change delivery date for order in status '{order.status.value}'"
                    ),
                    error_code="INVALID_STATE_TRANSITION",
                ).model_dump(),
            )

    updated_order = order_store.update_order(order_id, update)
    if updated_order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorResponse(
                detail=f"Order {order_id} not found",
                error_code="ORDER_NOT_FOUND",
            ).model_dump(),
        )

    return OrderResponse.from_order(updated_order)


@app.get("/orders", response_model=list[OrderResponse], tags=["orders"])
async def list_orders(customer_id: str | None = None):
    orders = order_store.list_orders(customer_id)
    return [OrderResponse.from_order(o) for o in orders]


@app.get("/orders/{order_id}/idempotency/{idempotency_key}", tags=["orders"])
async def check_idempotency_key(order_id: str, idempotency_key: str):
    """Check if an idempotency key exists for an order."""
    if order_store.get_order(order_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ErrorResponse(
                detail=f"Order {order_id} not found",
                error_code="ORDER_NOT_FOUND",
            ).model_dump(),
        )

    exists = order_store.has_idempotency_key(order_id, idempotency_key)
    return {"exists": exists}
