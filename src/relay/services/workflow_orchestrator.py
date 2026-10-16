import logging
import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from relay.core.config import settings
from relay.core.logging import log_order_service_call
from relay.models import (
    InboundEvent,
    OrderChangeRequest,
    WorkflowError,
    WorkflowErrorCode,
    WorkflowExecution,
    WorkflowStatus,
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

    def _create_workflow_execution(self, request: OrderChangeRequest) -> WorkflowExecution:
        execution = WorkflowExecution(
            workflow_type="order_change",
            status=WorkflowStatus.PENDING,
            original_request=request.to_event_payload(),
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

    def _mark_external_operation_pending(self, execution: WorkflowExecution) -> None:
        """Mark workflow as having initiated external operation.

        This status is persisted BEFORE making the external call,
        so we have a durable record that the operation was attempted.
        """
        execution.status = WorkflowStatus.EXTERNAL_OPERATION_PENDING
        execution.updated_at = datetime.now(UTC)
        self.db.flush()

    def _complete_execution(
        self, execution: WorkflowExecution, order: dict, updated_order: dict
    ) -> None:
        """Mark execution as completed with result."""
        execution.status = WorkflowStatus.COMPLETED
        execution.result = {
            "order_id": updated_order["id"],
            "previous_delivery_date": order["delivery_date"],
            "new_delivery_date": updated_order["delivery_date"],
            "order_status": updated_order["status"],
        }
        execution.completed_at = datetime.now(UTC)

    def _fail_execution(self, execution: WorkflowExecution, error: WorkflowError) -> None:
        """Mark execution as failed with error details."""
        execution.status = WorkflowStatus.FAILED
        execution.error_details = error.model_dump()
        execution.completed_at = datetime.now(UTC)

    def _mark_uncertain(self, execution: WorkflowExecution, error: WorkflowError) -> None:
        """Mark execution outcome as uncertain (external op may have succeeded).

        Used when external call succeeds but local commit fails,
        or when external call times out and outcome is unknown.
        """
        execution.status = WorkflowStatus.UNCERTAIN
        execution.error_details = error.model_dump()
        execution.completed_at = datetime.now(UTC)

    def execute_order_change(
        self, request: OrderChangeRequest, correlation_id: str | None = None
    ) -> WorkflowExecution:
        # Set correlation ID in context for logging
        from relay.api.correlation import set_correlation_id, set_workflow_id

        if correlation_id:
            set_correlation_id(correlation_id)

        existing_event = self._get_existing_event(request.source_system, request.external_event_id)
        if existing_event:
            raise WorkflowOrchestratorError(
                self._create_error(WorkflowErrorCode.DUPLICATE_EVENT, "Duplicate event detected"),
                existing_event=existing_event,
            ) from None

        execution = self._create_workflow_execution(request)
        event = self._create_inbound_event(request, execution.id)

        # Set workflow ID in context for logging
        set_workflow_id(str(execution.id))

        try:
            self.db.flush()
        except IntegrityError as e:
            self.db.rollback()
            raise WorkflowOrchestratorError(
                self._create_error(WorkflowErrorCode.DUPLICATE_EVENT, "Duplicate event detected"),
            ) from e

        execution.status = WorkflowStatus.RUNNING
        execution.updated_at = datetime.now(UTC)
        self.db.flush()

        try:
            order = self._get_order(request.order_id, correlation_id)
            if order is None:
                raise WorkflowOrchestratorError(
                    self._create_error(
                        WorkflowErrorCode.ORDER_NOT_FOUND, f"Order {request.order_id} not found"
                    )
                )

            if order["customer_id"] != request.customer_id:
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

            # Mark external operation as pending AND COMMIT IT
            # This creates a durable record that we attempted the operation
            # BEFORE making the external call, so recovery can find it
            self._mark_external_operation_pending(execution)
            self.db.commit()

            updated_order = self._update_order_delivery_date(
                request.order_id,
                request.requested_delivery_date,
                execution.idempotency_key,
                correlation_id,
            )

            # External operation confirmed - mark as completed
            self._complete_execution(execution, order, updated_order)
            event.processing_status = "completed"
            self.db.commit()

        except WorkflowOrchestratorError as e:
            # For known errors, mark as failed (not uncertain)
            # The external operation either failed or was rejected by order service
            self._fail_execution(execution, e.error)
            event.processing_status = "failed"
            if e.existing_event:
                event = e.existing_event
            self.db.commit()
            raise

        except Exception as e:
            # For unexpected errors (including timeout where outcome is unknown),
            # mark as uncertain so recovery can investigate
            logger.exception("Unexpected error during order change workflow")
            error = self._create_error(
                WorkflowErrorCode.INTERNAL_ERROR, "Unexpected execution failure", {"error": str(e)}
            )
            self._mark_uncertain(execution, error)
            event.processing_status = "uncertain"
            self.db.commit()
            raise WorkflowOrchestratorError(
                self._create_error(
                    WorkflowErrorCode.INTERNAL_ERROR,
                    "Unexpected execution failure",
                    {"error": str(e)},
                )
            ) from e

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
                # This tells us if the external operation was actually applied
                idempotency_exists = self._check_idempotency_key(order_id, idempotency_key)

                if idempotency_exists:
                    # External operation was applied - mark completed
                    order = self._get_order(order_id)
                    if order is not None:
                        self._complete_execution(execution, order, order)
                        execution.status = WorkflowStatus.COMPLETED
                    else:
                        # Order not found but idempotency key exists - still mark completed
                        execution.status = WorkflowStatus.COMPLETED
                        execution.completed_at = datetime.now(UTC)
                else:
                    # Idempotency key not found - external operation didn't take effect
                    # Mark as failed so it can be retried
                    error = self._create_error(
                        WorkflowErrorCode.EXTERNAL_SERVICE_ERROR,
                        (
                            "Recovery: external operation did not take effect "
                            "(idempotency key not found)"
                        ),
                    )
                    self._fail_execution(execution, error)

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
