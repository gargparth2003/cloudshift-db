from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from secrets import compare_digest
from time import perf_counter
from typing import Annotated
from uuid import uuid4

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from .config import get_settings
from .database import connect, endpoints

settings = get_settings()
COMMERCE_REQUESTS = Counter(
    "cloudshift_workload_commerce_requests_total", "Commerce HTTP requests", ["method", "route", "status"]
)
COMMERCE_DURATION = Histogram(
    "cloudshift_workload_commerce_request_duration_seconds", "Commerce HTTP request duration", ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)
app = FastAPI(
    title="Parth Commerce Application",
    version="0.1.0",
    description="Synthetic commerce workload used to verify CloudShift DB cutover.",
    docs_url="/api/docs",
    redoc_url=None,
)


@app.middleware("http")
async def request_metrics(request: Request, call_next):
    started = perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    route_path = getattr(route, "path", "unmatched")
    COMMERCE_REQUESTS.labels(request.method, route_path, str(response.status_code)).inc()
    COMMERCE_DURATION.labels(request.method, route_path).observe(perf_counter() - started)
    return response


@app.get("/metrics", include_in_schema=False, response_class=PlainTextResponse)
def metrics():
    return PlainTextResponse(generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST)


class OrderRequest(BaseModel):
    customer_id: int = Field(gt=0)
    product_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=5)


class SyntheticOperationRequest(BaseModel):
    product_id: int = Field(default=1, ge=1, le=1000)


def require_operator(
    x_cloudshift_token: Annotated[str | None, Header()] = None,
) -> None:
    if x_cloudshift_token is None or not compare_digest(
        x_cloudshift_token, settings.control_api_token
    ):
        raise HTTPException(status_code=401, detail="Valid operator token required")


def current_route() -> dict:
    with connect(endpoints(settings)["control"]) as connection:
        route = connection.execute(
            """
            SELECT active_endpoint::text, writes_enabled, version, updated_at
            FROM control.application_routes WHERE route_key = 'parth-commerce-application'
            """
        ).fetchone()
    if route is None:
        raise RuntimeError("commerce application route is not configured")
    return route


def active_app_dsn(route: str) -> str:
    return settings.app_source_database_url if route == "SOURCE" else settings.app_target_database_url


@app.get("/api/v1/commerce/health")
def health():
    route = current_route()
    try:
        with psycopg.connect(active_app_dsn(route["active_endpoint"]), connect_timeout=3) as connection:
            connection.execute("SELECT 1")
        state = "AVAILABLE"
    except psycopg.Error:
        state = "UNREACHABLE"
    return {
        "application": "parth-commerce-application",
        "state": state,
        "active_database": route["active_endpoint"],
        "writes_enabled": route["writes_enabled"],
        "route_version": route["version"],
        "observed_at": datetime.now(UTC),
    }


