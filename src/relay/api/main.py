import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.middleware.cors import CORSMiddleware

from relay.api.correlation import CorrelationIdMiddleware
from relay.core.config import settings
from relay.core.logging import setup_logging
from relay.core.ratelimit import RateLimitMiddleware
from relay.db.session import engine, get_db_session
from relay.models import (
    DashboardMetricsResponse,
    LLMInvocation,
    NLInterpretationRequest,
    NLInterpretationResponse,
    OrderChangeRequest,
    OrderChangeResponse,
    WorkflowDetailResponse,
    WorkflowErrorCode,
    WorkflowExecution,
    WorkflowListResponse,
    WorkflowStatus,
    WorkflowStep,
)
from relay.services import NLInterpreterService, WorkflowOrchestrator, WorkflowOrchestratorError


async def verify_demo_access(
    x_demo_key: Annotated[str | None, Header(alias="X-Demo-Key")] = None,
) -> None:
    """
    Verify demo access for expensive NL endpoint.

    If DEMO_API_KEY is configured, clients must provide it via X-Demo-Key header.
    If not configured, access is allowed (development mode).
    """
    if bool(settings.demo_api_key):
        if not x_demo_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error_code": "DEMO_KEY_REQUIRED",
                    "message": "Demo API key required. Provide X-Demo-Key header.",
                },
            )
        # Use constant-time comparison to prevent timing attacks
        import hmac

        if not hmac.compare_digest(x_demo_key, settings.demo_api_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error_code": "INVALID_DEMO_KEY",
                    "message": "Invalid demo API key.",
                },
            )


# Setup structured logging
setup_logging(
    level=settings.log_level,
    json_format=settings.environment == "production",
    include_timestamp=True,
)
logger = logging.getLogger(__name__)

# Package base directory for static assets and templates
BASE_DIR = Path(__file__).resolve().parent.parent

# Jinja2 templates
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up")
    yield
    logger.info("Application shutting down")


app = FastAPI(
    title="Relay",
    description="Business workflow integration system",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
)


# Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    # Content Security Policy
    csp = (
        "default-src 'self'; "
        "script-src 'self' https://fonts.googleapis.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self';"
    )
    response.headers["Content-Security-Policy"] = csp
    return response


# CORS - restrict to specific origins in production
if settings.environment == "production":
    allowed_origins = []  # Configure via environment in production
else:
    allowed_origins = ["http://localhost:8000", "http://127.0.0.1:8000"]

if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Correlation-ID", "X-Demo-Key"],
    )

# Add correlation ID middleware (must be first to capture all requests)
app.add_middleware(CorrelationIdMiddleware)

# Add rate limiting middleware
app.add_middleware(RateLimitMiddleware)

# Mount static files
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


DbSession = Annotated[Session, Depends(get_db_session)]


# --- Frontend Routes ---


@app.get("/", response_class=HTMLResponse, tags=["frontend"])
async def dashboard(request: Request):
    """Dashboard page."""
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"request": request},
    )


@app.get("/workflows", response_class=HTMLResponse, tags=["frontend"])
async def workflow_history(request: Request):
    """Workflow history page."""
    return templates.TemplateResponse(
        request,
        "workflow_history.html",
        {"request": request},
    )


@app.get("/workflows/{execution_id}", response_class=HTMLResponse, tags=["frontend"])
async def workflow_detail(execution_id: str, request: Request):
    """Workflow detail page."""
    try:
        uuid.UUID(execution_id)
    except ValueError:
        return templates.TemplateResponse(
            request,
            "404.html",
            {"request": request},
            status_code=404,
        )
    return templates.TemplateResponse(
        request,
        "workflow_detail.html",
        {"request": request, "execution_id": execution_id},
    )


@app.get("/workflows/new", response_class=HTMLResponse, tags=["frontend"])
@app.get("/request", response_class=HTMLResponse, tags=["frontend"])
async def nl_request_form(request: Request):
    """Natural language request form page."""
    return templates.TemplateResponse(
        request,
        "nl_request.html",
        {"request": request},
    )


# --- API Routes ---


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "healthy", "service": "relay"}


