"""Menu → PDF export: the menu card, the prep plan as a run sheet, and a timeline.

Takes the payload ``GET /menus/{id}`` returns and reuses the recipe PDF's page
setup (A4, DejaVu fonts, footer, colours). Steps are listed in time order with a
tick box; serving times are placed between them, so it works on the fridge door.
A final landscape page draws the cooking day as a timeline, one row per step,
grouped by recipe. It mirrors ``frontend-react/src/lib/menuPlan.ts``: only oven
clashes count, and long passive or overnight steps are cut off at the left edge
instead of stretching the day back to the morning.
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

# Course colours in course order — same palette as the app (lib/menuPlan.ts).
COURSE_COLORS = [
    (217, 138, 28),
    (191, 86, 11),
    (111, 154, 69),
    (224, 107, 63),
    (147, 181, 108),
    (240, 138, 36),
]
LONG_PASSIVE = 180  # passive steps longer than this don't widen the timeline
GRID = (226, 232, 240)
CLASH = (220, 38, 38)


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

    _timeline_page(pdf, menu, label)
    return bytes(pdf.output())


# ---------------------------------------------------------------------------
# Timeline page
# ---------------------------------------------------------------------------


@dataclass
class TimelineBar:
    step: Dict[str, Any]
    start: int
    end: int
    clipped: bool  # starts before the window: drawn cut off at the left edge
    overnight: bool  # started the day before


def _sorted_courses(menu: Dict[str, Any]) -> List[Dict[str, Any]]:
    return sorted(menu["courses"], key=lambda c: (c["position"], c["serve"], c["id"]))


def _live_steps(menu: Dict[str, Any]) -> List[Dict[str, Any]]:
    ids = {c["id"] for c in menu["courses"]}
    return [s for s in menu["steps"] if s["course_id"] in ids]


def overnight_end(step: Dict[str, Any]) -> Optional[int]:
    """When a day-before step that runs overnight ends on the cooking day."""
    if step["day"] != -1:
        return None
    end = (step["at"] if step["at"] is not None else 18 * 60) + step["duration"] - 1440
    return end if end > 0 else None


def day_window(menu: Dict[str, Any]) -> Tuple[int, int]:
    serve_by_course = {c["id"]: c["serve"] for c in menu["courses"]}
    day = [s for s in _live_steps(menu) if s["day"] != -1]
    anchors = [
        step_start(s, serve_by_course) for s in day if s["hands"] or s["duration"] <= LONG_PASSIVE
    ]
    serves = list(serve_by_course.values())
    lo = min(anchors + serves + [17 * 60]) // 60 * 60
    ends = [step_start(s, serve_by_course) + s["duration"] for s in day]
    hi = max(ends + [m + 15 for m in serves] + [lo + 120])
    return lo, -(-hi // 30) * 30


def timeline_bars(menu: Dict[str, Any]) -> List[TimelineBar]:
    serve_by_course = {c["id"]: c["serve"] for c in menu["courses"]}
    lo, _ = day_window(menu)
    bars: List[TimelineBar] = []
    for s in _live_steps(menu):
        if s["day"] == -1:
            end = overnight_end(s)
            if end is not None and end > lo:
                bars.append(TimelineBar(s, lo, end, clipped=True, overnight=True))
            continue
        start = step_start(s, serve_by_course)
        end = start + s["duration"]
        if end > lo:
            bars.append(TimelineBar(s, max(start, lo), end, clipped=start < lo, overnight=False))
    return bars


def oven_clashes(menu: Dict[str, Any]) -> List[Tuple[int, int, int, int]]:
    """``(step_a, step_b, start, end)`` for oven steps that overlap at different temperatures."""
    serve_by_course = {c["id"]: c["serve"] for c in menu["courses"]}
    oven = [s for s in _live_steps(menu) if s["day"] != -1 and s["equipment"] == "oven"]
    out = []
    for i, a in enumerate(oven):
        for b in oven[i + 1 :]:
            a0, b0 = step_start(a, serve_by_course), step_start(b, serve_by_course)
            start, end = max(a0, b0), min(a0 + a["duration"], b0 + b["duration"])
            if end > start and a["temp"] != b["temp"]:
                out.append((a["id"], b["id"], start, end))
    return out


def _tint(color: Tuple[int, int, int], amount: float) -> Tuple[int, int, int]:
    """``color`` mixed with white; ``amount`` = share of the colour."""
    r, g, b = (round(c * amount + 255 * (1 - amount)) for c in color)
    return (r, g, b)


def _fit(pdf: _RecipePDF, text: str, width: float) -> str:
    if pdf.get_string_width(text) <= width:
        return text
    while text and pdf.get_string_width(text + "…") > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _timeline_page(pdf: _RecipePDF, menu: Dict[str, Any], label) -> None:
    courses = _sorted_courses(menu)
    bars = timeline_bars(menu)
    if not courses or not bars:
        return
    color_of = {c["id"]: COURSE_COLORS[i % len(COURSE_COLORS)] for i, c in enumerate(courses)}
    clashes = oven_clashes(menu)
    clashing = {i for a, b, _, _ in clashes for i in (a, b)}
    lo, hi = day_window(menu)
    span = hi - lo

    pdf.add_page(orientation="L")
    pdf.set_auto_page_break(False)
    title = sanitize(menu.get("title") or "") or label("untitled_menu")
    pdf.paragraph(f"{title} · {label('timeline')}", size=15, style="B")

    before = sorted(
        (s for s in _live_steps(menu) if s["day"] == -1),
        key=lambda s: s["at"] or 0,
    )
    if before:
        parts = []
        for s in before:
            text = f"{hhmm(s['at'] or 0)} {sanitize(s['name'])} ({duration_text(s['duration'])}"
            end = overnight_end(s)
            text += f", {label('until', time=hhmm(end))})" if end is not None else ")"
            parts.append(text)
        pdf.ln(1)
        pdf.paragraph(f"{label('day_before')}: " + "  ·  ".join(parts), size=8.5, color=MUTED)
    pdf.ln(3)

    label_w = 62.0
    x0 = pdf.l_margin
    track_x = x0 + label_w
    track_w = pdf.epw - label_w

    def px(m: float) -> float:
        return track_x + (m - lo) / span * track_w

    rows = sum(1 + sum(1 for b in bars if b.step["course_id"] == c["id"]) for c in courses)
    has_oven = any(b.step["equipment"] == "oven" for b in bars)
    axis_y = pdf.get_y()
    top = axis_y + 5
    bottom_limit = pdf.h - pdf.b_margin - 12  # room for the legend
    room = bottom_limit - top - (8 if has_oven else 0)
    row_h = max(3.6, min(6.5, room / max(rows, 1)))

    # Axis + grid
    pdf.set_font(FONT_FAMILY, "", 7.5)
    pdf.set_text_color(*MUTED)
    grid_bottom = top + rows * row_h + (8 if has_oven else 0)
    m = lo
    while m <= hi:
        pdf.set_draw_color(*GRID)
        pdf.set_line_width(0.25 if m % 60 == 0 else 0.1)
        pdf.line(px(m), top, px(m), grid_bottom)
        if m % 60 == 0:
            pdf.set_xy(px(m) - 6, axis_y)
            pdf.cell(12, 4, hhmm(m), align="C")
        m += 30

    # Serving times: dashed lines in the course colour, labels staggered.
    pdf.set_line_width(0.4)
    pdf.set_dash_pattern(dash=1.2, gap=0.9)
    for c in courses:
        color = color_of[c["id"]]
        pdf.set_draw_color(*color)
        x = px(c["serve"])
        pdf.line(x, top, x, grid_bottom)
    pdf.set_dash_pattern()
    pdf.set_font(FONT_FAMILY, "B", 7.5)
    for i, c in enumerate(courses):
        color = color_of[c["id"]]
        text = f"{hhmm(c['serve'])} {label('serve_course', course=sanitize(c['name']))}"
        w = pdf.get_string_width(text) + 2
        x = px(c["serve"])
        left = x - w - 0.8 if x + w > track_x + track_w else x + 0.8
        y = top + 0.6 + i * 3.6
        pdf.set_fill_color(255, 255, 255)
        pdf.rect(left, y, w, 3.4, style="F")
        pdf.set_text_color(*color)
        pdf.set_xy(left, y)
        pdf.cell(w, 3.4, text, align="C")

    # Rows
    y = top
    bar_h = row_h * 0.62
    for c in courses:
        color = color_of[c["id"]]
        pdf.set_fill_color(*color)
        pdf.rect(x0, y + row_h / 2 - 1, 2, 2, style="F")
        pdf.set_xy(x0 + 3, y)
        pdf.set_font(FONT_FAMILY, "B", 9)
        pdf.set_text_color(*TEXT)
        name = sanitize(c["name"])
        pdf.cell(pdf.get_string_width(name) + 1.5, row_h, name)
        pdf.set_font(FONT_FAMILY, "", 8)
        pdf.set_text_color(*MUTED)
        pdf.cell(
            label_w - 6 - pdf.get_string_width(name),
            row_h,
            _fit(pdf, sanitize(c["recipe_title"]), label_w - 8 - pdf.get_string_width(name)),
        )
        y += row_h
        for b in sorted(
            (b for b in bars if b.step["course_id"] == c["id"]), key=lambda b: (b.start, b.end)
        ):
            s = b.step
            pdf.set_font(FONT_FAMILY, "", 7.5)
            pdf.set_text_color(*TEXT)
            pdf.set_xy(x0 + 3, y)
            pdf.cell(label_w - 4, row_h, _fit(pdf, sanitize(s["name"]), label_w - 5))
            bx, bw = px(b.start), max(0.8, px(b.end) - px(b.start))
            by = y + (row_h - bar_h) / 2
            if s["hands"]:
                pdf.set_fill_color(*color)
                pdf.rect(bx, by, bw, bar_h, style="F")
                text_color = (255, 255, 255)
            else:
                pdf.set_fill_color(*_tint(color, 0.3))
                pdf.set_draw_color(*color)
                pdf.set_line_width(0.3)
                pdf.rect(bx, by, bw, bar_h, style="DF")
                text_color = TEXT
            if b.clipped:  # torn left edge: started earlier than shown
                pdf.set_fill_color(255, 255, 255)
                q = bar_h / 4  # zigzag notches cut into the left edge
                pdf.polygon(
                    [
                        (bx - 0.2, by - 0.2),
                        (bx + 1.6, by + q),
                        (bx, by + 2 * q),
                        (bx + 1.6, by + 3 * q),
                        (bx - 0.2, by + bar_h + 0.2),
                    ],
                    style="F",
                )
            if s["id"] in clashing:
                pdf.set_draw_color(*CLASH)
                pdf.set_line_width(0.5)
                pdf.rect(bx - 0.4, by - 0.4, bw + 0.8, bar_h + 0.8, style="D")
            if b.overnight:
                text = f"{label('since_day_before', time=hhmm(s['at'] or 0))} – {hhmm(b.end)}"
            elif b.clipped:
                text = f"{label('since', time=hhmm(_real_start(menu, s)))} – {hhmm(b.end)}"
            else:
                text = f"{hhmm(b.start)}–{hhmm(b.end)}"
            pdf.set_font(FONT_FAMILY, "B" if s["hands"] else "", 6.5)
            tw = pdf.get_string_width(text) + 2
            if tw <= bw - (1.5 if b.clipped else 0):
                pdf.set_text_color(*text_color)
                pdf.set_xy(bx + (1.5 if b.clipped else 0.5), by)
            else:
                pdf.set_text_color(*MUTED)
                right = bx + bw + 0.8
                # Near the right edge the label goes left of the bar instead.
                pdf.set_xy(right if right + tw <= track_x + track_w else bx - tw - 0.8, by)
            pdf.cell(tw, bar_h, text)
            y += row_h

    # Oven lane
    if has_oven:
        y += 2
        pdf.set_font(FONT_FAMILY, "B", 8)
        pdf.set_text_color(*TEXT)
        pdf.set_xy(x0 + 3, y)
        pdf.cell(label_w - 4, 5, label("oven_lane"))
        pdf.set_fill_color(248, 250, 252)
        pdf.rect(track_x, y, track_w, 5, style="F")
        for b in bars:
            if b.step["equipment"] != "oven":
                continue
            bx, bw = px(b.start), max(0.8, px(b.end) - px(b.start))
            pdf.set_fill_color(*_tint(color_of[b.step["course_id"]], 0.3))
            pdf.rect(bx, y + 1, bw, 3, style="F")
            pdf.set_font(FONT_FAMILY, "", 6)
            pdf.set_text_color(*TEXT)
            pdf.set_xy(bx + 0.5, y + 1)
            temp = f"{b.step['temp'] or 180}°"
            if pdf.get_string_width(temp) + 1 < bw:
                pdf.cell(bw - 1, 3, temp)
        for _, _, start, end in clashes:
            pdf.set_fill_color(*_tint(CLASH, 0.3))
            pdf.set_draw_color(*CLASH)
            pdf.set_line_width(0.3)
            pdf.rect(px(start), y + 0.4, px(end) - px(start), 4.2, style="DF")
        y += 5

    # Legend
    y = max(y + 4, grid_bottom + 4)
    x = x0
    pdf.set_font(FONT_FAMILY, "", 7.5)
    legend = [
        ("solid", label("needs_you")),
        ("tint", label("runs_by_itself")),
        ("torn", label("started_earlier")),
    ]
    if clashes:
        legend.append(("clash", label("oven_clash")))
    sample = COURSE_COLORS[1]
    for kind, text in legend:
        if kind == "solid":
            pdf.set_fill_color(*sample)
            pdf.rect(x, y + 0.8, 6, 2.6, style="F")
        elif kind == "tint":
            pdf.set_fill_color(*_tint(sample, 0.3))
            pdf.set_draw_color(*sample)
            pdf.set_line_width(0.3)
            pdf.rect(x, y + 0.8, 6, 2.6, style="DF")
        elif kind == "torn":
            pdf.set_fill_color(*_tint(sample, 0.3))
            pdf.rect(x, y + 0.8, 6, 2.6, style="F")
            pdf.set_fill_color(255, 255, 255)
            pdf.polygon(
                [
                    (x - 0.2, y + 0.6),
                    (x + 1.2, y + 1.45),
                    (x, y + 2.1),
                    (x + 1.2, y + 2.75),
                    (x - 0.2, y + 3.6),
                ],
                style="F",
            )
        else:
            pdf.set_fill_color(*_tint(CLASH, 0.3))
            pdf.set_draw_color(*CLASH)
            pdf.rect(x, y + 0.8, 6, 2.6, style="DF")
        pdf.set_text_color(*MUTED)
        pdf.set_xy(x + 7.5, y)
        w = pdf.get_string_width(text) + 2
        pdf.cell(w, 4.2, text)
        x += 7.5 + w + 5


def _real_start(menu: Dict[str, Any], step: Dict[str, Any]) -> int:
    return step_start(step, {c["id"]: c["serve"] for c in menu["courses"]})
