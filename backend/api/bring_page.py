"""The tiny public HTML pages Bring! fetches to import ingredients.

Bring reads the schema.org/Recipe JSON-LD in ``<script type="application/ld+json">``.
These pages are served from the app's own origin, where the SPA keeps its JWT,
so everything user-controlled is escaped:

- text in ``<title>``/``<h1>`` and the ``lang`` attribute goes through ``html.escape``;
- the JSON-LD has ``<``, ``>`` and ``&`` replaced with ``\\u`` escapes, so a recipe
  name containing ``</script>`` cannot end the script element (still valid JSON);
- the response carries a CSP that forbids running any script, plus ``nosniff``.
"""

import html
import json
import re
from typing import Any, Dict

from fastapi.responses import HTMLResponse

# The page is pure data: nothing on it may execute, load or be framed.
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}

_LANG_RE = re.compile(r"^[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*$")


def script_safe_json(data: Any) -> str:
    """JSON text that is safe inside a ``<script>`` element."""
    text = json.dumps(data, ensure_ascii=False)
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def recipe_page(name: str, jsonld: Dict[str, Any], lang: str = "en") -> HTMLResponse:
    """An HTML page carrying ``jsonld`` for Bring, titled ``name``."""
    safe_lang = lang if isinstance(lang, str) and _LANG_RE.match(lang) else "en"
    title = html.escape(name or "Recipe")
    body = (
        "<!DOCTYPE html>\n"
        f'<html lang="{safe_lang}">\n'
        "<head>\n"
        '  <meta charset="UTF-8">\n'
        f"  <title>{title}</title>\n"
        '  <script type="application/ld+json">\n'
        f"  {script_safe_json(jsonld)}\n"
        "  </script>\n"
        "</head>\n"
        "<body>\n"
        f"  <h1>{title}</h1>\n"
        "</body>\n"
        "</html>"
    )
    return HTMLResponse(content=body, headers=SECURITY_HEADERS)
