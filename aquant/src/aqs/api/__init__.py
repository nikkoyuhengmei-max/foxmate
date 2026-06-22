"""Local web API + dashboard (optional ``web`` extra)."""

__all__ = ["create_app"]


def create_app():
    from aqs.api.server import create_app as _create

    return _create()
