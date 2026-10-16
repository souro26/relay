# Relay API package
# Import app from main module when needed, not at package level
# to avoid circular imports

__all__ = ["app"]


def get_app():
    """Get the FastAPI application instance."""
    from relay.api.main import app

    return app
