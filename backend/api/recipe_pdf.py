"""Recipe → PDF export.

Two layers:

  - ``build_document(recipe, servings, lang)`` turns a localized recipe payload
    (the shape ``GET /recipes/{uuid}.json`` returns) into a plain ``PdfDocument``:
    labels in the right language, ingredient amounts scaled to the requested
    servings, each step with the ingredients it uses. Pure and unit-tested.
  - ``render_pdf(doc, image_path)`` lays that out on A4 with fpdf2 and returns
    the PDF bytes.

Text is set in DejaVu Sans, vendored as a subset in ``api/fonts/`` (Latin,
punctuation, fractions, common symbols). Characters outside the subset — emoji,
mostly — are approximated or dropped by ``sanitize`` instead of rendering as
empty boxes.

Servings scaling mirrors ``frontend-react/src/lib/scaling.ts`` so the PDF shows
the same amounts as the screen.
"""

import io
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from typing import Any, Dict, FrozenSet, List, Optional
from urllib.parse import quote, urlparse

from fpdf import FPDF
from fpdf.enums import MethodReturnValue, XPos, YPos

from api.i18n import backend_text
from api.translation import recipe_content

FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
FONT_FAMILY = "DejaVu"
FONT_FILES = {"": "DejaVuSans.ttf", "B": "DejaVuSans-Bold.ttf"}

# Layout (mm) and colours (RGB) — Zestry's orange accent on the app's neutral palette.
MARGIN = 18
ACCENT = (191, 86, 11)  # #bf560b, the UI primary
TEXT = (15, 23, 42)
MUTED = (100, 116, 139)
RULE = (248, 196, 140)  # #f8c48c, a light apricot
MAX_IMAGE_HEIGHT = 85
AMOUNT_COL = 28

# ---------------------------------------------------------------------------
# Servings scaling — a port of frontend-react/src/lib/scaling.ts
# ---------------------------------------------------------------------------

_FRACTIONS = [(1 / 4, "¼"), (1 / 3, "⅓"), (1 / 2, "½"), (2 / 3, "⅔"), (3 / 4, "¾")]
_NUMBER_RE = re.compile(r"(\d+)\s+(\d+)\s*/\s*(\d+)|(\d+)\s*/\s*(\d+)|(\d+(?:[.,]\d+)?)")


def parse_servings(recipe_yield: Optional[str]) -> int:
    """First integer in the yield ("4 servings" → 4); 4 when there is none."""
    m = re.search(r"\d+", recipe_yield or "")
    return int(m.group(0)) if m else 4


def servings_unit(recipe_yield: Optional[str], fallback: str) -> str:
    """The unit part of a yield ("4 servings" → "servings")."""
    if not recipe_yield:
        return fallback
    return re.sub(r"^\d+\s*", "", recipe_yield).strip() or fallback


