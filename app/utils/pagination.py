"""Pagination helpers."""

def build_pagination(total: int, page: int, page_size: int) -> dict:
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
    }
