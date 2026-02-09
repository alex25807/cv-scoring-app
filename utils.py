from urllib.parse import urlparse

def is_valid_url(url: str) -> bool:
    try:
        r = urlparse(url)
        return bool(r.scheme and r.netloc)
    except Exception:
        return False

def clamp_text(text: str, limit: int = 7000) -> str:
    return text[:limit] if text else ""
