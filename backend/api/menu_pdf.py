"""Menu → PDF export: the menu card plus the prep plan as a printable run sheet.

Takes the payload ``GET /menus/{id}`` returns and reuses the recipe PDF's page
setup (A4, DejaVu fonts, footer, colours). Steps are listed in time order with a
tick box; serving times are placed between them, so it works on the fridge door.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from fpdf.enums import XPos, YPos

from api.i18n import backend_text
from api.recipe_pdf import (
    ACCENT,
    FONT_FAMILY,
    MUTED,
    RULE,
    TEXT,
    PdfDocument,
    _format_date,
    _RecipePDF,
    sanitize,
)

TIME_W = 14
BOX_W = 7
DUR_W = 22


def hhmm(minutes: int) -> str:
    m = minutes % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def duration_text(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} min"
    h, m = divmod(minutes, 60)
    return f"{h} h {m} min" if m else f"{h} h"


def step_start(step: Dict[str, Any], serve_by_course: Dict[int, int]) -> int:
    if step["day"] == -1:
        return step["at"] or 0
    return serve_by_course[step["course_id"]] - step["lead"] - step["duration"]


@dataclass
class _Row:
    time: int
    serve: Optional[Dict[str, Any]] = None  # a course being served
    step: Optional[Dict[str, Any]] = None


def plan_rows(menu: Dict[str, Any]) -> Tuple[List[_Row], List[_Row]]:
    """``(day_before, on_the_day)`` rows in time order; serving rows sort first on ties."""
    serve_by_course = {c["id"]: c["serve"] for c in menu["courses"]}
    steps = [s for s in menu["steps"] if s["course_id"] in serve_by_course]
    before = sorted(
        (_Row(step_start(s, serve_by_course), step=s) for s in steps if s["day"] == -1),
        key=lambda r: r.time,
    )
    day = [_Row(step_start(s, serve_by_course), step=s) for s in steps if s["day"] != -1]
    day += [_Row(c["serve"], serve=c) for c in menu["courses"]]
    day.sort(key=lambda r: (r.time, 0 if r.serve else 1))
    return before, day


def _date_label(iso: Optional[str], lang: str) -> str:
    if not iso:
        return ""
    try:
        return _format_date(date.fromisoformat(iso), lang)
    except ValueError:
        return ""


def render_menu_pdf(menu: Dict[str, Any], lang: str, today: Optional[date] = None) -> bytes:
    def label(key: str, **params: Any) -> str:
        return backend_text(lang, key, **params)

    title = sanitize(menu.get("title") or "") or label("untitled_menu")
    doc = PdfDocument(
        lang=lang,
        title=title,
        labels={},
        exported=label(
            "exported", app=label("app"), date=_format_date(today or date.today(), lang)
        ),
    )
    pdf = _RecipePDF(doc)
    pdf.add_page()

    pdf.paragraph(title, size=22, style="B")
    pdf.ln(1.5)
    meta = [
        m
        for m in (_date_label(menu.get("date"), lang), label("menu_guests", n=menu["guests"]))
        if m
    ]
    pdf.paragraph("  ·  ".join(meta), size=10, color=MUTED)

    courses = sorted(menu["courses"], key=lambda c: (c["position"], c["serve"]))
    course_by_id = {c["id"]: c for c in courses}
    if courses:
        pdf.section(label("menu_courses"))
        for c in courses:
            pdf.ensure_space(12)
            pdf.set_font(FONT_FAMILY, "B", 8.5)
            pdf.set_text_color(*ACCENT)
            pdf.cell(0, 4.5, sanitize(c["name"]).upper(), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.paragraph(sanitize(c["recipe_title"]), size=12, style="B")
            pdf.paragraph(label("served_at", time=hhmm(c["serve"])), size=9, color=MUTED)
            pdf.ln(2)

    before, day = plan_rows(menu)

    def step_row(row: _Row) -> None:
        step = row.step
        assert step is not None
        course = course_by_id[step["course_id"]]
        tags = [course["name"], label("needs_you") if step["hands"] else label("runs_by_itself")]
        if step["equipment"] == "oven":
            tags.append(label("oven", temp=step["temp"] or 180))
        elif step["equipment"] in ("stove", "fridge"):
            tags.append(label(step["equipment"]))
        name_w = pdf.epw - BOX_W - TIME_W - DUR_W
        pdf.set_font(FONT_FAMILY, "", 10.5)
        name = sanitize(step["name"])
        height = pdf.lines_needed(name_w, name) * 5 + 5
        pdf.ensure_space(height + 1.5)
        y = pdf.get_y()
        x = pdf.l_margin
        # Tick box
        pdf.set_draw_color(*MUTED)
        pdf.set_line_width(0.25)
        pdf.rect(x, y + 1, 3.2, 3.2)
        if step.get("done"):
            pdf.line(x + 0.6, y + 2.7, x + 1.4, y + 3.6)
            pdf.line(x + 1.4, y + 3.6, x + 2.8, y + 1.5)
        pdf.set_xy(x + BOX_W, y)
        pdf.set_font(FONT_FAMILY, "B", 10.5)
        pdf.set_text_color(*TEXT)
        pdf.cell(TIME_W, 5.2, hhmm(row.time))
        pdf.set_xy(x + BOX_W + TIME_W, y)
        pdf.set_font(FONT_FAMILY, "", 10.5)
        pdf.multi_cell(name_w, 5, name, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_x(x + BOX_W + TIME_W)
        pdf.set_font(FONT_FAMILY, "", 8.5)
        pdf.set_text_color(*MUTED)
        pdf.cell(name_w, 4.2, sanitize(" · ".join(tags)), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        end_y = pdf.get_y()
        pdf.set_xy(x + pdf.epw - DUR_W, y)
        pdf.set_font(FONT_FAMILY, "", 9.5)
        pdf.cell(DUR_W, 5.2, duration_text(step["duration"]), align="R")
        pdf.set_y(end_y + 1.5)

    def serve_row(row: _Row) -> None:
        course = row.serve
        assert course is not None
        pdf.ensure_space(9)
        y = pdf.get_y()
        pdf.set_fill_color(255, 241, 226)
        pdf.rect(pdf.l_margin, y, pdf.epw, 7, style="F")
        pdf.set_xy(pdf.l_margin + BOX_W, y + 0.9)
        pdf.set_font(FONT_FAMILY, "B", 10.5)
        pdf.set_text_color(*ACCENT)
        pdf.cell(TIME_W, 5.2, hhmm(row.time))
        text = f"{label('serve_course', course=course['name'])}: {course['recipe_title']}"
        pdf.cell(pdf.epw - BOX_W - TIME_W, 5.2, sanitize(text))
        pdf.set_y(y + 9)

    if before or day:
        pdf.section(label("prep_plan"))
    for heading, rows in ((label("day_before"), before), (label("on_the_day"), day)):
        if not rows:
            continue
        if before:  # only split into two days when there is a day before at all
            pdf.ensure_space(16)
            pdf.ln(1)
            pdf.set_font(FONT_FAMILY, "B", 9.5)
            pdf.set_text_color(*TEXT)
            pdf.cell(0, 5.5, heading, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_draw_color(*RULE)
            pdf.ln(1)
        for row in rows:
            if row.serve:
                serve_row(row)
            else:
                step_row(row)

    return bytes(pdf.output())
