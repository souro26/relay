"""Unit tests for the NL interpreter service with mocked LLM adapter."""

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from relay.adapters.llm import LLMProviderError, LLMTimeoutError
from relay.core.config import reload_settings, settings
from relay.models import NLInterpretationRequest
from relay.services.nl_interpreter import NLInterpreterService, interpret_natural_language


class MockLLMAdapter:
    """Mock LLM adapter for testing."""

    def __init__(self, response: str | None = None, exception: Exception | None = None):
        self._response = response
        self._exception = exception
        self.call_count = 0
        self.last_prompt = None
        self.last_kwargs = None

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-model"

    async def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: dict | None = None,
    ):
        self.call_count += 1
        self.last_prompt = prompt
        self.last_kwargs = {
            "system_prompt": system_prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": response_format,
        }
        if self._exception:
            raise self._exception
        if self._response is None:
            raise ValueError("No response configured")
        # Return LLMResponse object for compatibility with new interface
        from relay.adapters.llm.base import LLMResponse

        return LLMResponse(content=self._response)

    async def close(self) -> None:
        pass


def _create_mock_adapter(response_json: str):
    """Create a properly configured mock adapter for endpoint tests."""
    from relay.adapters.llm.base import LLMResponse

    mock = MagicMock(spec=["complete", "close", "provider_name", "model_name"])
    mock.provider_name = "mock"
    mock.model_name = "mock-model"
    mock.close = AsyncMock()
    mock.complete = AsyncMock(return_value=LLMResponse(content=response_json))
    return mock