@app.get("/ready", tags=["health"])
async def readiness_check():
    try:
        with engine.connect() as conn:
            conn.execute(select(1))
        return {"status": "ready", "database": "connected"}
    except SQLAlchemyError as e:
        logger.error("Database connectivity check failed: %s", e)
        raise HTTPException(
            status_code=503,
            detail={"status": "not ready", "database": "disconnected", "error": str(e)},
        ) from e


@app.post(
    "/api/v1/order-change-requests",
    response_model=OrderChangeResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["order-changes"],
)
async def create_order_change_request(
    request: OrderChangeRequest, db: DbSession, request_obj: Request
):
    orchestrator = WorkflowOrchestrator(db)

    # Get correlation ID from request
    correlation_id = request_obj.headers.get("X-Correlation-ID")

    try:
        execution = orchestrator.execute_order_change(request, correlation_id)
    except WorkflowOrchestratorError as e:
        if e.error.error_code == WorkflowErrorCode.DUPLICATE_EVENT:
            if e.existing_event and e.existing_event.workflow_execution_id:
                stmt = select(WorkflowExecution).where(
                    WorkflowExecution.id == e.existing_event.workflow_execution_id
                )
                existing_execution = db.execute(stmt).scalar_one_or_none()
                if existing_execution:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "error_code": WorkflowErrorCode.DUPLICATE_EVENT,
                            "message": "Duplicate event detected",
                            "existing_execution_id": str(e.existing_event.workflow_execution_id),
                            "existing_event_id": str(e.existing_event.id),
                        },
                    ) from e
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error_code": WorkflowErrorCode.DUPLICATE_EVENT,
                    "message": "Duplicate event detected",
                },
            ) from e
        elif e.error.error_code == WorkflowErrorCode.ORDER_NOT_FOUND:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error_code": e.error.error_code, "message": e.error.message},
            ) from e
        elif e.error.error_code == WorkflowErrorCode.CUSTOMER_ORDER_MISMATCH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error_code": e.error.error_code,
                    "message": e.error.message,
                    "details": e.error.details,
                },
            ) from e
        elif e.error.error_code == WorkflowErrorCode.INVALID_STATE_TRANSITION:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error_code": e.error.error_code, "message": e.error.message},
            ) from e
        elif e.error.error_code == WorkflowErrorCode.EXTERNAL_SERVICE_TIMEOUT:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail={"error_code": e.error.error_code, "message": e.error.message},
            ) from e
        elif e.error.error_code == WorkflowErrorCode.EXTERNAL_SERVICE_UNAVAILABLE:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error_code": e.error.error_code, "message": e.error.message},
            ) from e
        elif e.error.error_code == WorkflowErrorCode.EXTERNAL_SERVICE_ERROR:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"error_code": e.error.error_code, "message": e.error.message},
            ) from e
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error_code": e.error.error_code, "message": e.error.message},
            ) from e

    return OrderChangeResponse(
        execution_id=str(execution.id),
        status=execution.status.value,
        workflow_type=execution.workflow_type,
        result=execution.result,
        error_details=execution.error_details,
        correlation_id=execution.correlation_id,
        created_at=execution.created_at,
        updated_at=execution.updated_at,
        completed_at=execution.completed_at,
    )