@app.get("/api/v1/commerce/products")
def products(limit: int = Query(default=20, ge=1, le=100)):
    route = current_route()
    with psycopg.connect(active_app_dsn(route["active_endpoint"]), row_factory=dict_row) as connection:
        rows = connection.execute(
            """
            SELECT product_id, sku, name, price, active
            FROM commerce.products WHERE active ORDER BY product_id LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return {"active_database": route["active_endpoint"], "items": rows}


@app.get("/api/v1/commerce/orders")
def orders(limit: int = Query(default=20, ge=1, le=100)):
    route = current_route()
    with psycopg.connect(active_app_dsn(route["active_endpoint"]), row_factory=dict_row) as connection:
        rows = connection.execute(
            """
            SELECT order_id, order_ref, customer_id, status, total, currency, created_at
            FROM commerce.orders ORDER BY order_id DESC LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return {"active_database": route["active_endpoint"], "items": rows}


@app.get("/api/v1/commerce/customers")
def customers(limit: int = Query(default=20, ge=1, le=100)):
    route = current_route()
    with psycopg.connect(active_app_dsn(route["active_endpoint"]), row_factory=dict_row) as connection:
        rows = connection.execute(
            """
            SELECT customer_id, external_ref, full_name, region_code, created_at
            FROM commerce.customers ORDER BY customer_id DESC LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return {"active_database": route["active_endpoint"], "items": rows}


@app.get("/api/v1/commerce/inventory")
def inventory(limit: int = Query(default=20, ge=1, le=100)):
    route = current_route()
    with psycopg.connect(active_app_dsn(route["active_endpoint"]), row_factory=dict_row) as connection:
        rows = connection.execute(
            """
            SELECT inventory.warehouse_id, inventory.product_id, products.sku,
                   inventory.quantity_on_hand, inventory.quantity_reserved,
                   inventory.quantity_on_hand - inventory.quantity_reserved AS available
            FROM commerce.inventory JOIN commerce.products USING (product_id)
            ORDER BY inventory.product_id LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return {"active_database": route["active_endpoint"], "items": rows}


@app.get("/api/v1/commerce/payments")
def payments(limit: int = Query(default=20, ge=1, le=100)):
    route = current_route()
    with psycopg.connect(active_app_dsn(route["active_endpoint"]), row_factory=dict_row) as connection:
        rows = connection.execute(
            """
            SELECT payment_id, payment_ref, order_id, status, amount, updated_at
            FROM commerce.payments ORDER BY payment_id DESC LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return {"active_database": route["active_endpoint"], "items": rows}


@app.get("/api/v1/commerce/shipments")
def shipments(limit: int = Query(default=20, ge=1, le=100)):
    route = current_route()
    with psycopg.connect(active_app_dsn(route["active_endpoint"]), row_factory=dict_row) as connection:
        rows = connection.execute(
            """
            SELECT shipment_id, shipment_ref, order_id, status, carrier, updated_at
            FROM commerce.shipments ORDER BY shipment_id DESC LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return {"active_database": route["active_endpoint"], "items": rows}


@app.get("/api/v1/commerce/activity")
def activity(limit: int = Query(default=50, ge=1, le=200)):
    route = current_route()
    with psycopg.connect(active_app_dsn(route["active_endpoint"]), row_factory=dict_row) as connection:
        rows = connection.execute(
            """
            SELECT event_id, transaction_ref, event_type, entity_type, entity_id,
                   payload, committed_at
            FROM commerce.transaction_events ORDER BY event_id DESC LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return {"active_database": route["active_endpoint"], "items": rows}


def begin_routed_write():
    initial_route = current_route()
    if not initial_route["writes_enabled"]:
        raise HTTPException(status_code=503, detail="Commerce writes are temporarily fenced")
    connection = psycopg.connect(
        active_app_dsn(initial_route["active_endpoint"]), row_factory=dict_row
    )
    try:
        connection.execute("SELECT pg_advisory_xact_lock(20261127)")
        confirmed_route = current_route()
        if (
            not confirmed_route["writes_enabled"]
            or confirmed_route["active_endpoint"] != initial_route["active_endpoint"]
            or confirmed_route["version"] != initial_route["version"]
        ):
            connection.rollback()
            connection.close()
            raise HTTPException(status_code=503, detail="Database route changed; retry the transaction")
        return connection, initial_route
    except Exception:
        if not connection.closed:
            connection.rollback()
            connection.close()
        raise


@app.get("/api/v1/commerce/probe")
def read_probe():
    route = current_route()
    with psycopg.connect(active_app_dsn(route["active_endpoint"]), row_factory=dict_row) as connection:
        database = connection.execute("SELECT current_database() AS database").fetchone()
    return {
        "success": True, "active_database": route["active_endpoint"],
        "database": database["database"], "observed_at": datetime.now(UTC),
    }


@app.post("/api/v1/commerce/probe", dependencies=[Depends(require_operator)])
def write_probe():
    transaction_ref = f"probe-{uuid4()}"
    connection, route = begin_routed_write()
    try:
        event = connection.execute(
            """
            INSERT INTO commerce.transaction_events
                (transaction_ref, event_type, entity_type, entity_id, payload)
            VALUES (%s, 'PROBE_WRITE', 'AVAILABILITY_PROBE', 0,
                    jsonb_build_object('route', %s::text))
            RETURNING event_id, committed_at
            """,
            (transaction_ref, route["active_endpoint"]),
        ).fetchone()
        connection.commit()
        return {
            "success": True, "committed": True, "transaction_ref": transaction_ref,
            "event_id": event["event_id"], "active_database": route["active_endpoint"],
            "committed_at": event["committed_at"],
        }
    finally:
        connection.close()


@app.post(
    "/api/v1/commerce/synthetic/{operation}",
    dependencies=[Depends(require_operator)],
)
def synthetic_operation(operation: str, request: SyntheticOperationRequest):
    allowed = {"customer", "product_update", "payment_update", "shipment_update", "delete_customer"}
    if operation not in allowed:
        raise HTTPException(status_code=404, detail="Unsupported synthetic operation")
    transaction_ref = f"workload-{operation}-{uuid4()}"
    connection, route = begin_routed_write()
    try:
        if operation == "customer":
            token = uuid4().hex[:16]
            row = connection.execute(
                """
                INSERT INTO commerce.customers (external_ref, email, full_name, region_code)
                VALUES (%s, %s, 'Synthetic Workload Customer', 'NR')
                RETURNING customer_id
                """,
                (f"CUS-WORKLOAD-{token}", f"workload-{token}@example.invalid"),
            ).fetchone()
            event_type, entity_type, entity_id = "CUSTOMER_CREATED", "CUSTOMER", row["customer_id"]
        elif operation == "product_update":
            row = connection.execute(
                """
                UPDATE commerce.products SET price = price + 0.01, updated_at = now()
                WHERE product_id = %s RETURNING product_id
                """,
                (request.product_id,),
            ).fetchone()
            event_type, entity_type, entity_id = "PRODUCT_UPDATED", "PRODUCT", row["product_id"]
        elif operation == "payment_update":
            row = connection.execute(
                """
                UPDATE commerce.payments
                SET status = CASE WHEN status = 'CAPTURED' THEN 'AUTHORIZED' ELSE 'CAPTURED' END,
                    updated_at = now()
                WHERE payment_id = (SELECT max(payment_id) FROM commerce.payments)
                RETURNING payment_id
                """
            ).fetchone()
            event_type, entity_type, entity_id = "PAYMENT_UPDATED", "PAYMENT", row["payment_id"]
        elif operation == "shipment_update":
            row = connection.execute(
                """
                UPDATE commerce.shipments
                SET status = CASE WHEN status = 'IN_TRANSIT' THEN 'PACKED' ELSE 'IN_TRANSIT' END,
                    updated_at = now()
                WHERE shipment_id = (SELECT max(shipment_id) FROM commerce.shipments)
                RETURNING shipment_id
                """
            ).fetchone()
            event_type, entity_type, entity_id = "SHIPMENT_UPDATED", "SHIPMENT", row["shipment_id"]
        else:
            row = connection.execute(
                """
                DELETE FROM commerce.customers
                WHERE customer_id = (
                    SELECT customer.customer_id FROM commerce.customers customer
                    WHERE customer.external_ref LIKE 'CUS-WORKLOAD-%'
                      AND NOT EXISTS (SELECT 1 FROM commerce.orders orders WHERE orders.customer_id = customer.customer_id)
                    ORDER BY customer.customer_id LIMIT 1
                )
                RETURNING customer_id
                """
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=409, detail="No disposable workload customer is available")
            event_type, entity_type, entity_id = "CONTROLLED_DELETE", "CUSTOMER", row["customer_id"]

        connection.execute(
            """
            INSERT INTO commerce.transaction_events
                (transaction_ref, event_type, entity_type, entity_id, payload)
            VALUES (%s, %s, %s, %s, jsonb_build_object('route', %s::text))
            """,
            (transaction_ref, event_type, entity_type, entity_id, route["active_endpoint"]),
        )
        connection.commit()
        return {
            "success": True, "committed": True, "transaction_ref": transaction_ref,
            "operation": operation, "entity_id": entity_id,
            "active_database": route["active_endpoint"],
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


@app.post("/api/v1/commerce/orders", status_code=201)
def create_order(request: OrderRequest):
    initial_route = current_route()
    if not initial_route["writes_enabled"]:
        raise HTTPException(status_code=503, detail="Commerce writes are temporarily fenced")
    route_name = initial_route["active_endpoint"]
    order_ref = f"ORD-LIVE-{uuid4().hex[:16].upper()}"
    payment_ref = f"PAY-LIVE-{uuid4().hex[:16].upper()}"
    transaction_ref = f"commerce-{uuid4()}"

    try:
        with psycopg.connect(active_app_dsn(route_name), row_factory=dict_row) as connection:
            connection.execute("SELECT pg_advisory_xact_lock(20261127)")
            confirmed_route = current_route()
            if (
                not confirmed_route["writes_enabled"]
                or confirmed_route["active_endpoint"] != route_name
                or confirmed_route["version"] != initial_route["version"]
            ):
                raise HTTPException(status_code=503, detail="Database route changed; retry the transaction")

            inventory = connection.execute(
                """
                SELECT inventory.warehouse_id, inventory.quantity_on_hand,
                       inventory.quantity_reserved, products.price
                FROM commerce.inventory
                JOIN commerce.products USING (product_id)
                WHERE inventory.product_id = %s
                  AND inventory.quantity_on_hand - inventory.quantity_reserved >= %s
                  AND products.active
                ORDER BY inventory.warehouse_id
                LIMIT 1 FOR UPDATE OF inventory
                """,
                (request.product_id, request.quantity),
            ).fetchone()
            if inventory is None:
                raise HTTPException(status_code=409, detail="Insufficient inventory or inactive product")
            customer = connection.execute(
                "SELECT customer_id FROM commerce.customers WHERE customer_id = %s",
                (request.customer_id,),
            ).fetchone()
            if customer is None:
                raise HTTPException(status_code=404, detail="Customer not found")

            subtotal = (inventory["price"] * request.quantity).quantize(Decimal("0.01"))
            tax = (subtotal * Decimal("0.18")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            order = connection.execute(
                """
                INSERT INTO commerce.orders
                    (order_ref, customer_id, status, subtotal, tax)
                VALUES (%s, %s, 'PAID', %s, %s)
                RETURNING order_id, order_ref, total, currency, created_at
                """,
                (order_ref, request.customer_id, subtotal, tax),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO commerce.order_items (order_id, product_id, quantity, unit_price)
                VALUES (%s, %s, %s, %s)
                """,
                (order["order_id"], request.product_id, request.quantity, inventory["price"]),
            )
            connection.execute(
                """
                UPDATE commerce.inventory SET quantity_reserved = quantity_reserved + %s, updated_at = now()
                WHERE warehouse_id = %s AND product_id = %s
                """,
                (request.quantity, inventory["warehouse_id"], request.product_id),
            )
            connection.execute(
                """
                INSERT INTO commerce.payments (payment_ref, order_id, status, amount, provider)
                VALUES (%s, %s, 'CAPTURED', %s, 'SYNTHETIC_GATEWAY')
                """,
                (payment_ref, order["order_id"], order["total"]),
            )
            connection.execute(
                """
                INSERT INTO commerce.inventory_movements
                    (warehouse_id, product_id, order_id, movement_type, quantity_delta)
                VALUES (%s, %s, %s, 'RESERVATION', %s)
                """,
                (inventory["warehouse_id"], request.product_id, order["order_id"], -request.quantity),
            )
            connection.execute(
                """
                INSERT INTO commerce.transaction_events
                    (transaction_ref, event_type, entity_type, entity_id, payload)
                VALUES (%s, 'ORDER_CREATED', 'ORDER', %s,
                        jsonb_build_object('order_ref', %s::text, 'route', %s::text))
                """,
                (transaction_ref, order["order_id"], order_ref, route_name),
            )
        return {
            **order, "transaction_ref": transaction_ref,
            "active_database": route_name, "committed": True,
        }
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail=f"Database transaction failed: {exc.__class__.__name__}") from exc
