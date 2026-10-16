import logging
import time
import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from relay.api.correlation import set_correlation_id, set_step_name, set_workflow_id
from relay.core.config import settings
from relay.core.logging import (
    log_order_service_call,
    log_step_event,
    log_workflow_event,
)
from relay.models import (
    InboundEvent,
    OrderChangeRequest,
    WorkflowError,
    WorkflowErrorCode,
    WorkflowExecution,
    WorkflowStatus,
    WorkflowStep,
)

logger = logging.getLogger(__name__)


class WorkflowOrchestrator:
    def __init__(self, db: Session):
        self.db = db
        self.order_service_url = str(settings.order_service_url).rstrip("/")
        self.timeout = settings.order_service_timeout

    def _create_error(
        self, error_code: str, message: str, details: dict | None = None
    ) -> WorkflowError:
        return WorkflowError(error_code=error_code, message=message, details=details)

    def _get_order(self, order_id: str, correlation_id: str | None = None) -> dict | None:
        start_time = __import__("time").monotonic()
        try:
            with httpx.Client(timeout=self.timeout) as client:
                headers = {}
                if correlation_id:
                    headers["X-Correlation-ID"] = correlation_id
                response = client.get(
                    f"{self.order_service_url}/orders/{order_id}",
                    headers=headers,
                )
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException as e:
            duration_ms = (__import__("time").monotonic() - start_time) * 1000
            log_order_service_call(
                logger,
                "GET",
                f"{self.order_service_url}/orders/{order_id}",
                status_code=None,
                duration_ms=duration_ms,
                error="timeout",
                correlation_id=correlation_id,
            )
            raise WorkflowOrchestratorError(
                self._create_error(
                    WorkflowErrorCode.EXTERNAL_SERVICE_TIMEOUT, "Order service request timed out"
                )
            ) from e
        except httpx.HTTPStatusError as e:
            duration_ms = (__import__("time").monotonic() - start_time) * 1000
            log_order_service_call(
                logger,
                "GET",
                f"{self.order_service_url}/orders/{order_id}",
                status_code=e.response.status_code,
                duration_ms=duration_ms,
                error=str(e),
                correlation_id=correlation_id,
            )
            if e.response.status_code >= 500:
                raise WorkflowOrchestratorError(
                    self._create_error(
                        WorkflowErrorCode.EXTERNAL_SERVICE_ERROR,
                        f"Order service returned error: {e.response.status_code}",
                    )
                ) from e
            raise WorkflowOrchestratorError(
                self._create_error(
                    WorkflowErrorCode.EXTERNAL_SERVICE_UNAVAILABLE,
                    f"Order service unavailable: {e.response.status_code}",
                )
            ) from e
        except httpx.RequestError as e:
            duration_ms = (__import__("time").monotonic() - start_time) * 1000
            log_order_service_call(
                logger,
                "GET",
                f"{self.order_service_url}/orders/{order_id}",
                duration_ms=duration_ms,
                error=str(e),
                correlation_id=correlation_id,
            )
            raise WorkflowOrchestratorError(
                self._create_error(
                    WorkflowErrorCode.EXTERNAL_SERVICE_UNAVAILABLE,
                    f"Failed to connect to order service: {str(e)}",
                )
            ) from e
        else:
            duration_ms = (__import__("time").monotonic() - start_time) * 1000
            log_order_service_call(
                logger,
                "GET",
                f"{self.order_service_url}/orders/{order_id}",
                status_code=response.status_code if "response" in locals() else None,
                duration_ms=duration_ms,
                correlation_id=correlation_id,
            )

    def _update_order_delivery_date(
        self,
        order_id: str,
        new_delivery_date: datetime,
        idempotency_key: str,
        correlation_id: str | None = None,
    ) -> dict:
        """Update order delivery date with idempotency key.

        The idempotency key ensures the order service can deduplicate
        repeated requests for the same logical operation.
        """
        start_time = __import__("time").monotonic()
        try:
            with httpx.Client(timeout=self.timeout) as client:
                headers = {}
                if correlation_id:
                    headers["X-Correlation-ID"] = correlation_id
                if idempotency_key:
                    headers["Idempotency-Key"] = idempotency_key
                response = client.patch(
                    f"{self.order_service_url}/orders/{order_id}",
                    json={"delivery_date": new_delivery_date.isoformat()},
                    headers=headers,
                )
                if response.status_code == 404:
                    raise WorkflowOrchestratorError(
                        self._create_error(
                            WorkflowErrorCode.ORDER_NOT_FOUND, f"Order {order_id} not found"
                        )
                    ) from None
                if response.status_code == 409:
                    raise WorkflowOrchestratorError(
                        self._create_error(
                            WorkflowErrorCode.INVALID_STATE_TRANSITION,
                            "Cannot change delivery date for order in current status",
                        )
                    ) from None
                response.raise_for_status()
                return response.json()
        except WorkflowOrchestratorError:
            raise
        except httpx.TimeoutException as e:
            duration_ms = (__import__("time").monotonic() - start_time) * 1000
            log_order_service_call(
                logger,
                "PATCH",
                f"{self.order_service_url}/orders/{order_id}",
                status_code=None,
                duration_ms=duration_ms,
                error="timeout",
                correlation_id=correlation_id,
            )
            raise WorkflowOrchestratorError(
                self._create_error(
                    WorkflowErrorCode.EXTERNAL_SERVICE_TIMEOUT, "Order service request timed out"
                )
            ) from e
        except httpx.HTTPStatusError as e:
            duration_ms = (__import__("time").monotonic() - start_time) * 1000
            log_order_service_call(
                logger,
                "PATCH",
                f"{self.order_service_url}/orders/{order_id}",
                status_code=e.response.status_code,
                duration_ms=duration_ms,
                error=str(e),
                correlation_id=correlation_id,
            )
            if e.response.status_code >= 500:
                raise WorkflowOrchestratorError(
                    self._create_error(
                        WorkflowErrorCode.EXTERNAL_SERVICE_ERROR,
                        f"Order service returned error: {e.response.status_code}",
                    )
                ) from e
            raise WorkflowOrchestratorError(
                self._create_error(
                    WorkflowErrorCode.EXTERNAL_SERVICE_UNAVAILABLE,
                    f"Order service unavailable: {e.response.status_code}",
                )
            ) from e
        except httpx.RequestError as e:
            duration_ms = (__import__("time").monotonic() - start_time) * 1000
            log_order_service_call(
                logger,
                "PATCH",
                f"{self.order_service_url}/orders/{order_id}",
                duration_ms=duration_ms,
                error=str(e),
                correlation_id=correlation_id,
            )
            raise WorkflowOrchestratorError(
                self._create_error(
                    WorkflowErrorCode.EXTERNAL_SERVICE_UNAVAILABLE,
                    f"Failed to connect to order service: {str(e)}",
                )
            ) from e
        else:
            duration_ms = (__import__("time").monotonic() - start_time) * 1000
            log_order_service_call(
                logger,
                "PATCH",
                f"{self.order_service_url}/orders/{order_id}",
                status_code=response.status_code if "response" in locals() else None,
                duration_ms=duration_ms,
                correlation_id=correlation_id,
            )

    def _create_workflow_execution(
        self,
        request: OrderChangeRequest,
        correlation_id: str | None = None,
        interpreted_request: dict | None = None,
    ) -> WorkflowExecution:
        execution = WorkflowExecution(
            workflow_type="order_change",
            status=WorkflowStatus.PENDING,
            original_request=request.to_event_payload(),
            interpreted_request=interpreted_request,
            correlation_id=correlation_id,
            started_at=datetime.now(UTC),
            # Generate idempotency key from source system and external event ID
            idempotency_key=f"{request.source_system}:{request.external_event_id}",
        )
        self.db.add(execution)
        self.db.flush()
        return execution

    def _create_inbound_event(
        self, request: OrderChangeRequest, execution_id: uuid.UUID
    ) -> InboundEvent:
        event = InboundEvent(
            source_system=request.source_system,
            external_event_id=request.external_event_id,
            payload=request.to_event_payload(),
            processing_status="processing",
            workflow_execution_id=execution_id,
        )
        self.db.add(event)
        return event

    def _get_existing_event(
        self, source_system: str, external_event_id: str
    ) -> InboundEvent | None:
        stmt = select(InboundEvent).where(
            InboundEvent.source_system == source_system,
            InboundEvent.external_event_id == external_event_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def _record_step(
        self,
        execution_id: uuid.UUID,
        step_name: str,
        status: str,
        started_at: datetime,
        completed_at: datetime | None = None,
        duration_ms: float | None = None,
        attempt_number: int = 1,
        error_category: str | None = None,
        error_details: dict | None = None,
        step_metadata: dict | None = None,
    ) -> WorkflowStep:
        """Durable step record persistence."""
        step = WorkflowStep(
            workflow_execution_id=execution_id,
            step_name=step_name,
            attempt_number=attempt_number,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=round(duration_ms, 2) if duration_ms is not None else None,
            error_category=error_category,
            error_details=error_details,
            step_metadata=step_metadata,
        )
        self.db.add(step)
        self.db.flush()
        return step

    def _mark_external_operation_pending(self, execution: WorkflowExecution) -> None:
        """Mark workflow as having initiated external operation.

        This status is persisted BEFORE making the external call,
        so we have a durable record that the operation was attempted.
        """
        execution.status = WorkflowStatus.EXTERNAL_OPERATION_PENDING
        execution.updated_at = datetime.now(UTC)
        self.db.flush()

    def _complete_execution(
        self,
        execution: WorkflowExecution,
        order: dict,
        updated_order: dict,
        duration_ms: float | None = None,
    ) -> None:
        """Mark execution as completed with result and timing."""
        execution.status = WorkflowStatus.COMPLETED
        execution.result = {
            "order_id": updated_order["id"],
            "previous_delivery_date": order["delivery_date"],
            "new_delivery_date": updated_order["delivery_date"],
            "order_status": updated_order["status"],
        }
        execution.completed_at = datetime.now(UTC)
        execution.updated_at = datetime.now(UTC)
        execution.failure_category = None
        if duration_ms is not None:
            execution.duration_ms = round(duration_ms, 2)

    def _fail_execution(
        self,
        execution: WorkflowExecution,
        error: WorkflowError,
        duration_ms: float | None = None,
    ) -> None:
        """Mark execution as failed with error details and timing."""
        execution.status = WorkflowStatus.FAILED
        execution.error_details = error.model_dump()
        execution.failure_category = error.error_code
        execution.completed_at = datetime.now(UTC)
        execution.updated_at = datetime.now(UTC)
        if duration_ms is not None:
            execution.duration_ms = round(duration_ms, 2)

    def _mark_uncertain(
        self,
        execution: WorkflowExecution,
        error: WorkflowError,
        duration_ms: float | None = None,
    ) -> None:
        """Mark execution outcome as uncertain."""
        execution.status = WorkflowStatus.UNCERTAIN
        execution.error_details = error.model_dump()
        execution.failure_category = error.error_code
        execution.completed_at = datetime.now(UTC)
        execution.updated_at = datetime.now(UTC)
        if duration_ms is not None:
            execution.duration_ms = round(duration_ms, 2)

    def execute_order_change(
        self,
        request: OrderChangeRequest,
        correlation_id: str | None = None,
        interpreted_request: dict | None = None,
    ) -> WorkflowExecution:
        wf_start_time = time.monotonic()

        if correlation_id:
            set_correlation_id(correlation_id)

        # Step 1: Inbound Validation and Idempotency Verification
        step1_name = "validate_inbound_request"
        step1_start = time.monotonic()
        step1_utc = datetime.now(UTC)
        set_step_name(step1_name)
        log_step_event(logger, "started", step1_name, "running")

        existing_event = self._get_existing_event(request.source_system, request.external_event_id)
        if existing_event:
            step1_dur = (time.monotonic() - step1_start) * 1000
            log_step_event(
                logger,
                "failed",
                step1_name,
                "failed",
                duration_ms=step1_dur,
                error_category=WorkflowErrorCode.DUPLICATE_EVENT,
            )
            raise WorkflowOrchestratorError(
                self._create_error(WorkflowErrorCode.DUPLICATE_EVENT, "Duplicate event detected"),
                existing_event=existing_event,
            ) from None

        execution = self._create_workflow_execution(request, correlation_id, interpreted_request)
        event = self._create_inbound_event(request, execution.id)
        set_workflow_id(str(execution.id))

        try:
            self.db.flush()
        except IntegrityError as e:
            self.db.rollback()
            step1_dur = (time.monotonic() - step1_start) * 1000
            log_step_event(
                logger,
                "failed",
                step1_name,
                "failed",
                duration_ms=step1_dur,
                error_category=WorkflowErrorCode.DUPLICATE_EVENT,
            )
            raise WorkflowOrchestratorError(
                self._create_error(WorkflowErrorCode.DUPLICATE_EVENT, "Duplicate event detected"),
            ) from e

        step1_dur = (time.monotonic() - step1_start) * 1000
        self._record_step(
            execution.id,
            step1_name,
            "completed",
            step1_utc,
            completed_at=datetime.now(UTC),
            duration_ms=step1_dur,
        )
        log_step_event(logger, "completed", step1_name, "completed", duration_ms=step1_dur)

        execution.status = WorkflowStatus.RUNNING
        execution.updated_at = datetime.now(UTC)
        self.db.flush()
        log_workflow_event(logger, "transition", str(execution.id), "running")

        current_step = None
        step_start = None
        step_utc = None

        try:
            # Step 2: Fetch and Validate Order from Order Service
            current_step = "fetch_order_details"
            step_start = time.monotonic()
            step_utc = datetime.now(UTC)
            set_step_name(current_step)
            log_step_event(logger, "started", current_step, "running")

            order = self._get_order(request.order_id, correlation_id)
            if order is None:
                step_dur = (time.monotonic() - step_start) * 1000
                self._record_step(
                    execution.id,
                    current_step,
                    "failed",
                    step_utc,
                    completed_at=datetime.now(UTC),
                    duration_ms=step_dur,
                    error_category=WorkflowErrorCode.ORDER_NOT_FOUND,
                    error_details={"order_id": request.order_id},
                )
                log_step_event(
                    logger,
                    "failed",
                    current_step,
                    "failed",
                    duration_ms=step_dur,
                    error_category=WorkflowErrorCode.ORDER_NOT_FOUND,
                )
                raise WorkflowOrchestratorError(
                    self._create_error(
                        WorkflowErrorCode.ORDER_NOT_FOUND, f"Order {request.order_id} not found"
                    )
                )

            if order["customer_id"] != request.customer_id:
                step_dur = (time.monotonic() - step_start) * 1000
                self._record_step(
                    execution.id,
                    current_step,
                    "failed",
                    step_utc,
                    completed_at=datetime.now(UTC),
                    duration_ms=step_dur,
                    error_category=WorkflowErrorCode.CUSTOMER_ORDER_MISMATCH,
                    error_details={
                        "order_customer_id": order["customer_id"],
                        "request_customer_id": request.customer_id,
                    },
                )
                log_step_event(
                    logger,
                    "failed",
                    current_step,
                    "failed",
                    duration_ms=step_dur,
                    error_category=WorkflowErrorCode.CUSTOMER_ORDER_MISMATCH,
                )
                raise WorkflowOrchestratorError(
                    self._create_error(
                        WorkflowErrorCode.CUSTOMER_ORDER_MISMATCH,
                        (
                            f"Order {request.order_id} does not belong to customer "
                            f"{request.customer_id}"
                        ),
                        details={"order_customer_id": order["customer_id"]},
                    )
                )

            step_dur = (time.monotonic() - step_start) * 1000
            self._record_step(
                execution.id,
                current_step,
                "completed",
                step_utc,
                completed_at=datetime.now(UTC),
                duration_ms=step_dur,
                step_metadata={"order_status": order.get("status")},
            )
            log_step_event(logger, "completed", current_step, "completed", duration_ms=step_dur)

            # Step 3: Record Pending External Operation (Persisted Before Remote Call)
            current_step = "record_pending_external_op"
            step_start = time.monotonic()
            step_utc = datetime.now(UTC)
            set_step_name(current_step)
            log_step_event(logger, "started", current_step, "running")

            self._mark_external_operation_pending(execution)
            self._record_step(
                execution.id,
                current_step,
                "completed",
                step_utc,
                completed_at=datetime.now(UTC),
                duration_ms=(time.monotonic() - step_start) * 1000,
            )
            log_step_event(logger, "completed", current_step, "completed")
            self.db.commit()

            # Step 4: Execute External Operation with Idempotency Key
            current_step = "execute_delivery_update"
            step_start = time.monotonic()
            step_utc = datetime.now(UTC)
            set_step_name(current_step)
            log_step_event(logger, "started", current_step, "running")

            updated_order = self._update_order_delivery_date(
                request.order_id,
                request.requested_delivery_date,
                execution.idempotency_key,
                correlation_id,
            )

            step_dur = (time.monotonic() - step_start) * 1000
            self._record_step(
                execution.id,
                current_step,
                "completed",
                step_utc,
                completed_at=datetime.now(UTC),
                duration_ms=step_dur,
                step_metadata={"new_delivery_date": updated_order.get("delivery_date")},
            )
            log_step_event(logger, "completed", current_step, "completed", duration_ms=step_dur)

            # Step 5: Finalize Execution
            total_duration_ms = (time.monotonic() - wf_start_time) * 1000
            self._complete_execution(execution, order, updated_order, duration_ms=total_duration_ms)
            event.processing_status = "completed"
            self.db.commit()
            log_workflow_event(
                logger,
                "completed",
                str(execution.id),
                "completed",
                duration_ms=total_duration_ms,
            )

        except WorkflowOrchestratorError as e:
            total_duration_ms = (time.monotonic() - wf_start_time) * 1000
            if current_step and current_step == "execute_delivery_update":
                step_dur = (time.monotonic() - step_start) * 1000 if step_start else None
                self._record_step(
                    execution.id,
                    current_step,
                    "failed",
                    step_utc or datetime.now(UTC),
                    completed_at=datetime.now(UTC),
                    duration_ms=step_dur,
                    error_category=e.error.error_code,
                    error_details=e.error.details,
                )
                log_step_event(
                    logger,
                    "failed",
                    current_step,
                    "failed",
                    duration_ms=step_dur,
                    error_category=e.error.error_code,
                )

            self._fail_execution(execution, e.error, duration_ms=total_duration_ms)
            event.processing_status = "failed"
            if e.existing_event:
                event = e.existing_event
            self.db.commit()
            log_workflow_event(
                logger,
                "failed",
                str(execution.id),
                "failed",
                duration_ms=total_duration_ms,
                error_category=e.error.error_code,
            )
            raise

        except Exception as e:
            total_duration_ms = (time.monotonic() - wf_start_time) * 1000
            logger.exception("Unexpected error during order change workflow")
            if current_step:
                step_dur = (time.monotonic() - step_start) * 1000 if step_start else None
                self._record_step(
                    execution.id,
                    current_step,
                    "uncertain",
                    step_utc or datetime.now(UTC),
                    completed_at=datetime.now(UTC),
                    duration_ms=step_dur,
                    error_category=WorkflowErrorCode.INTERNAL_ERROR,
                    error_details={"error": str(e)},
                )
            error = self._create_error(
                WorkflowErrorCode.INTERNAL_ERROR,
                "Unexpected execution failure",
                {"error": str(e)},
            )
            self._mark_uncertain(execution, error, duration_ms=total_duration_ms)
            event.processing_status = "uncertain"
            self.db.commit()
            log_workflow_event(
                logger,
                "uncertain",
                str(execution.id),
                "uncertain",
                duration_ms=total_duration_ms,
                error_category=WorkflowErrorCode.INTERNAL_ERROR,
            )
            raise WorkflowOrchestratorError(error) from e

        return execution

    def recover_uncertain_workflows(self) -> list[WorkflowExecution]:
        """Find and attempt to recover workflows in UNCERTAIN or
        EXTERNAL_OPERATION_PENDING state.

        For each such workflow, check the order service using the idempotency
        key to determine if the external operation was applied, then update
        the workflow accordingly.

        Returns list of recovered executions.
        """
        stmt = select(WorkflowExecution).where(
            WorkflowExecution.status.in_(
                [WorkflowStatus.UNCERTAIN, WorkflowStatus.EXTERNAL_OPERATION_PENDING]
            )
        )
        executions = self.db.execute(stmt).scalars().all()

        recovered = []
        for execution in executions:
            recovery_start = time.monotonic()
            recovery_utc = datetime.now(UTC)
            try:
                # Get the order_id and idempotency key from the execution
                original = execution.original_request
                order_id = original.get("order_id")
                idempotency_key = execution.idempotency_key
                if not order_id or not idempotency_key:
                    logger.warning(
                        f"Cannot recover {execution.id}: missing order_id or idempotency_key"
                    )
                    continue

                # Check if idempotency key exists in order service
                idempotency_exists = self._check_idempotency_key(order_id, idempotency_key)

                if idempotency_exists:
                    # External operation was applied - mark completed
                    order = self._get_order(order_id)
                    if order is not None:
                        self._complete_execution(execution, order, order)
                        execution.status = WorkflowStatus.COMPLETED
                    else:
                        execution.status = WorkflowStatus.COMPLETED
                        execution.completed_at = datetime.now(UTC)
                else:
                    # Idempotency key not found - external operation didn't take effect
                    error = self._create_error(
                        WorkflowErrorCode.EXTERNAL_SERVICE_ERROR,
                        (
                            "Recovery: external operation did not take effect "
                            "(idempotency key not found)"
                        ),
                    )
                    self._fail_execution(execution, error)

                rec_dur = (time.monotonic() - recovery_start) * 1000
                self._record_step(
                    execution.id,
                    "recover_uncertain_workflow",
                    "completed" if execution.status == WorkflowStatus.COMPLETED else "failed",
                    recovery_utc,
                    completed_at=datetime.now(UTC),
                    duration_ms=rec_dur,
                    step_metadata={"recovered_status": execution.status.value},
                )
                self.db.commit()
                recovered.append(execution)
                logger.info(f"Recovered workflow {execution.id} to {execution.status.value}")

            except Exception:
                logger.exception(f"Failed to recover workflow {execution.id}")
                self.db.rollback()

        return recovered

    def _check_idempotency_key(self, order_id: str, idempotency_key: str) -> bool:
        """Check if idempotency key exists in order service."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    f"{self.order_service_url}/orders/{order_id}/idempotency/{idempotency_key}"
                )
                if response.status_code == 404:
                    return False
                response.raise_for_status()
                return response.json().get("exists", False)
        except Exception as e:
            logger.warning(f"Failed to check idempotency key for {order_id}: {e}")
            return False


class WorkflowOrchestratorError(Exception):
    def __init__(self, error: WorkflowError, existing_event: InboundEvent | None = None):
        self.error = error
        self.existing_event = existing_event
        super().__init__(error.message)
