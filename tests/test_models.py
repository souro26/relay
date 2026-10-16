"""Model tests with mocked database for unit testing."""

import uuid
from datetime import UTC, datetime

from relay.models import InboundEvent, WorkflowExecution, WorkflowStatus


class TestWorkflowExecutionModel:
    def test_workflow_execution_creation(self):
        workflow = WorkflowExecution(
            id=uuid.uuid4(),
            workflow_type="order_modification",
            status=WorkflowStatus.PENDING,
            original_request={"order_id": "123"},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert workflow.workflow_type == "order_modification"
        assert workflow.status == WorkflowStatus.PENDING
        assert workflow.original_request == {"order_id": "123"}
        assert workflow.interpreted_request is None
        assert workflow.result is None
        assert workflow.error_details is None
        assert isinstance(workflow.id, uuid.UUID)
        assert isinstance(workflow.created_at, datetime)
        assert isinstance(workflow.updated_at, datetime)
        assert workflow.completed_at is None

    def test_workflow_execution_with_all_fields(self):
        completed_at = datetime.now(UTC)
        workflow = WorkflowExecution(
            id=uuid.uuid4(),
            workflow_type="order_modification",
            status=WorkflowStatus.RUNNING,
            original_request={"order_id": "123"},
            interpreted_request={"action": "change_delivery_date", "new_date": "2026-10-15"},
            result={"success": True},
            error_details=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            completed_at=completed_at,
        )
        assert workflow.status == WorkflowStatus.RUNNING
        expected = {"action": "change_delivery_date", "new_date": "2026-10-15"}
        assert workflow.interpreted_request == expected
        assert workflow.result == {"success": True}
        assert workflow.completed_at == completed_at


class TestInboundEventModel:
    def test_inbound_event_creation(self):
        event = InboundEvent(
            id=uuid.uuid4(),
            source_system="email",
            external_event_id="evt_123",
            payload={"subject": "Order change request"},
            processing_status="received",
            created_at=datetime.now(UTC),
        )
        assert event.source_system == "email"
        assert event.external_event_id == "evt_123"
        assert event.payload == {"subject": "Order change request"}
        assert event.processing_status == "received"
        assert isinstance(event.id, uuid.UUID)
        assert isinstance(event.created_at, datetime)
        assert event.workflow_execution_id is None

    def test_inbound_event_with_workflow(self):
        workflow_id = uuid.uuid4()
        event = InboundEvent(
            id=uuid.uuid4(),
            source_system="webhook",
            external_event_id="evt_456",
            payload={"data": "test"},
            workflow_execution_id=workflow_id,
            processing_status="processed",
            created_at=datetime.now(UTC),
        )
        assert event.workflow_execution_id == workflow_id
        assert event.processing_status == "processed"


class TestInboundEventUniquenessConstraint:
    def test_duplicate_source_and_external_id_raises_error(self):
        """Test that duplicate source_system + external_event_id would raise IntegrityError."""
        # This test verifies the model definition has the constraint
        from sqlalchemy import UniqueConstraint

        from relay.models import InboundEvent

        table = InboundEvent.__table__
        # Check for unique constraint on source_system + external_event_id
        unique_constraints = [c for c in table.constraints if isinstance(c, UniqueConstraint)]
        assert len(unique_constraints) >= 1
        # Find the constraint on source_system + external_event_id
        found = False
        for constraint in unique_constraints:
            cols = [c.name for c in constraint.columns]
            if "source_system" in cols and "external_event_id" in cols:
                found = True
                break
        assert found, "Unique constraint on source_system + external_event_id not found"

    def test_different_source_allows_same_external_id(self):
        """Test that different source_system allows same external_event_id."""
        # This test verifies the model allows different sources
        from relay.models import InboundEvent

        event1 = InboundEvent(
            id=uuid.uuid4(),
            source_system="email",
            external_event_id="evt_123",
            payload={"subject": "Test"},
            created_at=datetime.now(UTC),
        )
        event2 = InboundEvent(
            id=uuid.uuid4(),
            source_system="webhook",
            external_event_id="evt_123",
            payload={"subject": "Test"},
            created_at=datetime.now(UTC),
        )
        # Both events should be valid model instances
        assert event1.source_system == "email"
        assert event2.source_system == "webhook"
        assert event1.external_event_id == event2.external_event_id == "evt_123"


class TestWorkflowStatusEnum:
    def test_workflow_status_values(self):
        assert WorkflowStatus.PENDING == "pending"
        assert WorkflowStatus.RUNNING == "running"
        assert WorkflowStatus.COMPLETED == "completed"
        assert WorkflowStatus.FAILED == "failed"

    def test_workflow_status_is_string_enum(self):
        assert isinstance(WorkflowStatus.PENDING, str)
        assert isinstance(WorkflowStatus.RUNNING, str)


class TestCircularImportRegression:
    """Regression tests for circular import fixes."""

    def test_order_service_models_import_without_application_init(self):
        """Test that order_service.models can be imported without triggering app init."""
        # This import should not trigger application initialization (logging, etc.)
        from order_service.models import IdempotencyKey, Order, OrderStatus

        # Verify the models are accessible
        assert Order is not None
        assert IdempotencyKey is not None
        assert OrderStatus is not None

    def test_relay_models_import_without_application_init(self):
        """Test that relay models can be imported without triggering app init."""
        from relay.models import (
            InboundEvent,
            NLInterpretationRequest,
            WorkflowExecution,
            WorkflowStatus,
        )

        assert InboundEvent is not None
        assert WorkflowExecution is not None
        assert WorkflowStatus is not None
        assert NLInterpretationRequest is not None

    def test_order_service_models_and_relay_models_both_importable(self):
        """Test that both model sets can be imported without circular import issues."""
        # This should not raise any import errors or cause circular imports
        from order_service.models import Order
        from order_service.models import OrderStatus as OSOrderStatus
        from relay.models import WorkflowExecution
        from relay.models import WorkflowStatus as RelayWorkflowStatus

        # Both should be accessible
        assert Order is not None
        assert OSOrderStatus is not None
        assert WorkflowExecution is not None
        assert RelayWorkflowStatus is not None

    def test_order_service_app_accessible_via_get_app(self):
        """Test that order_service app is accessible via get_app() without eager import."""
        from order_service import get_app

        app = get_app()
        assert app is not None
        assert hasattr(app, "title")
        assert app.title == "Order Management Service"

    def test_relay_app_accessible_via_get_app(self):
        """Test that relay app is accessible via get_app() without eager import."""
        from relay import get_app

        app = get_app()
        assert app is not None
        assert hasattr(app, "title")
        assert app.title == "Relay"
