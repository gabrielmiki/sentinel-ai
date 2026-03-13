"""
Tests for Celery application (api/tasks/celery_app.py).
"""

import os


class TestCeleryApp:
    """Test Celery application configuration."""

    def test_celery_app_exists(self) -> None:
        """Verify Celery app is created."""
        from api.tasks.celery_app import celery_app

        assert celery_app is not None
        assert celery_app.main == "sentinel-ai"

    def test_celery_broker_url(self) -> None:
        """Verify Celery broker URL is configured."""
        from api.tasks.celery_app import broker_url

        assert broker_url is not None
        # Should either be from env or default
        assert "redis://" in broker_url

    def test_celery_result_backend(self) -> None:
        """Verify Celery result backend is configured."""
        from api.tasks.celery_app import result_backend

        assert result_backend is not None
        # Should either be from env or default
        assert "redis://" in result_backend

    def test_celery_configuration(self) -> None:
        """Verify Celery app has correct configuration."""
        from api.tasks.celery_app import celery_app

        assert celery_app.conf.task_serializer == "json"
        assert celery_app.conf.accept_content == ["json"]
        assert celery_app.conf.result_serializer == "json"
        assert celery_app.conf.timezone == "UTC"
        assert celery_app.conf.enable_utc is True
        assert celery_app.conf.task_track_started is True
        assert celery_app.conf.task_time_limit == 30 * 60  # 30 minutes
        assert celery_app.conf.task_soft_time_limit == 25 * 60  # 25 minutes


class TestHealthCheckTask:
    """Test health check Celery task."""

    def test_health_check_task_exists(self) -> None:
        """Verify health_check_task is registered."""
        from api.tasks.celery_app import health_check_task

        assert health_check_task is not None
        assert hasattr(health_check_task, "name")
        assert health_check_task.name == "sentinel.health_check"

    def test_health_check_task_returns_correct_data(self) -> None:
        """Verify health_check_task returns expected data."""
        from api.tasks.celery_app import health_check_task

        result = health_check_task()

        assert isinstance(result, dict)
        assert result["status"] == "healthy"
        assert result["service"] == "celery-worker"

    def test_health_check_task_can_be_called_directly(self) -> None:
        """Verify health_check_task can be called as regular function."""
        from api.tasks.celery_app import health_check_task

        # Should be callable without Celery infrastructure
        result = health_check_task()
        assert result is not None


class TestCeleryEnvironmentConfiguration:
    """Test Celery environment variable configuration."""

    def test_broker_url_uses_environment_variable(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """Verify broker URL can be set via environment variable."""
        # Note: This test verifies the logic at import time
        test_broker = "redis://test-redis:6379/1"
        monkeypatch.setenv("CELERY_BROKER_URL", test_broker)

        # Re-import to get new environment value
        import importlib

        from api.tasks import celery_app as celery_module

        importlib.reload(celery_module)

        assert celery_module.broker_url == test_broker

    def test_result_backend_uses_environment_variable(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """Verify result backend can be set via environment variable."""
        test_backend = "redis://test-redis:6379/2"
        monkeypatch.setenv("CELERY_RESULT_BACKEND", test_backend)

        # Re-import to get new environment value
        import importlib

        from api.tasks import celery_app as celery_module

        importlib.reload(celery_module)

        assert celery_module.result_backend == test_backend
