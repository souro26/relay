# Relay package
# Import app from api module when needed, not at package level
# to avoid circular imports

__all__ = ["app"]


def get_app():
    """Get the FastAPI application instance."""
    from relay.api.main import app

    return app