@app.post(
    "/api/v1/order-change-requests/nl",
    response_model=NLInterpretationResponse,
    status_code=status.HTTP_200_OK,
    tags=["order-changes"],
    dependencies=[Depends(verify_demo_access)],
)
async def create_order_change_request_nl(
    request: NLInterpretationRequest, db: DbSession, request_obj: Request
):
    """
    Interpret a natural language order change request and execute it with durable telemetry.

    Requires X-Demo-Key header if DEMO_API_KEY is configured.
    """
    nl_service = NLInterpreterService()

    try:
        interpretation = await nl_service.interpret(request, db=db)
    except Exception as e:
        logger.exception("Unexpected error during NL interpretation")
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "INTERNAL_ERROR",
                "message": "Internal error during interpretation",
            },
        ) from e

    if not interpretation.success:
        status_code_map = {
            "LLM_NOT_CONFIGURED": 503,
            "LLM_TIMEOUT": 504,
            "LLM_RATE_LIMIT": 429,
            "LLM_PROVIDER_ERROR": 503,
            "LLM_OUTPUT_PARSE_ERROR": 422,
            "VALIDATION_ERROR": 422,
            "AMBIGUOUS_REQUEST": 422,
            "INPUT_TOO_LARGE": 413,
            "INTERNAL_ERROR": 500,
        }
        status_code = status_code_map.get(interpretation.error_code, 422)

        raise HTTPException(
            status_code=status_code,
            detail=interpretation.model_dump(mode="json"),
        )

    assert interpretation.draft is not None

    order_change_request = OrderChangeRequest(
        source_system=request.source_system,
        external_event_id=request.external_event_id,
        customer_id=interpretation.draft.customer_id or request.customer_id or "",
        order_id=interpretation.draft.order_id,
        requested_delivery_date=interpretation.draft.requested_delivery_date,
    )

    orchestrator = WorkflowOrchestrator(db)
    correlation_id = request_obj.headers.get("X-Correlation-ID")

    try:
        execution = orchestrator.execute_order_change(
            order_change_request,
            correlation_id=correlation_id,
            interpreted_request=interpretation.draft.model_dump(mode="json"),
        )
        # Link LLM invocation with newly created workflow execution
        if interpretation.invocation_id:
            try:
                inv_uuid = uuid.UUID(interpretation.invocation_id)
                db.execute(
                    update(LLMInvocation)
                    .where(LLMInvocation.id == inv_uuid)
                    .values(workflow_execution_id=execution.id)
                )
                db.commit()
            except Exception as link_err:
                logger.warning("Failed to link LLM invocation to workflow: %s", link_err)

    except WorkflowOrchestratorError as e:
        if e.error.error_code == WorkflowErrorCode.DUPLICATE_EVENT:
            if e.existing_event and e.existing_event.workflow_execution_id:
                stmt = select(WorkflowExecution).where(
                    WorkflowExecution.id == e.existing_event.workflow_execution_id
                )
                existing_execution = db.execute(stmt).scalar_one_or_none()
                if existing_execution:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "error_code": WorkflowErrorCode.DUPLICATE_EVENT,
                            "message": "Duplicate event detected",
                            "existing_execution_id": str(e.existing_event.workflow_execution_id),
                            "existing_event_id": str(e.existing_event.id),
                        },
                    ) from e
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error_code": WorkflowErrorCode.DUPLICATE_EVENT,
                    "message": "Duplicate event detected",
                },
            ) from e
        elif e.error.error_code == WorkflowErrorCode.ORDER_NOT_FOUND:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error_code": e.error.error_code, "message": e.error.message},
            ) from e
        elif e.error.error_code == WorkflowErrorCode.CUSTOMER_ORDER_MISMATCH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error_code": e.error.error_code,
                    "message": e.error.message,
                    "details": e.error.details,
                },
            ) from e
        elif e.error.error_code == WorkflowErrorCode.INVALID_STATE_TRANSITION:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error_code": e.error.error_code, "message": e.error.message},
            ) from e
        elif e.error.error_code == WorkflowErrorCode.EXTERNAL_SERVICE_TIMEOUT:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail={"error_code": e.error.error_code, "message": e.error.message},
            ) from e
        elif e.error.error_code == WorkflowErrorCode.EXTERNAL_SERVICE_UNAVAILABLE:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error_code": e.error.error_code, "message": e.error.message},
            ) from e
        elif e.error.error_code == WorkflowErrorCode.EXTERNAL_SERVICE_ERROR:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"error_code": e.error.error_code, "message": e.error.message},
            ) from e
        else:
            logger.exception("Unexpected workflow error")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error_code": e.error.error_code, "message": e.error.message},
            ) from e
    except Exception as e:
        logger.exception("Unexpected error during workflow execution")
        raise HTTPException(
            status_code=500,
            detail={"error_code": "INTERNAL_ERROR", "message": "Workflow execution failed"},
        ) from e

    return interpretation


