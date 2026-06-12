from datetime import datetime, UTC

def utc_now() -> datetime:
    """Returns a naive UTC datetime."""
    return datetime.now(UTC).replace(tzinfo=None)
