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


class TestApplicationInitialization:
    def test_app_creates_successfully(self):
        from relay.api.main import app

        assert app is not None
        assert app.title == "Relay"
