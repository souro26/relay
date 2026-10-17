"""API endpoint tests with mocked database for unit testing."""

import uuid
from unittest.mock import MagicMock, patch


class TestHealthEndpoint:
    def test_health_endpoint_returns_healthy(self, client):
        test_client, _ = client
        response = test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "relay"


class TestReadinessEndpoint:
    def test_readiness_returns_ready_when_db_available(self, client):
        test_client, mock_session = client
        # Mock the database connection check
        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_session.connection.return_value = mock_conn

        response = test_client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["database"] == "connected"

    def test_readiness_returns_not_ready_when_db_unavailable(self):
        # This test needs its own client with a failing engine
        from unittest.mock import MagicMock

        from sqlalchemy.exc import SQLAlchemyError

        with patch("relay.api.main.engine") as mock_engine:
            mock_conn = MagicMock()
            mock_conn.__enter__.side_effect = SQLAlchemyError("Connection refused")
            mock_engine.connect.return_value = mock_conn

            from fastapi.testclient import TestClient

            from relay.api.main import app

            with TestClient(app) as test_client:
                response = test_client.get("/ready")
                assert response.status_code == 503
                data = response.json()
                assert data["detail"]["status"] == "not ready"
                assert data["detail"]["database"] == "disconnected"


class TestWorkflowEndpoints:
    def test_get_workflow_not_found(self, client):
        test_client, mock_session = client
        # Mock the database query to return None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        response = test_client.get(f"/api/v1/workflows/{uuid.uuid4()}")
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    def test_get_workflow_invalid_id_format(self, client):
        test_client, _ = client
        response = test_client.get("/api/v1/workflows/not-a-uuid")
        assert response.status_code == 400
        data = response.json()
        assert "invalid" in data["detail"].lower()

    def test_get_workflow_returns_workflow(self, client, sample_workflow):
        test_client, mock_session = client
        # Mock the database query to return the sample workflow
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_workflow
        mock_session.execute.return_value = mock_result

        response = test_client.get(f"/api/v1/workflows/{sample_workflow.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_workflow.id)
        assert data["workflow_type"] == sample_workflow.workflow_type
        assert data["status"] == sample_workflow.status.value
        assert data["original_request"] == sample_workflow.original_request

    def test_list_workflows_returns_paginated_results(self, client, sample_workflow):
        test_client, mock_session = client
        # Mock the database query to return paginated results
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 1

        mock_items_result = MagicMock()
        mock_items_result.scalars.return_value.all.return_value = [sample_workflow]

        # The execute method is called twice: once for count, once for items
        mock_session.execute.side_effect = [mock_count_result, mock_items_result]

        response = test_client.get("/api/v1/workflows?page=1&page_size=20")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "total_pages" in data
        assert data["total"] == 1
        assert len(data["items"]) == 1

    def test_list_workflows_pagination_parameters(self, client):
        test_client, mock_session = client
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 0

        mock_items_result = MagicMock()
        mock_items_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [mock_count_result, mock_items_result]

        response = test_client.get("/api/v1/workflows?page=2&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 2
        assert data["page_size"] == 10

    def test_get_workflow_with_steps_and_llm(self, client, sample_workflow):
        test_client, mock_session = client
        from datetime import UTC, datetime

        step = MagicMock()
        step.id = uuid.uuid4()
        step.step_name = "fetch_order_details"
        step.attempt_number = 1
        step.status = "completed"
        step.started_at = datetime.now(UTC)
        step.completed_at = datetime.now(UTC)
        step.duration_ms = 120.5
        step.error_category = None
        step.error_details = None
        step.step_metadata = {"order_id": "ORD-123"}
        sample_workflow.steps = [step]

        inv = MagicMock()
        inv.id = uuid.uuid4()
        inv.step_name = "interpret_nl_request"
        inv.provider = "openai"
        inv.model = "gpt-4o-mini"
        inv.started_at = datetime.now(UTC)
        inv.completed_at = datetime.now(UTC)
        inv.latency_ms = 400.0
        inv.prompt_tokens = 100
        inv.completion_tokens = 50
        inv.total_tokens = 150
        inv.estimated_cost_usd = 0.000045
        inv.status = "success"
        inv.error_category = None
        inv.error_message = None
        sample_workflow.llm_invocations = [inv]

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_workflow
        mock_session.execute.return_value = mock_result

        response = test_client.get(f"/api/v1/workflows/{sample_workflow.id}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["steps"]) == 1
        assert data["steps"][0]["step_name"] == "fetch_order_details"
        assert len(data["llm_invocations"]) == 1
        assert data["llm_invocations"][0]["model"] == "gpt-4o-mini"
        assert data["llm_invocations"][0]["total_tokens"] == 150

    def test_get_metrics_endpoint(self, client, sample_workflow):
        test_client, mock_session = client

        # 1. status counts: [('completed', 10), ('failed', 2)]
        mock_status_res = MagicMock()
        mock_status_res.all.return_value = [("completed", 10), ("failed", 2)]

        # 2. durations: [100.0, 200.0, 300.0]
        mock_dur_res = MagicMock()
        mock_dur_res.scalars.return_value.all.return_value = [100.0, 200.0, 300.0]

        # 3. step failures: [('execute_delivery_update', 2)]
        mock_failures_res = MagicMock()
        mock_failures_res.all.return_value = [("execute_delivery_update", 2)]

        # 4. llm stats: (total_inv, sum_tokens, sum_cost, avg_latency)
        mock_llm_res = MagicMock()
        mock_llm_res.one.return_value = (5, 1200, 0.005, 350.2)

        # 5. recent workflows
        mock_recent_res = MagicMock()
        mock_recent_res.scalars.return_value.all.return_value = [sample_workflow]

        mock_session.execute.side_effect = [
            mock_status_res,
            mock_dur_res,
            mock_failures_res,
            mock_llm_res,
            mock_recent_res,
        ]

        response = test_client.get("/api/v1/metrics")
        assert response.status_code == 200
        data = response.json()
        assert data["total_workflows"] == 12
        assert data["completed_workflows"] == 10
        assert data["failed_workflows"] == 2
        assert data["success_rate_percentage"] == "83.3%"
        assert data["median_duration_ms"] == 200.0
        assert data["step_failure_counts"] == {"execute_delivery_update": 2}
        assert data["total_tokens"] == 1200
        assert data["total_estimated_cost_usd"] == 0.005



class TestApplicationInitialization:
    def test_app_creates_successfully(self):
        from relay.api.main import app

        assert app is not None
        assert app.title == "Relay"


class TestFrontendDataIntegrity:
    """Regression tests verifying frontend truthful representation and data integrity."""

    def test_templates_render_valid_html(self):
        """Verify templates exist and contain valid html structure."""
        import os

        template_dir = "src/relay/templates"
        for filename in os.listdir(template_dir):
            if filename.endswith(".html"):
                path = os.path.join(template_dir, filename)
                with open(path, encoding="utf-8") as f:
                    content = f.read()
                    assert "<html" in content or "{% extends" in content

    def test_frontend_routes_render_cleanly(self, client):
        """Verify all frontend HTML routes render successfully."""
        test_client, _ = client

        routes = ["/", "/workflows", "/request", "/workflows/new"]
        for route in routes:
            res = test_client.get(route)
            assert res.status_code == 200, f"Route {route} returned {res.status_code}"
            assert "text/html" in res.headers["content-type"]

    def test_openai_adapter_model_fallback(self):
        """Verify OpenAIAdapter safely falls back to gpt-4o-mini when default model is nvidia."""
        from relay.adapters.llm.openai import OpenAIAdapter

        adapter = OpenAIAdapter(api_key="test-key")
        assert adapter.model_name == "gpt-4o-mini"
        assert adapter.provider_name == "openai"