@app.get("/api/v1/workflows", response_model=WorkflowListResponse, tags=["workflows"])
async def list_workflows(
    db: DbSession,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Number of items per page"),
):
    offset = (page - 1) * page_size

    total_stmt = select(func.count(WorkflowExecution.id))
    total = db.execute(total_stmt).scalar_one()

    stmt = (
        select(WorkflowExecution)
        .order_by(WorkflowExecution.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    workflows = db.execute(stmt).scalars().all()

    return {
        "items": [
            {
                "id": str(w.id),
                "workflow_type": w.workflow_type,
                "status": w.status.value,
                "original_request": w.original_request,
                "interpreted_request": w.interpreted_request,
                "result": w.result,
                "error_details": w.error_details,
                "failure_category": w.failure_category,
                "correlation_id": w.correlation_id,
                "duration_ms": w.duration_ms,
                "started_at": w.started_at.isoformat() if w.started_at else None,
                "created_at": w.created_at.isoformat() if w.created_at else None,
                "updated_at": w.updated_at.isoformat() if w.updated_at else None,
                "completed_at": w.completed_at.isoformat() if w.completed_at else None,
            }
            for w in workflows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@app.get(
    "/api/v1/workflows/{execution_id}",
    response_model=WorkflowDetailResponse,
    tags=["workflows"],
)
async def get_workflow(execution_id: str, db: DbSession):
    try:
        workflow_id = uuid.UUID(execution_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid execution ID format") from e

    stmt = select(WorkflowExecution).where(WorkflowExecution.id == workflow_id)
    workflow = db.execute(stmt).scalar_one_or_none()

    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow execution not found")

    orig = workflow.original_request if isinstance(workflow.original_request, dict) else {}

    steps_data = [
        {
            "id": str(s.id),
            "step_name": s.step_name,
            "attempt_number": s.attempt_number,
            "status": s.status,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            "duration_ms": s.duration_ms,
            "error_category": s.error_category,
            "error_details": s.error_details,
            "metadata": s.step_metadata,
        }
        for s in (workflow.steps or [])
    ]

    llm_data = [
        {
            "id": str(inv.id),
            "step_name": inv.step_name,
            "provider": inv.provider,
            "model": inv.model,
            "started_at": inv.started_at.isoformat() if inv.started_at else None,
            "completed_at": inv.completed_at.isoformat() if inv.completed_at else None,
            "latency_ms": inv.latency_ms,
            "prompt_tokens": inv.prompt_tokens,
            "completion_tokens": inv.completion_tokens,
            "total_tokens": inv.total_tokens,
            "estimated_cost_usd": inv.estimated_cost_usd,
            "status": inv.status,
            "error_category": inv.error_category,
            "error_message": inv.error_message,
        }
        for inv in (workflow.llm_invocations or [])
    ]

    return {
        "id": str(workflow.id),
        "workflow_type": workflow.workflow_type,
        "status": workflow.status.value,
        "source_system": orig.get("source_system"),
        "external_event_id": orig.get("external_event_id"),
        "correlation_id": workflow.correlation_id,
        "idempotency_key": (
            orig.get("idempotency_key")
            if isinstance(orig.get("idempotency_key"), str)
            else (
                workflow.idempotency_key
                if isinstance(getattr(workflow, "idempotency_key", None), str)
                else None
            )
        ),
        "order_id": orig.get("order_id"),
        "customer_id": orig.get("customer_id"),
        "original_request": workflow.original_request,
        "interpreted_request": workflow.interpreted_request,
        "result": workflow.result,
        "error_details": workflow.error_details,
        "failure_category": workflow.failure_category,
        "started_at": workflow.started_at.isoformat() if workflow.started_at else None,
        "created_at": workflow.created_at.isoformat() if workflow.created_at else None,
        "updated_at": workflow.updated_at.isoformat() if workflow.updated_at else None,
        "completed_at": workflow.completed_at.isoformat() if workflow.completed_at else None,
        "duration_ms": workflow.duration_ms,
        "steps": steps_data,
        "llm_invocations": llm_data,
    }


@app.get(
    "/api/v1/metrics",
    response_model=DashboardMetricsResponse,
    tags=["metrics"],
)
async def get_dashboard_metrics(db: DbSession):
    """Aggregate operational metrics calculated directly from persistent database records."""
    # 1. Status distribution
    status_counts_raw = db.execute(
        select(WorkflowExecution.status, func.count(WorkflowExecution.id)).group_by(
            WorkflowExecution.status
        )
    ).all()
    status_map: dict[str, int] = {}
    for st, count in status_counts_raw:
        key = st.value if hasattr(st, "value") else str(st)
        status_map[key] = int(count)

    completed = status_map.get("completed", 0)
    failed = status_map.get("failed", 0)
    uncertain = status_map.get("uncertain", 0)
    running = status_map.get("running", 0)
    pending = status_map.get("pending", 0)
    total = sum(status_map.values())

    resolved = completed + failed
    if resolved > 0:
        success_rate = round(completed / resolved, 4)
        success_rate_percentage = f"{(success_rate * 100):.1f}%"
    else:
        success_rate = None
        success_rate_percentage = "—"

    # 2. Durations of completed executions
    duration_stmt = (
        select(WorkflowExecution.duration_ms)
        .where(
            WorkflowExecution.duration_ms.is_not(None),
            WorkflowExecution.status == WorkflowStatus.COMPLETED,
        )
        .order_by(WorkflowExecution.duration_ms.asc())
    )
    durations = db.execute(duration_stmt).scalars().all()

    median_duration_ms = None
    p95_duration_ms = None
    if durations:
        import statistics

        median_duration_ms = round(float(statistics.median(durations)), 2)
        idx_p95 = min(int(len(durations) * 0.95), len(durations) - 1)
        p95_duration_ms = round(float(durations[idx_p95]), 2)

    # 3. Step failure counts
    step_failures = db.execute(
        select(WorkflowStep.step_name, func.count(WorkflowStep.id))
        .where(WorkflowStep.status == "failed")
        .group_by(WorkflowStep.step_name)
    ).all()
    step_failure_counts = {str(name): int(count) for name, count in step_failures}

    # 4. LLM telemetry aggregate
    llm_row = db.execute(
        select(
            func.count(LLMInvocation.id),
            func.coalesce(func.sum(LLMInvocation.total_tokens), 0),
            func.coalesce(func.sum(LLMInvocation.estimated_cost_usd), 0.0),
            func.avg(LLMInvocation.latency_ms),
        )
    ).one()
    llm_total = int(llm_row[0] or 0)
    total_tokens = int(llm_row[1] or 0)
    total_cost = round(float(llm_row[2] or 0.0), 6)
    avg_latency = round(float(llm_row[3]), 2) if llm_row[3] is not None else None

    # Recent workflows
    recent_stmt = (
        select(WorkflowExecution).order_by(WorkflowExecution.created_at.desc()).limit(5)
    )
    recent_wfs = db.execute(recent_stmt).scalars().all()
    recent_serialized = [
        {
            "id": str(w.id),
            "workflow_type": w.workflow_type,
            "status": w.status.value,
            "original_request": w.original_request,
            "interpreted_request": w.interpreted_request,
            "result": w.result,
            "error_details": w.error_details,
            "failure_category": w.failure_category,
            "correlation_id": w.correlation_id,
            "duration_ms": w.duration_ms,
            "started_at": w.started_at.isoformat() if w.started_at else None,
            "created_at": w.created_at.isoformat() if w.created_at else None,
            "updated_at": w.updated_at.isoformat() if w.updated_at else None,
            "completed_at": w.completed_at.isoformat() if w.completed_at else None,
        }
        for w in recent_wfs
    ]

    return {
        "total_workflows": total,
        "completed_workflows": completed,
        "failed_workflows": failed,
        "uncertain_workflows": uncertain,
        "running_workflows": running,
        "pending_workflows": pending,
        "success_rate": success_rate,
        "success_rate_percentage": success_rate_percentage,
        "median_duration_ms": median_duration_ms,
        "p95_duration_ms": p95_duration_ms,
        "step_failure_counts": step_failure_counts,
        "total_llm_invocations": llm_total,
        "total_tokens": int(total_tokens),
        "total_estimated_cost_usd": round(float(total_cost), 4),
        "avg_llm_latency_ms": round(float(avg_latency), 2) if avg_latency is not None else None,
        "recent_workflows": recent_serialized,
    }
