"""Menu → PDF export: the menu card, the prep plan per day, a timeline per day, and
the plan by course.

Takes the payload ``GET /menus/{id}`` returns and reuses the recipe PDF's page
setup (A4, DejaVu fonts, footer, colours). The report has three parts:

* **The day before** (only when there are day-before steps): a run sheet and a
  landscape timeline of that day alone.
* **On the day**: a run sheet with the serving times placed between the steps,
  and a landscape timeline of the cooking day.
* **By course**: a timeline per course on its own time scale (the day before above
  the cooking day), so one person can take a dish.
* **Recipes** (optional): each course's recipe, scaled to the guests, one per page.

Run sheets list steps in time order with a tick box, so they work on the fridge
door. Timelines draw one row per step, grouped by course. Like
``frontend-react/src/lib/menuPlan.ts``, only oven clashes count and long
passive steps are cut off at the window's edge instead of stretching the day;
unlike the app, day-before steps never take a row on the cooking day's timeline.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Dict, List, Optional, Tuple

from fpdf.enums import XPos, YPos

from api.i18n import backend_text
from api.recipe_pdf import (
    ACCENT,
    FONT_FAMILY,
    MUTED,
    TEXT,
    PdfDocument,
    _format_date,
    _RecipePDF,
    draw_recipe,
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
DAY = 24 * 60
DAY_BEFORE = -1
ON_THE_DAY = 0

Label = Callable[..., str]


@dataclass
class MenuRecipe:
    """A course's recipe to print after the plan."""

    course: str
    doc: PdfDocument
    image_path: Optional[str] = None


def hhmm(minutes: int) -> str:
    m = minutes % DAY
    return f"{m // 60:02d}:{m % 60:02d}"


def duration_text(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} min"
    h, m = divmod(minutes, 60)
    return f"{h} h {m} min" if m else f"{h} h"


def step_start(step: Dict[str, Any], serve_by_course: Dict[int, int]) -> int:
    """Minutes from midnight of the step's own day."""
    if step["day"] == DAY_BEFORE:
        return step["at"] if step["at"] is not None else 18 * 60
    return serve_by_course[step["course_id"]] - step["lead"] - step["duration"]


def _on(step: Dict[str, Any], day: int) -> bool:
    return (step["day"] == DAY_BEFORE) == (day == DAY_BEFORE)


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
        (_Row(step_start(s, serve_by_course), step=s) for s in steps if s["day"] == DAY_BEFORE),
        key=lambda r: r.time,
    )
    day = [_Row(step_start(s, serve_by_course), step=s) for s in steps if s["day"] != DAY_BEFORE]
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


def render_menu_pdf(
    menu: Dict[str, Any],
    lang: str,
    today: Optional[date] = None,
    recipes: Optional[List[MenuRecipe]] = None,
) -> bytes:
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

    courses = _sorted_courses(menu)
    course_by_id = {c["id"]: c for c in courses}
    if courses:
        pdf.section(label("menu_courses"))
        for c in courses:
            pdf.ensure_space(12)
            course_heading(pdf, c, label)
            pdf.ln(2)

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

    def rows_out(rows: List[_Row]) -> None:
        for row in rows:
            if row.serve:
                serve_row(row)
            else:
                step_row(row)

    before, day = plan_rows(menu)
    split = bool(before)  # only split into two days when there is a day before at all
    landscape = False  # the last page is a timeline: the next part starts a new page

    def part(heading: str) -> None:
        nonlocal landscape
        if landscape:
            pdf.add_page()
            landscape = False
        pdf.section(heading)

    if before:
        part(label("day_before"))
        rows_out(before)
        landscape = _timeline_page(pdf, menu, label, DAY_BEFORE, label("day_before"))
    if day:
        part(label("on_the_day") if split else label("prep_plan"))
        rows_out(day)
        heading = label("on_the_day") if split else None
        landscape = _timeline_page(pdf, menu, label, ON_THE_DAY, heading) or landscape

    _by_course_pages(pdf, menu, label)
    for recipe in recipes or []:
        pdf.add_page()
        draw_recipe(pdf, recipe.doc, recipe.image_path, kicker=recipe.course)
    return bytes(pdf.output())


