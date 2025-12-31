from urllib.parse import urlparse
import html


def safe_url(url: str) -> str:
    """Return URL only if http/https and has netloc; else '#' to avoid JS schemes."""
    if not isinstance(url, str):
        return "#"
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return url
    return "#"


def sanitize_text(text: str, max_len: int = 300) -> str:
    """Escape HTML and strip Markdown-breaking brackets/parentheses; trim length."""
    if text is None:
        return ""
    # Basic normalization
    s = str(text).replace("\n", " ").replace("\r", " ")
    # Escape HTML entities
    s = html.escape(s, quote=True)
    # Remove markdown link control characters to prevent structural injection
    s = s.replace("[", "").replace("]", "").replace("(", "").replace(")", "")
    # Collapse excessive whitespace
    s = " ".join(s.split())
    # Truncate to reasonable length
    if len(s) > max_len:
        s = s[:max_len - 1] + "…"
    return s


def safe_markdown_link(title: str, url: str) -> str:
    """Produce a safe Markdown link using sanitized title and validated URL."""
    return f"[{sanitize_text(title)}]({safe_url(url)})"
