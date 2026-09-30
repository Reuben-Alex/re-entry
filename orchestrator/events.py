"""Pipeline event types for live dashboard streaming."""

from typing import Callable

EmitFn = Callable[..., None] | None


def emit(emitter: EmitFn, event_type: str, **data) -> None:
    """Emit a pipeline event if an emitter is configured."""
    if emitter is not None:
        emitter(event_type, **data)