def course_heading(pdf: _RecipePDF, course: Dict[str, Any], label: Label) -> None:
    pdf.set_font(FONT_FAMILY, "B", 8.5)
    pdf.set_text_color(*ACCENT)
    pdf.cell(0, 4.5, sanitize(course["name"]).upper(), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.paragraph(sanitize(course["recipe_title"]), size=12, style="B")
    pdf.paragraph(label("served_at", time=hhmm(course["serve"])), size=9, color=MUTED)


# ---------------------------------------------------------------------------
# Timeline pages
# ---------------------------------------------------------------------------


@dataclass
class TimelineBar:
    step: Dict[str, Any]
    start: int
    end: int
    clipped: bool = False  # starts before the window: drawn cut off at the left edge
    cut: bool = False  # ends after the window: drawn cut off at the right edge


def _sorted_courses(menu: Dict[str, Any]) -> List[Dict[str, Any]]:
    return sorted(menu["courses"], key=lambda c: (c["position"], c["serve"], c["id"]))


def _live_steps(menu: Dict[str, Any], day: Optional[int] = None) -> List[Dict[str, Any]]:
    ids = {c["id"] for c in menu["courses"]}
    return [s for s in menu["steps"] if s["course_id"] in ids and (day is None or _on(s, day))]


def overnight_end(step: Dict[str, Any]) -> Optional[int]:
    """When a day-before step that runs overnight ends on the cooking day."""
    if step["day"] != DAY_BEFORE:
        return None
    end = step_start(step, {}) + step["duration"] - DAY
    return end if end > 0 else None


def _anchored(step: Dict[str, Any]) -> bool:
    """Steps that set the window; long passive ones are cut off instead."""
    return step["hands"] or step["duration"] <= LONG_PASSIVE


def day_window(menu: Dict[str, Any], earliest: Optional[int] = 17 * 60) -> Tuple[int, int]:
    """The cooking day's window; ``earliest`` keeps whole-menu timelines from starting late."""
    serve_by_course = {c["id"]: c["serve"] for c in menu["courses"]}
    day = _live_steps(menu, ON_THE_DAY)
    anchors = [step_start(s, serve_by_course) for s in day if _anchored(s)]
    serves = list(serve_by_course.values())
    lo = min(anchors + serves + ([earliest] if earliest is not None else [])) // 60 * 60
    ends = [step_start(s, serve_by_course) + s["duration"] for s in day]
    hi = max(ends + [m + 15 for m in serves] + [lo + 120])
    return lo, -(-hi // 30) * 30


def before_window(menu: Dict[str, Any]) -> Tuple[int, int]:
    """The day before runs from its first step to the end of the last short one."""
    steps = _live_steps(menu, DAY_BEFORE)
    starts = [step_start(s, {}) for s in steps]
    lo = min(starts + [DAY - 60]) // 60 * 60
    ends = [step_start(s, {}) + s["duration"] for s in steps if _anchored(s)]
    hi = max(ends + [m + 30 for m in starts] + [lo + 120])
    return lo, -(-hi // 30) * 30


def timeline_bars(
    menu: Dict[str, Any], day: int = ON_THE_DAY, window: Optional[Tuple[int, int]] = None
) -> List[TimelineBar]:
    """Bars for one day's timeline; day-before steps never show on the cooking day."""
    serve_by_course = {c["id"]: c["serve"] for c in menu["courses"]}
    if window is None:
        window = before_window(menu) if day == DAY_BEFORE else day_window(menu)
    lo, hi = window
    bars: List[TimelineBar] = []
    for s in _live_steps(menu, day):
        start = step_start(s, serve_by_course)
        end = start + s["duration"]
        if end > lo and start < hi:
            bars.append(
                TimelineBar(s, max(start, lo), min(end, hi), clipped=start < lo, cut=end > hi)
            )
    return bars


def oven_clashes(menu: Dict[str, Any], day: int = ON_THE_DAY) -> List[Tuple[int, int, int, int]]:
    """``(step_a, step_b, start, end)`` for oven steps that overlap at different temperatures."""
    serve_by_course = {c["id"]: c["serve"] for c in menu["courses"]}
    oven = [s for s in _live_steps(menu, day) if s["equipment"] == "oven"]
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


def _bar_text(menu: Dict[str, Any], bar: TimelineBar, label: Label) -> str:
    s = bar.step
    real_start = step_start(s, {c["id"]: c["serve"] for c in menu["courses"]})
    real_end = real_start + s["duration"]
    first = label("since", time=hhmm(real_start)) if bar.clipped else hhmm(real_start)
    if not bar.cut:
        last = hhmm(real_end)
    elif s["day"] == DAY_BEFORE and real_end > DAY:
        last = label("until_on_the_day", time=hhmm(real_end))
    else:
        last = label("until", time=hhmm(real_end))
    sep = " – " if bar.clipped or bar.cut else "–"
    return f"{first}{sep}{last}"


def _torn(pdf: _RecipePDF, x: float, y: float, h: float, right: bool) -> None:
    """Cut zigzag notches into the left (or right) edge of a bar at ``x``."""
    d = -1 if right else 1
    q = h / 4
    pdf.set_fill_color(255, 255, 255)
    pdf.polygon(
        [
            (x - 0.2 * d, y - 0.2),
            (x + 1.6 * d, y + q),
            (x, y + 2 * q),
            (x + 1.6 * d, y + 3 * q),
            (x - 0.2 * d, y + h + 0.2),
        ],
        style="F",
    )


def _course_colors(menu: Dict[str, Any]) -> Dict[int, Tuple[int, int, int]]:
    return {
        c["id"]: COURSE_COLORS[i % len(COURSE_COLORS)] for i, c in enumerate(_sorted_courses(menu))
    }


def _page_title(pdf: _RecipePDF, menu: Dict[str, Any], label: Label, heading: Optional[str]):
    pdf.add_page(orientation="L")
    pdf.set_auto_page_break(False)
    title = sanitize(menu.get("title") or "") or label("untitled_menu")
    parts = [title, label("timeline")] + ([heading] if heading else [])
    pdf.paragraph(" · ".join(parts), size=15, style="B")
    pdf.ln(3)


@dataclass
class _Drawn:
    bottom: float
    bars: List[TimelineBar]
    clashes: List[Tuple[int, int, int, int]]


def _chart(
    pdf: _RecipePDF,
    menu: Dict[str, Any],
    label: Label,
    day: int,
    window: Tuple[int, int],
    axis_y: float,
    row_h: float,
    caption: Optional[str] = None,
    course_rows: bool = True,
    oven_lane: bool = True,
    serve_labels: bool = True,
    color_of: Optional[Dict[int, Tuple[int, int, int]]] = None,
) -> _Drawn:
    """Draw one day of ``menu`` as a Gantt chart starting at ``axis_y``.

    ``course_rows`` puts a heading row above each course's steps; ``caption`` goes
    in the label column of the time axis; ``color_of`` defaults to ``menu``'s colours.
    """
    color_of = color_of or _course_colors(menu)
    bars = timeline_bars(menu, day, window)
    shown = {b.step["course_id"] for b in bars}
    courses = [c for c in _sorted_courses(menu) if c["id"] in shown]
    clashes = oven_clashes(menu, day)
    clashing = {i for a, b, _, _ in clashes for i in (a, b)}
    lo, hi = window
    span = hi - lo
    on_the_day = day != DAY_BEFORE

    label_w = 62.0
    x0 = pdf.l_margin
    track_x = x0 + label_w
    track_w = pdf.epw - label_w

    def px(m: float) -> float:
        return track_x + (m - lo) / span * track_w

    rows = (len(courses) if course_rows else 0) + len(bars)
    has_oven = oven_lane and any(b.step["equipment"] == "oven" for b in bars)
    top = axis_y + 5
    grid_bottom = top + rows * row_h + (8 if has_oven else 0)

    if caption:
        pdf.set_font(FONT_FAMILY, "B", 8)
        pdf.set_text_color(*TEXT)
        pdf.set_xy(x0 + 3, axis_y)
        pdf.cell(label_w - 4, 4, caption)

    # Axis + grid
    pdf.set_font(FONT_FAMILY, "", 7.5)
    pdf.set_text_color(*MUTED)
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
    if on_the_day:
        pdf.set_line_width(0.4)
        pdf.set_dash_pattern(dash=1.2, gap=0.9)
        for c in courses:
            pdf.set_draw_color(*color_of[c["id"]])
            x = px(c["serve"])
            pdf.line(x, top, x, grid_bottom)
        pdf.set_dash_pattern()
        pdf.set_font(FONT_FAMILY, "B", 7.5)
        for i, c in enumerate(courses if serve_labels else []):
            text = f"{hhmm(c['serve'])} {label('serve_course', course=sanitize(c['name']))}"
            w = pdf.get_string_width(text) + 2
            x = px(c["serve"])
            left = x - w - 0.8 if x + w > track_x + track_w else x + 0.8
            y = top + 0.6 + i * 3.6
            pdf.set_fill_color(255, 255, 255)
            pdf.rect(left, y, w, 3.4, style="F")
            pdf.set_text_color(*color_of[c["id"]])
            pdf.set_xy(left, y)
            pdf.cell(w, 3.4, text, align="C")

    # Rows
    y = top
    bar_h = row_h * 0.62
    for c in courses:
        color = color_of[c["id"]]
        if course_rows:
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
                _torn(pdf, bx, by, bar_h, right=False)
            if b.cut:  # torn right edge: goes on after the window
                _torn(pdf, bx + bw, by, bar_h, right=True)
            if s["id"] in clashing:
                pdf.set_draw_color(*CLASH)
                pdf.set_line_width(0.5)
                pdf.rect(bx - 0.4, by - 0.4, bw + 0.8, bar_h + 0.8, style="D")
            text = _bar_text(menu, b, label)
            pdf.set_font(FONT_FAMILY, "B" if s["hands"] else "", 6.5)
            tw = pdf.get_string_width(text) + 2
            pad = 1.5 if b.clipped else 0.5
            if tw <= bw - pad - (1.5 if b.cut else 0):
                pdf.set_text_color(*text_color)
                pdf.set_xy(bx + pad, by)
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

    return _Drawn(max(y, grid_bottom), bars, clashes)


def _legend(
    pdf: _RecipePDF,
    label: Label,
    y: float,
    bars: List[TimelineBar],
    clashes: List[Tuple[int, int, int, int]],
) -> None:
    x = pdf.l_margin
    pdf.set_font(FONT_FAMILY, "", 7.5)
    legend = [("solid", label("needs_you")), ("tint", label("runs_by_itself"))]
    if any(b.clipped for b in bars):
        legend.append(("torn", label("started_earlier")))
    if any(b.cut for b in bars):
        legend.append(("cut", label("continues_later")))
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
        elif kind in ("torn", "cut"):
            pdf.set_fill_color(*_tint(sample, 0.3))
            pdf.rect(x, y + 0.8, 6, 2.6, style="F")
            if kind == "torn":
                _torn(pdf, x, y + 0.8, 2.6, right=False)
            else:
                _torn(pdf, x + 6, y + 0.8, 2.6, right=True)
        else:
            pdf.set_fill_color(*_tint(CLASH, 0.3))
            pdf.set_draw_color(*CLASH)
            pdf.rect(x, y + 0.8, 6, 2.6, style="DF")
        pdf.set_text_color(*MUTED)
        pdf.set_xy(x + 7.5, y)
        w = pdf.get_string_width(text) + 2
        pdf.cell(w, 4.2, text)
        x += 7.5 + w + 5


def _timeline_page(
    pdf: _RecipePDF, menu: Dict[str, Any], label: Label, day: int, heading: Optional[str]
) -> bool:
    """Draw one day's timeline on a landscape page; ``False`` if there's nothing to draw."""
    bars = timeline_bars(menu, day)
    if not bars:
        return False
    window = before_window(menu) if day == DAY_BEFORE else day_window(menu)
    page_break = pdf.auto_page_break, pdf.b_margin
    _page_title(pdf, menu, label, heading)

    courses = {b.step["course_id"] for b in bars}
    has_oven = any(b.step["equipment"] == "oven" for b in bars)
    top = pdf.get_y() + 5
    room = pdf.h - pdf.b_margin - 12 - top - (8 if has_oven else 0)  # 12: the legend
    row_h = max(3.6, min(6.5, room / (len(courses) + len(bars))))

    drawn = _chart(pdf, menu, label, day, window, pdf.get_y(), row_h)
    _legend(pdf, label, drawn.bottom + 4, drawn.bars, drawn.clashes)
    pdf.set_auto_page_break(page_break[0], margin=page_break[1])
    return True


def _by_course_pages(pdf: _RecipePDF, menu: Dict[str, Any], label: Label) -> bool:
    """One timeline block per course, each on its own time scale: the day before
    (if the course has steps then) above the cooking day."""
    color_of = _course_colors(menu)
    blocks = []
    for c in _sorted_courses(menu):
        own = {**menu, "courses": [c]}
        days = [
            (d, w)
            for d, w in (
                (DAY_BEFORE, before_window(own)),
                (ON_THE_DAY, day_window(own, earliest=None)),
            )
            if timeline_bars(own, d, w)
        ]
        if days:
            blocks.append((c, own, days))
    if not blocks:
        return False

    page_break = pdf.auto_page_break, pdf.b_margin
    heading_h, axis_h, gap, legend_h = 8.0, 8.0, 7.0, 10.0
    bottom = pdf.h - pdf.b_margin - legend_h
    _page_title(pdf, menu, label, label("by_course"))
    page_top = pdf.get_y()
    all_bars: List[TimelineBar] = []
    all_clashes: List[Tuple[int, int, int, int]] = []

    for c, own, days in blocks:
        n_rows = sum(len(timeline_bars(own, d, w)) for d, w in days)
        fixed = heading_h + axis_h * len(days)
        row_h = 5.0
        if pdf.get_y() + fixed + n_rows * row_h > bottom and pdf.get_y() > page_top:
            _page_title(pdf, menu, label, label("by_course"))
        # A very long course gets squeezed onto one page.
        row_h = max(3.6, min(row_h, (bottom - pdf.get_y() - fixed) / max(n_rows, 1)))

        y = pdf.get_y()
        pdf.set_fill_color(*color_of[c["id"]])
        pdf.rect(pdf.l_margin, y + 1.6, 2.6, 2.6, style="F")
        pdf.set_xy(pdf.l_margin + 4, y)
        pdf.set_font(FONT_FAMILY, "B", 11)
        pdf.set_text_color(*TEXT)
        name = sanitize(c["name"])
        pdf.cell(pdf.get_string_width(name) + 2, 6, name)
        pdf.set_font(FONT_FAMILY, "", 9)
        pdf.set_text_color(*MUTED)
        detail = f"{sanitize(c['recipe_title'])} · {label('served_at', time=hhmm(c['serve']))}"
        pdf.cell(0, 6, detail)
        y += heading_h

        for d, w in days:
            caption = label("day_before") if d == DAY_BEFORE else label("on_the_day")
            drawn = _chart(
                pdf,
                own,
                label,
                d,
                w,
                y,
                row_h,
                caption,
                course_rows=False,
                oven_lane=False,
                serve_labels=False,
                color_of=color_of,
            )
            all_bars += drawn.bars
            all_clashes += drawn.clashes
            y = drawn.bottom + 3
        pdf.set_y(y + gap - 3)

    _legend(pdf, label, min(pdf.get_y(), bottom + 2), all_bars, all_clashes)
    pdf.set_auto_page_break(page_break[0], margin=page_break[1])
    return True