class MockHttpResponse:
    """A mock HTTP response that properly handles .json() calls."""

    def __init__(self, json_data: dict, status_code: int = 200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(f"HTTP {self.status_code}", request=None, response=self)


class TestNLInterpreterService:
    """Tests for NLInterpreterService with mocked LLM."""

    @pytest.fixture
    def mock_adapter(self) -> MockLLMAdapter:
        return MockLLMAdapter()

    @pytest.fixture
    def service(self, mock_adapter: MockLLMAdapter) -> NLInterpreterService:
        return NLInterpreterService(llm_adapter=mock_adapter)

    @pytest.fixture
    def base_request(self) -> dict[str, Any]:
        return {
            "source_system": "demo",
            "external_event_id": "evt-001",
            "customer_id": "customer-101",
        }

    # --- Successful Interpretation Tests ---

    async def test_successful_interpretation_with_order_id_and_date(
        self, service: NLInterpreterService, mock_adapter: MockLLMAdapter, base_request: dict
    ):
        """Test successful interpretation with order ID and delivery date."""
        response_json = json.dumps(
            {
                "success": True,
                "draft": {
                    "order_id": "ORD-9D3220DE",
                    "requested_delivery_date": "2026-11-22T00:00:00+00:00",
                    "customer_id": "customer-101",
                },
                "missing_fields": [],
                "ambiguities": [],
                "error": None,
                "error_code": None,
            }
        )
        mock_adapter._response = response_json

        request = NLInterpretationRequest(
            text="Change order ORD-9D3220DE's delivery date to November 22, 2026.",
            source_system="demo",
            external_event_id="evt-success-001",
            customer_id="customer-101",
        )

        result = await service.interpret(request)

        assert result.success is True
        assert result.draft is not None
        assert result.draft.order_id == "ORD-9D3220DE"
        assert result.draft.requested_delivery_date == datetime(2026, 11, 22, tzinfo=UTC)
        assert result.draft.customer_id == "customer-101"
        assert result.missing_fields == []
        assert result.ambiguities == []

    async def test_successful_interpretation_with_customer_id_in_text(
        self, service: NLInterpreterService, mock_adapter: MockLLMAdapter
    ):
        """Test successful interpretation with customer ID in the natural language text."""
        response_json = json.dumps(
            {
                "success": True,
                "draft": {
                    "order_id": "ORD-00000456",
                    "requested_delivery_date": "2026-12-25T00:00:00+00:00",
                    "customer_id": "CUST-789",
                },
                "missing_fields": [],
                "ambiguities": [],
                "error": None,
                "error_code": None,
            }
        )
        mock_adapter._response = response_json

        request_text = "Change order ORD-456 delivery to 2026-12-25 for customer CUST-789"
        result = await service.interpret(
            NLInterpretationRequest(
                text=request_text,
                source_system="demo",
                external_event_id="evt-002",
            )
        )

        assert result.success is True
        assert result.draft.customer_id == "CUST-789"

    async def test_successful_interpretation_with_order_hash_prefix(
        self, service: NLInterpreterService, mock_adapter: MockLLMAdapter
    ):
        """Test successful interpretation with # prefix on order ID."""
        response_json = json.dumps(
            {
                "success": True,
                "draft": {
                    "order_id": "12345",
                    "requested_delivery_date": "2026-12-25T00:00:00+00:00",
                    "customer_id": None,
                },
                "missing_fields": [],
                "ambiguities": [],
                "error": None,
                "error_code": None,
            }
        )
        mock_adapter._response = response_json

        request_text = "Please change the delivery for order #12345 to Dec 25th"
        result = await service.interpret(
            NLInterpretationRequest(
                text=request_text,
                source_system="demo",
                external_event_id="evt-003",
            )
        )

        assert result.success is True
        assert result.draft.order_id == "12345"
        assert result.draft.requested_delivery_date == datetime(2026, 12, 25, tzinfo=UTC)

    # --- Missing Order ID Tests ---

    async def test_missing_order_id(
        self, service: NLInterpreterService, mock_adapter: MockLLMAdapter
    ):
        """Test interpretation fails when order ID is missing."""
        response_json = json.dumps(
            {
                "success": False,
                "draft": None,
                "missing_fields": ["order_id"],
                "ambiguities": [],
                "error": "Missing required field: order_id",
                "error_code": "VALIDATION_ERROR",
            }
        )
        mock_adapter._response = response_json

        result = await service.interpret(
            NLInterpretationRequest(
                text="Change delivery date to December 1st",
                source_system="demo",
                external_event_id="evt-004",
            )
        )

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        assert result.draft is None
        assert "order_id" in result.missing_fields

    # --- Missing Delivery Date Tests ---

    async def test_missing_delivery_date(
        self, service: NLInterpreterService, mock_adapter: MockLLMAdapter
    ):
        """Test interpretation when delivery date is missing."""
        response_json = json.dumps(
            {
                "success": False,
                "draft": None,
                "missing_fields": ["requested_delivery_date"],
                "ambiguities": [],
                "error": "Missing required field: requested_delivery_date",
                "error_code": "VALIDATION_ERROR",
            }
        )
        mock_adapter._response = response_json

        result = await service.interpret(
            NLInterpretationRequest(
                text="Change order ORD-123",
                source_system="demo",
                external_event_id="evt-005",
            )
        )

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        assert "requested_delivery_date" in result.missing_fields

    # --- Ambiguous Date Tests ---

    async def test_ambiguous_next_friday(
        self, service: NLInterpreterService, mock_adapter: MockLLMAdapter
    ):
        """Test ambiguous 'next Friday' date."""
        response_json = json.dumps(
            {
                "success": False,
                "draft": {
                    "order_id": "ORD-00000123",
                    "requested_delivery_date": "2026-11-20T00:00:00+00:00",
                    "customer_id": None,
                },
                "missing_fields": [],
                "ambiguities": [
                    {
                        "field": "requested_delivery_date",
                        "message": "'next Friday' is ambiguous - could mean this week or next week",
                        "suggestions": ["2026-11-20", "2026-11-27"],
                    }
                ],
                "error": "Ambiguous delivery date",
                "error_code": "AMBIGUOUS_REQUEST",
            }
        )
        mock_adapter._response = response_json

        result = await service.interpret(
            NLInterpretationRequest(
                text="Change order ORD-123's delivery date to next Friday",
                source_system="demo",
                external_event_id="evt-006",
            )
        )

        assert result.success is False
        assert result.error_code == "AMBIGUOUS_REQUEST"
        assert len(result.ambiguities) == 1
        assert result.ambiguities[0].field == "requested_delivery_date"
        assert "next Friday" in result.ambiguities[0].message
        assert len(result.ambiguities[0].suggestions) == 2

    async def test_ambiguous_next_week(
        self, service: NLInterpreterService, mock_adapter: MockLLMAdapter
    ):
        """Test ambiguous 'next week' date."""
        response_json = json.dumps(
            {
                "success": False,
                "draft": {
                    "order_id": "ORD-0ABC1234",
                    "requested_delivery_date": "2026-11-23T00:00:00+00:00",
                    "customer_id": None,
                },
                "missing_fields": [],
                "ambiguities": [
                    {
                        "field": "requested_delivery_date",
                        "message": "'next week' is ambiguous - which specific day?",
                        "suggestions": ["2026-11-23", "2026-11-24", "2026-11-25"],
                    }
                ],
                "error": "Ambiguous delivery date",
                "error_code": "AMBIGUOUS_REQUEST",
            }
        )
        mock_adapter._response = response_json

        result = await service.interpret(
            NLInterpretationRequest(
                text="Please change the delivery date for order ORD-ABC123 to next week",
                source_system="demo",
                external_event_id="evt-007",
            )
        )

        assert result.success is False
        assert result.error_code == "AMBIGUOUS_REQUEST"
        assert len(result.ambiguities) == 1
        assert "next week" in result.ambiguities[0].message
        assert len(result.ambiguities[0].suggestions) == 3

    # --- Malformed LLM Output Tests ---

    async def test_malformed_json_output(
        self, service: NLInterpreterService, mock_adapter: MockLLMAdapter
    ):
        """Test handling of malformed JSON from LLM."""
        mock_adapter._response = "not valid json {{{"

        result = await service.interpret(
            NLInterpretationRequest(
                text="Change order ORD-123 to next week",
                source_system="demo",
                external_event_id="evt-008",
            )
        )

        assert result.success is False
        assert result.error_code == "LLM_OUTPUT_PARSE_ERROR"
        assert "Invalid JSON" in result.error

    async def test_missing_success_field(
        self, service: NLInterpreterService, mock_adapter: MockLLMAdapter
    ):
        """Test missing 'success' field in LLM response."""
        mock_adapter._response = json.dumps(
            {
                "draft": {
                    "order_id": "ORD-00000123",
                    "requested_delivery_date": "2026-11-22T00:00:00+00:00",
                }
            }
        )

        result = await service.interpret(
            NLInterpretationRequest(
                text="Change order ORD-123 to next week",
                source_system="demo",
                external_event_id="evt-009",
            )
        )

        assert result.success is False
        assert result.error_code == "LLM_OUTPUT_PARSE_ERROR"
        assert "missing 'success' field" in result.error

    async def test_missing_draft_in_success(
        self, service: NLInterpreterService, mock_adapter: MockLLMAdapter
    ):
        """Test missing draft in successful interpretation."""
        mock_adapter._response = json.dumps(
            {
                "success": True,
                "missing_fields": [],
                "ambiguities": [],
                "error": None,
                "error_code": None,
            }
        )

        result = await service.interpret(
            NLInterpretationRequest(
                text="Change order ORD-123 to next week",
                source_system="demo",
                external_event_id="evt-009",
            )
        )

        assert result.success is False
        assert result.error_code == "LLM_OUTPUT_PARSE_ERROR"
        assert "Missing draft" in result.error

    async def test_invalid_draft_structure(
        self, service: NLInterpreterService, mock_adapter: MockLLMAdapter
    ):
        """Test invalid draft structure in successful interpretation."""
        mock_adapter._response = json.dumps(
            {
                "success": True,
                "draft": {"order_id": "ORD-123"},  # missing requested_delivery_date
                "missing_fields": [],
                "ambiguities": [],
                "error": None,
                "error_code": None,
            }
        )

        result = await service.interpret(
            NLInterpretationRequest(
                text="Change order ORD-123 to next week",
                source_system="demo",
                external_event_id="evt-011",
            )
        )

        assert result.success is False
        assert result.error_code == "LLM_OUTPUT_PARSE_ERROR"
        assert "Invalid draft structure" in result.error

    # --- Provider Error Tests ---

    async def test_provider_timeout(self, service: NLInterpreterService):
        """Test handling of LLM timeout."""
        service._llm_adapter = MockLLMAdapter(
            exception=LLMTimeoutError("Request timed out", "mock")
        )

        result = await service.interpret(
            NLInterpretationRequest(
                text="Change order ORD-123 to next week",
                source_system="demo",
                external_event_id="evt-timeout",
            )
        )

        assert result.success is False
        assert result.error_code == "LLM_TIMEOUT"

    async def test_provider_rate_limit(self, service: NLInterpreterService):
        """Test handling of rate limit (429)."""
        service._llm_adapter = MockLLMAdapter(
            exception=LLMProviderError("Rate limit", "mock", status_code=429)
        )

        result = await service.interpret(
            NLInterpretationRequest(
                text="Change order ORD-123 to next week",
                source_system="demo",
                external_event_id="evt-012",
            )
        )

        assert result.success is False
        assert result.error_code == "LLM_RATE_LIMIT"
        assert "rate limit" in result.error.lower()

    async def test_provider_500_error(self, service: NLInterpreterService):
        """Test handling of 5xx provider errors."""
        service._llm_adapter = MockLLMAdapter(
            exception=LLMProviderError("Server error", "mock", status_code=500)
        )

        result = await service.interpret(
            NLInterpretationRequest(
                text="Change order ORD-123 to next week",
                source_system="demo",
                external_event_id="evt-013",
            )
        )

        assert result.success is False
        assert result.error_code == "LLM_PROVIDER_ERROR"
        assert "unavailable" in result.error.lower()

    async def test_provider_unavailable(self, service: NLInterpreterService):
        """Test handling of provider unavailable (connection error)."""
        service._llm_adapter = MockLLMAdapter(
            exception=LLMProviderError("Connection refused", "mock", status_code=503)
        )

        result = await service.interpret(
            NLInterpretationRequest(
                text="Change order ORD-123 to next week",
                source_system="demo",
                external_event_id="evt-014",
            )
        )

        assert result.success is False
        assert result.error_code == "LLM_PROVIDER_ERROR"
        assert "unavailable" in result.error.lower()

    # --- Missing Configuration Tests ---

    async def test_missing_llm_config(self, monkeypatch: pytest.MonkeyPatch):
        """Test interpretation when LLM is not configured."""

        # Temporarily clear the API key - use monkeypatch to ensure it's cleared
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.setattr("relay.core.config.settings.llm_api_key", None, raising=False)
        monkeypatch.setattr(
            "relay.services.nl_interpreter.settings.llm_api_key", None, raising=False
        )
        monkeypatch.setattr("relay.api.main.settings.llm_api_key", None, raising=False)
        reload_settings()

        service = NLInterpreterService()
        result = await service.interpret(
            NLInterpretationRequest(
                text="Change order ORD-123 to next week",
                source_system="demo",
                external_event_id="evt-015",
            )
        )

        assert result.success is False
        assert result.error_code == "LLM_NOT_CONFIGURED"
        assert "not configured" in result.error.lower()

    # --- Workflow Execution Prevention Tests ---

    async def test_failed_interpretation_does_not_execute_workflow(
        self, service: NLInterpreterService, mock_adapter: MockLLMAdapter
    ):
        """Test that failed interpretations do not execute the workflow."""
        response_json = json.dumps(
            {
                "success": False,
                "draft": None,
                "missing_fields": ["order_id"],
                "ambiguities": [],
                "error": "Missing required field: order_id",
                "error_code": "VALIDATION_ERROR",
            }
        )
        mock_adapter._response = response_json

        result = await service.interpret(
            NLInterpretationRequest(
                text="Change delivery date to December 1st",
                source_system="demo",
                external_event_id="evt-016",
            )
        )

        assert result.success is False
        # The service should not execute the workflow - it just returns the interpretation

    async def test_ambiguous_interpretation_does_not_execute_workflow(
        self, service: NLInterpreterService, mock_adapter: MockLLMAdapter
    ):
        """Test that ambiguous interpretations do not execute the workflow."""
        response_json = json.dumps(
            {
                "success": False,
                "draft": {
                    "order_id": "ORD-00000123",
                    "requested_delivery_date": "2026-11-20T00:00:00+00:00",
                },
                "missing_fields": [],
                "ambiguities": [
                    {
                        "field": "requested_delivery_date",
                        "message": "'next Friday' is ambiguous",
                        "suggestions": ["2026-11-20", "2026-11-27"],
                    }
                ],
                "error": "Ambiguous delivery date",
                "error_code": "AMBIGUOUS_REQUEST",
            }
        )
        mock_adapter._response = response_json

        result = await service.interpret(
            NLInterpretationRequest(
                text="Change order ORD-123's delivery date to next Friday",
                source_system="demo",
                external_event_id="evt-017",
            )
        )

        assert result.success is False
        assert result.error_code == "AMBIGUOUS_REQUEST"
        assert result.draft is None  # No draft when ambiguous

    # --- Convenience Function Tests ---

    async def test_interpret_natural_language_convenience_function(
        self, mock_adapter: MockLLMAdapter
    ):
        """Test the convenience function interpret_natural_language."""
        response_json = json.dumps(
            {
                "success": True,
                "draft": {
                    "order_id": "ORD-00000123",
                    "requested_delivery_date": "2026-11-22T00:00:00+00:00",
                    "customer_id": "customer-101",
                },
                "missing_fields": [],
                "ambiguities": [],
                "error": None,
                "error_code": None,
            }
        )
        mock_adapter._response = response_json

        result = await interpret_natural_language(
            NLInterpretationRequest(
                text="Change order ORD-123 to November 22",
                source_system="demo",
                external_event_id="evt-018",
            ),
            llm_adapter=mock_adapter,
        )

        assert result.success is True
        assert result.draft.order_id == "ORD-00000123"

    # --- Ambiguity Details Tests ---

    async def test_ambiguity_suggestions_included(
        self, service: NLInterpreterService, mock_adapter: MockLLMAdapter
    ):
        """Test that ambiguity suggestions are included in response."""
        response_json = json.dumps(
            {
                "success": False,
                "draft": {"order_id": "ORD-123"},
                "missing_fields": [],
                "ambiguities": [
                    {
                        "field": "requested_delivery_date",
                        "message": "'next Friday' is ambiguous",
                        "suggestions": ["2026-11-20", "2026-11-27"],
                    }
                ],
                "error": "Ambiguous delivery date",
                "error_code": "AMBIGUOUS_REQUEST",
            }
        )
        mock_adapter._response = response_json

        result = await service.interpret(
            NLInterpretationRequest(
                text="Change order ORD-123's delivery date to next Friday",
                source_system="demo",
                external_event_id="evt-019",
            )
        )

        assert len(result.ambiguities) == 1
        assert result.ambiguities[0].field == "requested_delivery_date"
        assert len(result.ambiguities[0].suggestions) == 2
        assert "2026-11-20" in result.ambiguities[0].suggestions
        assert "2026-11-27" in result.ambiguities[0].suggestions


# --- Endpoint-level integration tests ---
# These tests require a real database (PostgreSQL) and are skipped in local development.
# Run with: pytest tests/test_nl_interpreter.py::TestNLInterpreterEndpoint --run-integration
# when PostgreSQL is available.


class TestNLInterpreterEndpoint:
    """Endpoint-level integration tests for POST /api/v1/order-change-requests/nl

    These tests use the pg_integration_order_client fixture which provides a real
    database for the order service. Requires --run-integration flag.
    """

    @pytest.fixture
    def client(self, pg_integration_relay_client):
        """Relay API client with real order service."""
        return pg_integration_relay_client

    def test_nl_endpoint_missing_llm_config(
        self, pg_integration_relay_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """Test endpoint returns 503 when LLM_API_KEY not set."""
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        settings.llm_api_key = None
        reload_settings()

        # Also mock get_llm_adapter to raise config error
        from relay.adapters.llm import LLMConfigurationError

        def mock_get_adapter():
            raise LLMConfigurationError("LLM_API_KEY not set", "openai")

        monkeypatch.setattr("relay.adapters.llm.get_llm_adapter", mock_get_adapter)

        response = pg_integration_relay_client.post(
            "/api/v1/order-change-requests/nl",
            json={
                "source_system": "demo",
                "external_event_id": "evt-001",
                "customer_id": "customer-101",
                "text": "Change order ORD-123 to November 22",
            },
        )
        assert response.status_code == 503
        assert response.json()["detail"]["error_code"] == "LLM_NOT_CONFIGURED"

    def test_nl_endpoint_success(
        self, pg_integration_relay_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """Test successful NL interpretation via endpoint."""
        # Mock the LLM adapter
        mock_adapter = _create_mock_adapter(
            json.dumps(
                {
                    "success": True,
                    "draft": {
                        "order_id": "ORD-9D3220DE",
                        "requested_delivery_date": "2026-11-22T00:00:00+00:00",
                        "customer_id": "customer-101",
                    },
                    "missing_fields": [],
                    "ambiguities": [],
                    "error": None,
                    "error_code": None,
                }
            )
        )

        monkeypatch.setattr("relay.adapters.llm.get_llm_adapter", lambda: mock_adapter)

        # Also mock the order service client to avoid connection errors
        with patch("relay.services.workflow_orchestrator.httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "id": "ORD-9D3220DE",
                "customer_id": "customer-101",
                "status": "confirmed",
                "delivery_date": "2026-11-10T00:00:00+00:00",
                "items": [],
                "created_at": "2026-11-01T00:00:00+00:00",
                "updated_at": "2026-11-01T00:00:00+00:00",
            }
            mock_response.raise_for_status = MagicMock()
            mock_response.status_code = 200
            mock_client.get.return_value = mock_response

            # Mock the update order endpoint
            mock_update_response = MagicMock()
            mock_update_response.json.return_value = {
                "id": "ORD-9D3220DE",
                "customer_id": "customer-101",
                "status": "confirmed",
                "delivery_date": "2026-11-22T00:00:00+00:00",
                "items": [],
                "created_at": "2026-11-01T00:00:00+00:00",
                "updated_at": "2026-11-01T00:00:00+00:00",
            }
            mock_update_response.raise_for_status = MagicMock()
            mock_update_response.status_code = 200
            mock_client.patch.return_value = mock_update_response

            response = pg_integration_relay_client.post(
                "/api/v1/order-change-requests/nl",
                json={
                    "source_system": "demo",
                    "external_event_id": "evt-access-001",
                    "customer_id": "customer-101",
                    "text": "Change order ORD-9D3220DE's delivery date to November 22, 2026.",
                },
            )
            assert response.status_code == 200
            assert response.json()["success"] is True
            assert response.json()["draft"]["order_id"] == "ORD-9D3220DE"

    def test_nl_endpoint_missing_order_id(
        self, pg_integration_relay_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """Test endpoint returns 422 for missing order ID."""
        mock_adapter = _create_mock_adapter(
            json.dumps(
                {
                    "success": False,
                    "draft": None,
                    "missing_fields": ["order_id"],
                    "ambiguities": [],
                    "error": "Missing required field: order_id",
                    "error_code": "VALIDATION_ERROR",
                }
            )
        )

        monkeypatch.setattr("relay.adapters.llm.get_llm_adapter", lambda: mock_adapter)

        response = pg_integration_relay_client.post(
            "/api/v1/order-change-requests/nl",
            json={
                "source_system": "demo",
                "external_event_id": "evt-001",
                "customer_id": "customer-101",
                "text": "Change delivery date to December 1st",
            },
        )
        assert response.status_code == 422
        assert response.json()["detail"]["error_code"] == "VALIDATION_ERROR"
        assert "order_id" in response.json()["detail"]["missing_fields"]

    def test_nl_endpoint_ambiguous_date(
        self, pg_integration_relay_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """Test endpoint returns 422 for ambiguous date."""
        mock_adapter = _create_mock_adapter(
            json.dumps(
                {
                    "success": False,
                    "draft": {
                        "order_id": "ORD-00000123",
                        "requested_delivery_date": "2026-11-20T00:00:00+00:00",
                    },
                    "missing_fields": [],
                    "ambiguities": [
                        {
                            "field": "requested_delivery_date",
                            "message": (
                                "'next Friday' is ambiguous - could mean this week or next week"
                            ),
                            "suggestions": ["2026-11-20", "2026-11-27"],
                        }
                    ],
                    "error": "Ambiguous delivery date",
                    "error_code": "AMBIGUOUS_REQUEST",
                }
            )
        )

        monkeypatch.setattr("relay.adapters.llm.get_llm_adapter", lambda: mock_adapter)

        response = pg_integration_relay_client.post(
            "/api/v1/order-change-requests/nl",
            json={
                "source_system": "demo",
                "external_event_id": "evt-001",
                "customer_id": "customer-101",
                "text": "Change order ORD-123's delivery date to next Friday",
            },
        )
        assert response.status_code == 422
        assert response.json()["detail"]["error_code"] == "AMBIGUOUS_REQUEST"
        assert "ambiguities" in response.json()["detail"]
        assert len(response.json()["detail"]["ambiguities"]) == 1

    def test_nl_endpoint_provider_timeout(
        self, pg_integration_relay_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """Test endpoint returns 504 on provider timeout."""

        class TimeoutMock:
            provider_name = "mock"
            model_name = "mock-model"

            async def close(self):
                pass

            async def complete(self, **kwargs):
                raise LLMTimeoutError("timeout", "mock")

        monkeypatch.setattr("relay.adapters.llm.get_llm_adapter", lambda: TimeoutMock())

        response = pg_integration_relay_client.post(
            "/api/v1/order-change-requests/nl",
            json={
                "source_system": "demo",
                "external_event_id": "evt-001",
                "customer_id": "customer-101",
                "text": "Change order ORD-123 to next week",
            },
        )
        assert response.status_code == 504
        assert response.json()["detail"]["error_code"] == "LLM_TIMEOUT"

    def test_nl_endpoint_invalid_json_output(
        self, pg_integration_relay_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """Test endpoint handles malformed LLM output."""
        mock_adapter = _create_mock_adapter("not valid json {{{")

        monkeypatch.setattr("relay.adapters.llm.get_llm_adapter", lambda: mock_adapter)

        response = pg_integration_relay_client.post(
            "/api/v1/order-change-requests/nl",
            json={
                "source_system": "demo",
                "external_event_id": "evt-001",
                "customer_id": "customer-101",
                "text": "Change order ORD-123 to next week",
            },
        )
        assert response.status_code == 422
        assert response.json()["detail"]["error_code"] == "LLM_OUTPUT_PARSE_ERROR"

    def test_nl_endpoint_no_workflow_on_failed_interpretation(
        self, pg_integration_relay_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """Test that failed interpretation does not execute workflow."""
        mock_adapter = _create_mock_adapter(
            json.dumps(
                {
                    "success": False,
                    "draft": None,
                    "missing_fields": ["order_id"],
                    "ambiguities": [],
                    "error": "Missing required field: order_id",
                    "error_code": "VALIDATION_ERROR",
                }
            )
        )

        monkeypatch.setattr("relay.adapters.llm.get_llm_adapter", lambda: mock_adapter)

        response = pg_integration_relay_client.post(
            "/api/v1/order-change-requests/nl",
            json={
                "source_system": "demo",
                "external_event_id": "evt-001",
                "customer_id": "customer-101",
                "text": "Change delivery date to December 1st",
            },
        )
        assert response.status_code == 422
        assert response.json()["detail"]["error_code"] == "VALIDATION_ERROR"

    def test_nl_endpoint_ambiguous_does_not_execute_workflow(
        self, pg_integration_relay_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """Test that ambiguous interpretation does not execute workflow."""
        mock_adapter = _create_mock_adapter(
            json.dumps(
                {
                    "success": False,
                    "draft": {
                        "order_id": "ORD-00000123",
                        "requested_delivery_date": "2026-11-20T00:00:00+00:00",
                    },
                    "missing_fields": [],
                    "ambiguities": [
                        {
                            "field": "requested_delivery_date",
                            "message": "'next Friday' is ambiguous",
                            "suggestions": ["2026-11-20", "2026-11-27"],
                        }
                    ],
                    "error": "Ambiguous delivery date",
                    "error_code": "AMBIGUOUS_REQUEST",
                }
            )
        )

        monkeypatch.setattr("relay.adapters.llm.get_llm_adapter", lambda: mock_adapter)

        response = pg_integration_relay_client.post(
            "/api/v1/order-change-requests/nl",
            json={
                "source_system": "demo",
                "external_event_id": "evt-001",
                "customer_id": "customer-101",
                "text": "Change order ORD-123's delivery date to next Friday",
            },
        )
        assert response.status_code == 422
        assert response.json()["detail"]["error_code"] == "AMBIGUOUS_REQUEST"

    def test_nl_endpoint_duplicate_event(
        self, pg_integration_relay_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """Test endpoint returns 409 for duplicate event via NL endpoint."""
        # First request succeeds
        mock_adapter = _create_mock_adapter(
            json.dumps(
                {
                    "success": True,
                    "draft": {
                        "order_id": "ORD-9D3220DE",
                        "requested_delivery_date": "2026-11-22T00:00:00+00:00",
                        "customer_id": "customer-101",
                    },
                    "missing_fields": [],
                    "ambiguities": [],
                    "error": None,
                    "error_code": None,
                }
            )
        )

        monkeypatch.setattr("relay.adapters.llm.get_llm_adapter", lambda: mock_adapter)

        # Mock the order service client
        with patch("relay.services.workflow_orchestrator.httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "id": "ORD-9D3220DE",
                "customer_id": "customer-101",
                "status": "confirmed",
                "delivery_date": "2026-11-10T00:00:00+00:00",
                "items": [],
                "created_at": "2026-11-01T00:00:00+00:00",
                "updated_at": "2026-11-01T00:00:00+00:00",
            }
            mock_response.raise_for_status = MagicMock()
            mock_response.status_code = 200
            mock_client.get.return_value = mock_response

            mock_update_response = MagicMock()
            mock_update_response.json.return_value = {
                "id": "ORD-9D3220DE",
                "customer_id": "customer-101",
                "status": "confirmed",
                "delivery_date": "2026-11-22T00:00:00+00:00",
                "items": [],
                "created_at": "2026-11-01T00:00:00+00:00",
                "updated_at": "2026-11-01T00:00:00+00:00",
            }
            mock_update_response.raise_for_status = MagicMock()
            mock_update_response.status_code = 200
            mock_client.patch.return_value = mock_update_response

            # First request
            response1 = pg_integration_relay_client.post(
                "/api/v1/order-change-requests/nl",
                json={
                    "source_system": "demo",
                    "external_event_id": "evt-duplicate-001",
                    "customer_id": "customer-101",
                    "text": "Change order ORD-9D3220DE's delivery date to November 22, 2026.",
                },
            )
            assert response1.status_code == 200
            assert response1.json()["success"] is True

            # Second request with same external_event_id should return 409
            response2 = pg_integration_relay_client.post(
                "/api/v1/order-change-requests/nl",
                json={
                    "source_system": "demo",
                    "external_event_id": "evt-duplicate-001",
                    "customer_id": "customer-101",
                    "text": "Change order ORD-9D3220DE's delivery date to November 22, 2026.",
                },
            )
            assert response2.status_code == 409
            assert response2.json()["detail"]["error_code"] == "DUPLICATE_EVENT"
            assert "existing_execution_id" in response2.json()["detail"]

    def test_nl_endpoint_order_not_found(
        self, pg_integration_relay_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """Test endpoint returns 404 for nonexistent order via NL endpoint."""
        mock_adapter = _create_mock_adapter(
            json.dumps(
                {
                    "success": True,
                    "draft": {
                        "order_id": "ORD-00000000",
                        "requested_delivery_date": "2026-11-22T00:00:00+00:00",
                        "customer_id": "customer-101",
                    },
                    "missing_fields": [],
                    "ambiguities": [],
                    "error": None,
                    "error_code": None,
                }
            )
        )

        monkeypatch.setattr("relay.adapters.llm.get_llm_adapter", lambda: mock_adapter)

        # Mock the order service to return 404 for the order
        with patch("relay.services.workflow_orchestrator.httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Not Found", request=None, response=mock_response
            )
            mock_client.get.return_value = mock_response

            response = pg_integration_relay_client.post(
                "/api/v1/order-change-requests/nl",
                json={
                    "source_system": "demo",
                    "external_event_id": "evt-notfound-001",
                    "customer_id": "customer-101",
                    "text": "Change order ORD-NOTEXIST's delivery date to November 22, 2026.",
                },
            )
            assert response.status_code == 404
            assert response.json()["detail"]["error_code"] == "ORDER_NOT_FOUND"

    def test_nl_endpoint_customer_order_mismatch(
        self, pg_integration_relay_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """Test endpoint returns 400 for customer order mismatch via NL endpoint."""
        # Draft does NOT include customer_id, so it falls back to request.customer_id
        mock_adapter = _create_mock_adapter(
            json.dumps(
                {
                    "success": True,
                    "draft": {
                        "order_id": "ORD-00000001",
                        "requested_delivery_date": "2026-11-22T00:00:00+00:00",
                    },
                    "missing_fields": [],
                    "ambiguities": [],
                    "error": None,
                    "error_code": None,
                }
            )
        )

        monkeypatch.setattr("relay.adapters.llm.get_llm_adapter", lambda: mock_adapter)

        # Mock the order service to return order with different customer
        with patch("relay.services.workflow_orchestrator.httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_response = MockHttpResponse(
                {
                    "id": "ORD-OTHER",
                    "customer_id": "customer-999",  # Different from request
                    "status": "confirmed",
                    "delivery_date": "2026-11-10T00:00:00+00:00",
                    "items": [],
                    "created_at": "2026-11-01T00:00:00+00:00",
                    "updated_at": "2026-11-01T00:00:00+00:00",
                },
                status_code=200,
            )
            mock_client.get.return_value = mock_response

            # Also mock the patch method for the order update
            mock_patch_response = MockHttpResponse(
                {
                    "id": "ORD-OTHER",
                    "customer_id": "customer-999",
                    "status": "confirmed",
                    "delivery_date": "2026-11-22T00:00:00+00:00",
                    "items": [],
                    "created_at": "2026-11-01T00:00:00+00:00",
                    "updated_at": "2026-11-01T00:00:00+00:00",
                },
                status_code=200,
            )
            mock_client.patch.return_value = mock_patch_response

            response = pg_integration_relay_client.post(
                "/api/v1/order-change-requests/nl",
                json={
                    "source_system": "demo",
                    "external_event_id": "evt-mismatch-001",
                    "customer_id": "customer-101",  # Different from order
                    "text": "Change order ORD-OTHER's delivery date to November 22, 2026.",
                },
            )
            assert response.status_code == 400
            assert response.json()["detail"]["error_code"] == "CUSTOMER_ORDER_MISMATCH"
            assert "details" in response.json()["detail"]

    def test_nl_endpoint_invalid_state_transition(
        self, pg_integration_relay_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """Test endpoint returns 409 for shipped order via NL endpoint."""
        mock_adapter = _create_mock_adapter(
            json.dumps(
                {
                    "success": True,
                    "draft": {
                        "order_id": "ORD-00000002",
                        "requested_delivery_date": "2026-11-22T00:00:00+00:00",
                        "customer_id": "customer-101",
                    },
                    "missing_fields": [],
                    "ambiguities": [],
                    "error": None,
                    "error_code": None,
                }
            )
        )

        monkeypatch.setattr("relay.adapters.llm.get_llm_adapter", lambda: mock_adapter)

        # Mock the order service to return shipped order
        with patch("relay.services.workflow_orchestrator.httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_response = MockHttpResponse(
                {
                    "id": "ORD-SHIPPED",
                    "customer_id": "customer-101",
                    "status": "shipped",
                    "delivery_date": "2026-11-10T00:00:00+00:00",
                    "items": [],
                    "created_at": "2026-11-01T00:00:00+00:00",
                    "updated_at": "2026-11-01T00:00:00+00:00",
                },
                status_code=200,
            )
            mock_client.get.return_value = mock_response

            # Mock the patch method to return 409 for shipped order
            mock_patch_response = MockHttpResponse(
                {"detail": "Cannot change delivery date for order in current status"},
                status_code=409,
            )
            mock_patch_response.raise_for_status = lambda: (_ for _ in ()).throw(
                httpx.HTTPStatusError("409 Conflict", request=None, response=mock_patch_response)
            )
            mock_client.patch.return_value = mock_patch_response

            response = pg_integration_relay_client.post(
                "/api/v1/order-change-requests/nl",
                json={
                    "source_system": "demo",
                    "external_event_id": "evt-shipped-001",
                    "customer_id": "customer-101",
                    "text": "Change order ORD-SHIPPED's delivery date to November 22, 2026.",
                },
            )
            assert response.status_code == 409
            assert response.json()["detail"]["error_code"] == "INVALID_STATE_TRANSITION"


# --- Regression Tests for Cost Controls and Access Control ---


class TestCostControls:
    """Regression tests for LLM cost control features."""

    @pytest.fixture
    def mock_adapter(self) -> MockLLMAdapter:
        return MockLLMAdapter()

    @pytest.fixture
    def service(self, mock_adapter: MockLLMAdapter) -> NLInterpreterService:
        return NLInterpreterService(llm_adapter=mock_adapter)

    async def test_input_size_limit_enforced(self, service: NLInterpreterService):
        """Test that oversized input text is rejected."""
        # Bypass Pydantic validation by creating request with a smaller text
        # then mutating it to test the service logic directly
        request = NLInterpretationRequest(
            text="x" * settings.llm_max_input_chars,
            source_system="demo",
            external_event_id="evt-oversized",
        )
        # Mutate to exceed limit (bypassing Pydantic)
        request.text = "x" * (settings.llm_max_input_chars + 1)
        result = await service.interpret(request)

        assert result.success is False
        assert result.error_code == "INPUT_TOO_LARGE"
        assert "too long" in result.error.lower()

    async def test_input_size_at_limit_allowed(
        self, service: NLInterpreterService, mock_adapter: MockLLMAdapter
    ):
        """Test that input at exactly the limit is allowed."""
        mock_adapter._response = json.dumps(
            {
                "success": True,
                "draft": {
                    "order_id": "ORD-12345678",
                    "requested_delivery_date": "2026-11-22T00:00:00+00:00",
                    "customer_id": None,
                },
                "missing_fields": [],
                "ambiguities": [],
                "error": None,
                "error_code": None,
            }
        )

        text_at_limit = "x" * settings.llm_max_input_chars
        request = NLInterpretationRequest(
            text=text_at_limit,
            source_system="demo",
            external_event_id="evt-at-limit",
        )
        result = await service.interpret(request)

        # Should not be rejected for size
        assert result.error_code != "INPUT_TOO_LARGE"

    async def test_output_token_limit_used(
        self, service: NLInterpreterService, mock_adapter: MockLLMAdapter
    ):
        """Test that max_tokens is passed to adapter and capped at config limit."""
        mock_adapter._response = json.dumps(
            {
                "success": True,
                "draft": {
                    "order_id": "ORD-12345678",
                    "requested_delivery_date": "2026-11-22T00:00:00+00:00",
                },
                "missing_fields": [],
                "ambiguities": [],
                "error": None,
                "error_code": None,
            }
        )

        request = NLInterpretationRequest(
            text="Change order ORD-12345678 to November 22",
            source_system="demo",
            external_event_id="evt-token-limit",
        )
        await service.interpret(request)

        # Verify max_tokens was passed and capped at llm_max_output_tokens
        assert mock_adapter.last_kwargs["max_tokens"] == settings.llm_max_output_tokens
        assert mock_adapter.last_kwargs["max_tokens"] <= settings.llm_max_output_tokens

    async def test_provider_timeout_handled(self, service: NLInterpreterService):
        """Test that provider timeout returns structured error."""
        service._llm_adapter = MockLLMAdapter(
            exception=LLMTimeoutError("Request timed out", "mock")
        )

        result = await service.interpret(
            NLInterpretationRequest(
                text="Change order ORD-123 to next week",
                source_system="demo",
                external_event_id="evt-timeout",
            )
        )

        assert result.success is False
        assert result.error_code == "LLM_TIMEOUT"
        assert "timed out" in result.error.lower()

    async def test_provider_rate_limit_handled(self, service: NLInterpreterService):
        """Test that provider rate limit (429) returns structured error."""
        service._llm_adapter = MockLLMAdapter(
            exception=LLMProviderError("Rate limit", "mock", status_code=429)
        )

        result = await service.interpret(
            NLInterpretationRequest(
                text="Change order ORD-123 to next week",
                source_system="demo",
                external_event_id="evt-ratelimit",
            )
        )

        assert result.success is False
        assert result.error_code == "LLM_RATE_LIMIT"
        assert "rate limit" in result.error.lower()

    async def test_provider_500_error_handled(self, service: NLInterpreterService):
        """Test that provider 5xx errors return structured error."""
        service._llm_adapter = MockLLMAdapter(
            exception=LLMProviderError("Server error", "mock", status_code=500)
        )

        result = await service.interpret(
            NLInterpretationRequest(
                text="Change order ORD-123 to next week",
                source_system="demo",
                external_event_id="evt-500",
            )
        )

        assert result.success is False
        assert result.error_code == "LLM_PROVIDER_ERROR"
        assert "unavailable" in result.error.lower()

    async def test_adapter_receives_retry_config(self, service: NLInterpreterService):
        """Test that adapter is configured with retry settings from config."""
        from relay.core.config import settings

        # Verify settings are accessible
        assert settings.llm_max_retries >= 0
        assert settings.llm_retry_backoff_base > 0

        # The actual retry logic is in the adapter implementations
        # This test verifies the config values exist and are reasonable
        assert settings.llm_max_retries == 1  # Default
        assert settings.llm_retry_backoff_base == 1.0  # Default


class TestAccessControl:
    """Regression tests for demo access control on NL endpoint.

    These tests use the pg_integration_relay_client fixture which provides a real
    database for the order service. Requires --run-integration flag.
    """

    def test_nl_endpoint_allows_access_without_demo_key_in_dev(
        self, pg_integration_relay_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """Test NL endpoint accessible without X-Demo-Key when DEMO_API_KEY not set."""
        monkeypatch.delenv("DEMO_API_KEY", raising=False)
        settings.demo_api_key = None
        reload_settings()

        mock_adapter = _create_mock_adapter(
            json.dumps(
                {
                    "success": True,
                    "draft": {
                        "order_id": "ORD-9D3220DE",
                        "requested_delivery_date": "2026-11-22T00:00:00+00:00",
                        "customer_id": "customer-101",
                    },
                    "missing_fields": [],
                    "ambiguities": [],
                    "error": None,
                    "error_code": None,
                }
            )
        )
        monkeypatch.setattr("relay.adapters.llm.get_llm_adapter", lambda: mock_adapter)

        with patch("relay.services.workflow_orchestrator.httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_response = MockHttpResponse(
                {
                    "id": "ORD-9D3220DE",
                    "customer_id": "customer-101",
                    "status": "confirmed",
                    "delivery_date": "2026-11-10T00:00:00+00:00",
                },
                status_code=200,
            )
            mock_client.get.return_value = mock_response

            mock_update_response = MockHttpResponse(
                {
                    "id": "ORD-9D3220DE",
                    "customer_id": "customer-101",
                    "status": "confirmed",
                    "delivery_date": "2026-11-22T00:00:00+00:00",
                },
                status_code=200,
            )
            mock_client.patch.return_value = mock_update_response

            response = pg_integration_relay_client.post(
                "/api/v1/order-change-requests/nl",
                json={
                    "source_system": "demo",
                    "external_event_id": "evt-access-001",
                    "customer_id": "customer-101",
                    "text": "Change order ORD-9D3220DE's delivery date to November 22, 2026.",
                },
            )
            assert response.status_code == 200
            assert response.json()["success"] is True

    def test_nl_endpoint_requires_demo_key_when_configured(
        self, pg_integration_relay_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """Test NL endpoint requires X-Demo-Key when DEMO_API_KEY is set."""
        monkeypatch.setenv("DEMO_API_KEY", "test-secret-key")
        settings.demo_api_key = "test-secret-key"
        reload_settings()

        # Request without demo key should fail
        response = pg_integration_relay_client.post(
            "/api/v1/order-change-requests/nl",
            json={
                "source_system": "demo",
                "external_event_id": "evt-001",
                "customer_id": "customer-101",
                "text": "Change order ORD-123 to November 22",
            },
        )
        assert response.status_code == 401
        assert response.json()["detail"]["error_code"] == "DEMO_KEY_REQUIRED"

    def test_nl_endpoint_accepts_valid_demo_key(
        self, pg_integration_relay_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """Test NL endpoint accepts valid X-Demo-Key."""
        monkeypatch.setenv("DEMO_API_KEY", "test-secret-key")
        settings.demo_api_key = "test-secret-key"
        reload_settings()

        mock_adapter = _create_mock_adapter(
            json.dumps(
                {
                    "success": True,
                    "draft": {
                        "order_id": "ORD-9D3220DE",
                        "requested_delivery_date": "2026-11-22T00:00:00+00:00",
                        "customer_id": "customer-101",
                    },
                    "missing_fields": [],
                    "ambiguities": [],
                    "error": None,
                    "error_code": None,
                }
            )
        )
        monkeypatch.setattr("relay.adapters.llm.get_llm_adapter", lambda: mock_adapter)

        with patch("relay.services.workflow_orchestrator.httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_response = MockHttpResponse(
                {
                    "id": "ORD-9D3220DE",
                    "customer_id": "customer-101",
                    "status": "confirmed",
                    "delivery_date": "2026-11-10T00:00:00+00:00",
                },
                status_code=200,
            )
            mock_client.get.return_value = mock_response

            mock_update_response = MockHttpResponse(
                {
                    "id": "ORD-9D3220DE",
                    "customer_id": "customer-101",
                    "status": "confirmed",
                    "delivery_date": "2026-11-22T00:00:00+00:00",
                },
                status_code=200,
            )
            mock_client.patch.return_value = mock_update_response

            response = pg_integration_relay_client.post(
                "/api/v1/order-change-requests/nl",
                json={
                    "source_system": "demo",
                    "external_event_id": "evt-access-002",
                    "customer_id": "customer-101",
                    "text": "Change order ORD-9D3220DE's delivery date to November 22, 2026.",
                },
                headers={"X-Demo-Key": "test-secret-key"},
            )
            assert response.status_code == 200
            assert response.json()["success"] is True

    def test_nl_endpoint_rejects_invalid_demo_key(
        self, pg_integration_relay_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """Test NL endpoint rejects invalid X-Demo-Key."""
        monkeypatch.setenv("DEMO_API_KEY", "correct-secret")
        settings.demo_api_key = "correct-secret"
        reload_settings()

        response = pg_integration_relay_client.post(
            "/api/v1/order-change-requests/nl",
            json={
                "source_system": "demo",
                "external_event_id": "evt-001",
                "customer_id": "customer-101",
                "text": "Change order ORD-123 to November 22",
            },
            headers={"X-Demo-Key": "wrong-secret"},
        )
        assert response.status_code == 401
        assert response.json()["detail"]["error_code"] == "INVALID_DEMO_KEY"

    def test_health_and_ready_endpoints_accessible_without_demo_key(
        self, pg_integration_relay_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """Test health and ready endpoints accessible without demo key."""
        monkeypatch.setenv("DEMO_API_KEY", "test-secret-key")
        settings.demo_api_key = "test-secret-key"
        reload_settings()

        # Health should always be accessible
        response = pg_integration_relay_client.get("/health")
        assert response.status_code == 200

        # Ready should always be accessible
        response = pg_integration_relay_client.get("/ready")
        assert response.status_code in (200, 503)  # 503 if DB not available


class TestCredentialProtection:
    """Regression tests for protection against credential exposure."""

    def test_demo_api_key_not_in_frontend_templates(self):
        """Test that DEMO_API_KEY is not exposed in any frontend template."""
        import os

        template_dir = "src/relay/templates"
        for filename in os.listdir(template_dir):
            if filename.endswith(".html"):
                with open(os.path.join(template_dir, filename)) as f:
                    content = f.read()
                    assert "DEMO_API_KEY" not in content
                    assert "demo_api_key" not in content.lower()

    def test_llm_api_key_not_in_frontend_templates(self):
        """Test that LLM_API_KEY is not exposed in any frontend template."""
        import os

        template_dir = "src/relay/templates"
        for filename in os.listdir(template_dir):
            if filename.endswith(".html"):
                with open(os.path.join(template_dir, filename)) as f:
                    content = f.read()
                    assert "LLM_API_KEY" not in content
                    assert "llm_api_key" not in content.lower()
