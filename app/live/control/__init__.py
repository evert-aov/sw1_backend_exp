from app.live.control.live_websocket_controller import live_router
from app.live.control.report_controller import report_router
from app.live.control.age_distribution_controller import age_distribution_router  # noqa: F401

__all__ = ["live_router", "report_router"]