def format_amount(n: float) -> str:
    """Readable number: unicode fractions for common values, else ≤1 decimal."""
    n = round(n * 100) / 100
    whole = int(n // 1)
    frac = n - whole
    for value, symbol in _FRACTIONS:
        if abs(frac - value) < 0.06:
            return f"{whole}{symbol}" if whole > 0 else symbol
    if frac < 0.05:
        return str(whole)
    fixed = round(n * 10) / 10
    return str(int(fixed)) if fixed % 1 == 0 else f"{fixed:.1f}"


def scale_text(text: str, factor: float) -> str:
    """Scale every number in ``text`` (ints, decimals, "1/2", "1 1/2") by ``factor``."""
    if abs(factor - 1) < 0.001:
        return text

    def repl(m: "re.Match[str]") -> str:
        mw, mn, md, fn, fd, num = m.groups()
        if mw is not None:
            value = int(mw) + int(mn) / int(md)
        elif fn is not None:
            value = int(fn) / int(fd)
        else:
            value = float(num.replace(",", "."))
        return format_amount(value * factor)

    return _NUMBER_RE.sub(repl, text)


# ---------------------------------------------------------------------------
# Text sanitising against the font subset
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _supported_codepoints() -> FrozenSet[int]:
    from fontTools.ttLib import TTFont

    font = TTFont(os.path.join(FONT_DIR, FONT_FILES[""]))
    cmap = font.getBestCmap() or {}
    return frozenset(cmap.keys())


def sanitize(text: Any) -> str:
    """Make ``text`` renderable with the font subset.

    Unsupported characters are replaced by their compatibility decomposition
    when that is renderable (e.g. "ﬃ" → "ffi"), otherwise dropped (emoji).
    Control characters other than newlines are removed.
    """
    supported = _supported_codepoints()
    out: List[str] = []
    for ch in str(text or ""):
        if ch == "\n":
            out.append(ch)
        elif ch == "\t":
            out.append(" ")
        elif ord(ch) in supported:
            out.append(ch)
        else:
            decomposed = unicodedata.normalize("NFKD", ch)
            out.extend(c for c in decomposed if ord(c) in supported)
    return re.sub(r"[ ]{2,}", " ", "".join(out)).strip()


# ---------------------------------------------------------------------------
# Document model
# ---------------------------------------------------------------------------


@dataclass
class PdfIngredient:
    amount: str
    name: str


@dataclass
class PdfStep:
    number: int
    text: str
    uses: List[str] = field(default_factory=list)


@dataclass
class PdfDocument:
    lang: str
    title: str
    labels: Dict[str, str]
    servings: Optional[str] = None
    source: Optional[str] = None
    description: str = ""
    tags: List[str] = field(default_factory=list)
    ingredients: List[PdfIngredient] = field(default_factory=list)
    steps: List[PdfStep] = field(default_factory=list)
    note: str = ""
    exported: str = ""


def _format_date(d: date, lang: str) -> str:
    return d.strftime("%d.%m.%Y") if lang == "de" else d.isoformat()


def build_document(
    recipe: Dict[str, Any],
    servings: Optional[int] = None,
    lang: Optional[str] = None,
    today: Optional[date] = None,
) -> PdfDocument:
    """Shape a localized recipe payload into the content of the PDF.

    ``servings`` scales every amount (and amounts mentioned in step
    ingredient lists) relative to the recipe's yield, like the servings
    selector in the app. ``lang`` picks the label language.
    """
    lang = lang or recipe.get("language") or "en"

    def label(key: str, **params: Any) -> str:
        return backend_text(lang, key, **params)

    content = recipe_content(recipe)  # also normalises old flat-format recipes
    recipe_yield = content.get("recipeYield") or ""
    base = parse_servings(recipe_yield)
    target = servings or base
    factor = target / base if base else 1.0

    ingredients = [
        PdfIngredient(
            amount=sanitize(scale_text(str(ing.get("amount") or ""), factor)),
            name=sanitize(ing.get("name") or ""),
        )
        for ing in content.get("ingredients") or []
    ]

    def uses(indices: List[int]) -> List[str]:
        out = []
        for idx in indices or []:
            if isinstance(idx, int) and 0 <= idx < len(ingredients):
                ing = ingredients[idx]
                out.append(f"{ing.amount} {ing.name}".strip())
        return out

    # Number after dropping blank steps so the numbering has no gaps.
    non_blank = [st for st in content.get("instructions") or [] if (st.get("text") or "").strip()]
    steps = [
        PdfStep(number=n, text=sanitize(st.get("text")), uses=uses(st.get("ingredients")))
        for n, st in enumerate(non_blank, start=1)
    ]

    source = None
    src = recipe.get("source") or {}
    if src.get("kind") == "url" and src.get("value"):
        host = urlparse(str(src["value"])).hostname or ""
        source = host[4:] if host.startswith("www.") else host or None

    show_servings = bool(recipe_yield) or servings is not None
    return PdfDocument(
        lang=lang,
        title=sanitize(content.get("name")) or label("untitled"),
        labels={
            k: label(k) for k in ("ingredients", "instructions", "note", "uses", "tags", "source")
        },
        servings=(
            sanitize(f"{target} {servings_unit(recipe_yield, label('servings'))}")
            if show_servings
            else None
        ),
        source=source,
        description=sanitize(content.get("description")),
        tags=[sanitize(t.get("name")) for t in recipe.get("tags") or [] if t.get("name")],
        ingredients=ingredients,
        steps=steps,
        note=sanitize(recipe.get("note")),
        exported=label(
            "exported", app=label("app"), date=_format_date(today or date.today(), lang)
        ),
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


class _RecipePDF(FPDF):
    def __init__(self, doc: PdfDocument):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.doc = doc
        self.set_margins(MARGIN, MARGIN, MARGIN)
        self.set_auto_page_break(auto=True, margin=MARGIN + 6)
        for style, filename in FONT_FILES.items():
            self.add_font(FONT_FAMILY, style, os.path.join(FONT_DIR, filename))
        self.set_title(doc.title)
        self.set_creator(backend_text(doc.lang, "app"))
        self.set_lang(doc.lang)

    def footer(self) -> None:
        self.set_y(-MARGIN)
        self.set_font(FONT_FAMILY, "", 8)
        self.set_text_color(*MUTED)
        self.cell(self.epw / 2, 5, self.doc.exported)
        self.cell(
            self.epw / 2,
            5,
            backend_text(self.doc.lang, "page", page=self.page_no(), pages="{nb}"),
            align="R",
        )

    # -- helpers -----------------------------------------------------------

    def lines_needed(self, width: float, text: str) -> int:
        lines = self.multi_cell(
            width, 5, text, align="L", dry_run=True, output=MethodReturnValue.LINES
        )
        # With output=LINES fpdf2 returns the wrapped lines as a list.
        return max(1, len(lines)) if isinstance(lines, list) else 1

    def ensure_space(self, height: float) -> None:
        if self.get_y() + height > self.page_break_trigger:
            self.add_page()

    def paragraph(self, text: str, size: float = 10.5, color=TEXT, style: str = "") -> None:
        self.set_font(FONT_FAMILY, style, size)
        self.set_text_color(*color)
        self.multi_cell(0, size * 0.5, text, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def section(self, title: str) -> None:
        # Keep a heading with at least a couple of lines of its content.
        self.ensure_space(22)
        self.ln(5)
        self.set_font(FONT_FAMILY, "B", 9)
        self.set_text_color(*ACCENT)
        self.cell(0, 6, title.upper(), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*RULE)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), self.l_margin + self.epw, self.get_y())
        self.ln(2.5)


def _hero_image(pdf: _RecipePDF, image_path: str) -> None:
    """Full text-width banner, centre-cropped to at most ``MAX_IMAGE_HEIGHT``."""
    from PIL import Image

    try:
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            width_px, height_px = img.size
            if not width_px or not height_px:
                return
            w = pdf.epw
            h = w * height_px / width_px
            if h > MAX_IMAGE_HEIGHT:
                # Too tall for the banner: crop the middle band instead of shrinking.
                h = MAX_IMAGE_HEIGHT
                keep = int(width_px * h / w)
                top = (height_px - keep) // 2
                img = img.crop((0, top, width_px, top + keep))
            # Embed as JPEG: a raw Pillow image would be stored losslessly and
            # make photo PDFs several MB.
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            buf.seek(0)
            pdf.image(buf, x=pdf.l_margin, y=pdf.get_y(), w=w, h=h)
    except Exception:
        return  # unreadable image: export without it rather than failing
    pdf.set_y(pdf.get_y() + h + 6)


def render_pdf(doc: PdfDocument, image_path: Optional[str] = None) -> bytes:
    """Lay out ``doc`` on A4 pages and return the PDF bytes."""
    pdf = _RecipePDF(doc)
    pdf.add_page()
    draw_recipe(pdf, doc, image_path)
    return bytes(pdf.output())


def draw_recipe(
    pdf: _RecipePDF,
    doc: PdfDocument,
    image_path: Optional[str] = None,
    kicker: Optional[str] = None,
) -> None:
    """Draw ``doc`` from the current position (e.g. a menu PDF's recipe pages).

    ``kicker`` is a small accent line above the title, such as the course name.
    """
    if image_path:
        _hero_image(pdf, image_path)

    if kicker:
        pdf.set_font(FONT_FAMILY, "B", 8.5)
        pdf.set_text_color(*ACCENT)
        pdf.cell(0, 4.5, sanitize(kicker).upper(), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Title + meta line
    pdf.paragraph(doc.title, size=22, style="B")
    pdf.ln(1.5)
    meta = [m for m in (doc.servings, doc.source) if m]
    if meta:
        pdf.paragraph("  ·  ".join(meta), size=10, color=MUTED)
    if doc.tags:
        pdf.paragraph(f"{doc.labels['tags']}: {', '.join(doc.tags)}", size=9, color=MUTED)
    if doc.description:
        pdf.ln(2)
        pdf.paragraph(doc.description, size=10.5, color=MUTED)

    # Ingredients: amount column + name column, rows kept whole across pages.
    if doc.ingredients:
        pdf.section(doc.labels["ingredients"])
        name_w = pdf.epw - AMOUNT_COL - 2
        for ing in doc.ingredients:
            pdf.set_font(FONT_FAMILY, "", 10.5)
            rows = max(pdf.lines_needed(AMOUNT_COL, ing.amount), pdf.lines_needed(name_w, ing.name))
            pdf.ensure_space(rows * 5 + 2)
            x, y = pdf.l_margin, pdf.get_y()
            pdf.set_font(FONT_FAMILY, "B", 10.5)
            pdf.set_text_color(*TEXT)
            pdf.set_xy(x, y)
            pdf.multi_cell(
                AMOUNT_COL, 5, ing.amount or "", align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT
            )
            pdf.set_font(FONT_FAMILY, "", 10.5)
            pdf.set_xy(x + AMOUNT_COL + 2, y)
            pdf.multi_cell(name_w, 5, ing.name, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_y(y + rows * 5 + 1.5)

    # Instructions: accent number, step text, then the ingredients it uses.
    if doc.steps:
        pdf.section(doc.labels["instructions"])
        indent = 9
        text_w = pdf.epw - indent
        for step in doc.steps:
            pdf.set_font(FONT_FAMILY, "", 10.5)
            uses_text = f"{doc.labels['uses']}: {', '.join(step.uses)}" if step.uses else ""
            needed = pdf.lines_needed(text_w, step.text) * 5.2
            if uses_text:
                pdf.set_font(FONT_FAMILY, "", 8.5)
                needed += pdf.lines_needed(text_w, uses_text) * 4.2
            pdf.ensure_space(min(needed + 3, 60))
            y = pdf.get_y()
            pdf.set_font(FONT_FAMILY, "B", 10.5)
            pdf.set_text_color(*ACCENT)
            pdf.set_xy(pdf.l_margin, y)
            pdf.cell(indent, 5.2, f"{step.number:02d}")
            pdf.set_font(FONT_FAMILY, "", 10.5)
            pdf.set_text_color(*TEXT)
            pdf.set_xy(pdf.l_margin + indent, y)
            pdf.multi_cell(text_w, 5.2, step.text, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            if uses_text:
                pdf.set_font(FONT_FAMILY, "", 8.5)
                pdf.set_text_color(*MUTED)
                pdf.set_x(pdf.l_margin + indent)
                pdf.multi_cell(
                    text_w, 4.2, uses_text, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT
                )
            pdf.ln(3)

    if doc.note:
        pdf.section(doc.labels["note"])
        pdf.paragraph(doc.note, size=10.5)


# ---------------------------------------------------------------------------
# File naming
# ---------------------------------------------------------------------------


def pdf_filename(title: str) -> str:
    """A filesystem-friendly ``<title>.pdf`` (keeps umlauts; strips separators)."""
    name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", " ", title or "").strip()
    name = re.sub(r"\s+", " ", name)[:80].strip(" .") or "recipe"
    return f"{name}.pdf"


def content_disposition(filename: str, disposition: str = "inline") -> str:
    """``Content-Disposition`` with an ASCII fallback and an RFC 5987 UTF-8 name."""
    ascii_name = (
        unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode().replace('"', "")
        or "recipe.pdf"
    )
    return f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
