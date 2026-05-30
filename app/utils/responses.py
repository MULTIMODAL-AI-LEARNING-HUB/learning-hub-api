"""Response helpers."""

def ok(data: dict | list | None = None, message: str = "Success") -> dict:
    return {"data": data, "message": message}
