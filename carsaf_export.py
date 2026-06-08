"""ISUBÜ çarşaf ders programı PDF dışa aktarma (faculty master grid)."""
from __future__ import annotations

import io
import re
from collections import defaultdict
from html import escape
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A2, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

from obs_export import _parse_hour_from_saat, parse_class_section
from scheduler import (
    DAYS,
    HOUR_TO_SLOT_INDEX,
    TIME_SLOTS,
    carsaf_include_class,
    format_slot_label,
    row_is_elective,
)

CARSaf_TIME_SLOTS = TIME_SLOTS
HOUR_TO_SLOT = HOUR_TO_SLOT_INDEX

HEADER_GREY = colors.HexColor("#D9D9D9")
GRID_COLOR = colors.black
N_GRADES = 4
N_TIME_SLOTS = len(CARSaf_TIME_SLOTS)
N_COLS = 2 + N_GRADES * 2
HEADER_ROWS = 3
GRADE_LABELS = ["1. Sınıf", "2. Sınıf", "3. Sınıf", "4. Sınıf"]
MAX_COURSE_CHARS = 40

DEFAULT_TITLE = (
    "ISUBÜ TEKNOLOJİ FAKÜLTESİ BİLGİSAYAR MÜHENDİSLİĞİ BÖLÜMÜ "
    "2025-2026 EĞİTİM ÖĞRETİM YILI GÜZ DÖNEMİ DERS PROGRAMI"
)

CARSaf_PDF_FILENAME = "çarşaf program.pdf"
# Geniş tek sayfa: A2 yatay genişlik, yükseklik tabloya göre (günler ayrı sayfaya bölünmez)
PAGE_WIDTH, _ = landscape(A2)
MARGIN_TOP = 8 * mm
MARGIN_BOTTOM = 8 * mm
MARGIN_LR = 10 * mm
BODY_ROW_MM = 6.0


def _register_fonts() -> Tuple[str, str]:
    regular_candidates = [
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\ARIAL.TTF",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    bold_candidates = [
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\ARIALBD.TTF",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    reg_name, bold_name = "Helvetica", "Helvetica-Bold"
    for path in regular_candidates:
        try:
            pdfmetrics.registerFont(TTFont("CarsafReg", path))
            reg_name = "CarsafReg"
            break
        except Exception:
            continue
    for path in bold_candidates:
        try:
            pdfmetrics.registerFont(TTFont("CarsafBold", path))
            bold_name = "CarsafBold"
            break
        except Exception:
            continue
    if reg_name == "CarsafReg" and bold_name == "Helvetica-Bold":
        bold_name = "CarsafReg"
    return reg_name, bold_name


def _grade_from_class(class_name: str) -> Optional[int]:
    sinif, _ = parse_class_section(class_name)
    compact = re.sub(r"\s+", "", sinif)
    m = re.search(r"(\d+)", compact)
    if not m:
        m = re.search(r"(\d+)", str(class_name))
    if not m:
        return None
    g = int(m.group(1))
    return g if 1 <= g <= N_GRADES else None


def _room_number(room: str) -> str:
    room = str(room or "").strip()
    if not room:
        return ""
    if room.upper() == "ONLINE":
        return "ONLINE"
    m = re.search(r"(\d{2,4})", room)
    return m.group(1) if m else room


def _shorten(text: str, limit: int = MAX_COURSE_CHARS) -> str:
    text = re.sub(r"\s+", " ", str(text or "").strip())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _format_course_label(name: str, code: str) -> str:
    name = re.sub(r"\s*\(Laboratuvar\)\s*$", "", str(name or "").strip(), flags=re.I)
    code = str(code or "").strip()
    if not name:
        return _shorten(code)
    return _shorten(name)


def _vertical_day_label(day: str) -> str:
    return "\n".join(list(day.upper()))


def _slot_label(idx: int) -> str:
    return format_slot_label(idx).replace(" - ", "-\n")


def _hour_to_slot(hour: int) -> Optional[int]:
    return HOUR_TO_SLOT.get(hour)


def _para_height(para: Paragraph, width_pt: float) -> float:
    _w, h = para.wrap(max(10, width_pt - 6), 10000)
    return h + 6


def _entry_cell_html(name: str, is_red: bool, *, elective: bool = False) -> str:
    if elective:
        return (
            f'<font color="#005A8C"><i>{escape(_shorten(name, 36))}</i></font>'
        )
    color = "#CC0000" if is_red else "#000000"
    return f'<font color="{color}"><b>{escape(_shorten(name, 40))}</b></font>'


def _combined_course_html(entries: Dict[str, Dict[str, Any]]) -> str:
    """A/B zorunlu (siyah/kırmızı); paralel seçmeliler mavi italik (E0, E1, …)."""
    parts: List[str] = []
    for sube in ("A", "B"):
        entry = entries.get(sube)
        if entry:
            parts.append(_entry_cell_html(entry.get("name", ""), sube == "B"))
    for ek in sorted(k for k in entries if str(k).startswith("E")):
        entry = entries[ek]
        if entry:
            parts.append(_entry_cell_html(entry.get("name", ""), False, elective=True))
    return "<br/>".join(parts)


def _combined_room_html(entries: Dict[str, Dict[str, Any]]) -> str:
    parts: List[str] = []
    for sube in ("A", "B"):
        entry = entries.get(sube)
        if not entry:
            continue
        room = str(entry.get("room", "")).strip() or ""
        color = "#CC0000" if sube == "B" else "#000000"
        parts.append(f'<font color="{color}">{escape(room)}</font>')
    for ek in sorted(k for k in entries if str(k).startswith("E")):
        entry = entries[ek]
        if not entry:
            continue
        room = str(entry.get("room", "")).strip() or ""
        parts.append(f'<font color="#005A8C">{escape(room)}</font>')
    return "<br/>".join(parts)


def _course_paragraph(entries: Dict[str, Dict[str, Any]], style: ParagraphStyle) -> Paragraph:
    return Paragraph(_combined_course_html(entries), style)


def _room_paragraph(entries: Dict[str, Dict[str, Any]], style: ParagraphStyle) -> Paragraph:
    return Paragraph(_combined_room_html(entries), style)


def _elective_codes_from_courses(courses_df: Optional[pd.DataFrame]) -> set:
    codes: set = set()
    if courses_df is None or courses_df.empty:
        return codes
    code_col = "code" if "code" in courses_df.columns else ("Kod" if "Kod" in courses_df.columns else None)
    type_col = "course_type" if "course_type" in courses_df.columns else ("Tür" if "Tür" in courses_df.columns else None)
    if not code_col:
        return codes
    for _, r in courses_df.iterrows():
        code = str(r.get(code_col, "")).strip()
        if not code:
            continue
        tur = str(r.get(type_col, "")).strip().lower() if type_col else ""
        dept = str(r.get("department", r.get("Departman", ""))).strip().lower()
        if tur in ("seçimlik", "secimlik", "elective", "s") or "seçimlik" in dept or dept == "üos seçmeli":
            codes.add(code)
    return codes


def _build_slot_map(
    schedule_df: pd.DataFrame,
    courses_df: Optional[pd.DataFrame] = None,
) -> Dict[Tuple[str, int, int], Dict[str, Dict[str, Any]]]:
    """
    (gün, saat_dilimi, sınıf_seviyesi) -> {'A','B': zorunlu; 'E0','E1': paralel seçmeli}.
    Sınıf adı 3.Sınıf / 4.Sınıf vb. sınıf seviyesine map edilir (A/B yoksa E* anahtarı).
    """
    slot_map: Dict[Tuple[str, int, int], Dict[str, Dict[str, Any]]] = defaultdict(dict)
    seen: Dict[Tuple[str, int, int, str], set] = defaultdict(set)
    elective_codes = _elective_codes_from_courses(courses_df)

    if schedule_df is None or schedule_df.empty:
        return slot_map

    for _, row in schedule_df.iterrows():
        day = str(row.get("Gün", "")).strip()
        if day not in DAYS:
            continue
        hour = _parse_hour_from_saat(row.get("Saat"))
        if hour is None:
            continue
        si = _hour_to_slot(hour)
        if si is None:
            continue
        cls = str(row.get("Sınıf", "")).strip()
        if not cls:
            continue
        code = str(row.get("Kod", "")).strip()
        elective = row_is_elective(
            departman=str(row.get("Departman", "")),
            tur=str(row.get("Tür", "")),
            code=code,
            elective_codes=elective_codes,
        )
        if not carsaf_include_class(cls, elective):
            continue
        grade = _grade_from_class(cls)
        if grade is None:
            continue
        key = (day, si, grade)
        if elective:
            n_e = sum(1 for k in slot_map[key] if str(k).startswith("E"))
            sube = f"E{n_e}"
        else:
            _, sube = parse_class_section(cls)
            if sube not in ("A", "B"):
                sube = "A"
        teacher = str(row.get("Öğretim Elemanı", row.get("Hoca", ""))).strip().split(" || ")[0]
        dedupe_key = (day, si, grade, sube)
        dedupe = (code, cls)
        if dedupe in seen[dedupe_key]:
            continue
        seen[dedupe_key].add(dedupe)
        slot_map[key][sube] = {
            "day": day,
            "slot_idx": si,
            "grade": grade,
            "class_name": cls,
            "code": code,
            "name": _format_course_label(str(row.get("Ders", "")), code),
            "teacher": teacher,
            "room": _room_number(str(row.get("Room", "") or "")),
            "is_red": sube == "B",
            "is_elective": elective,
        }

    return slot_map


def _build_body_layout(
    slot_map: Dict[Tuple[str, int, int], Dict[str, Dict[str, Any]]],
) -> Tuple[List[Dict[str, Any]], List[Tuple[int, int, int, int]]]:
    """
    Sabit ızgara: her (gün, saat) tek satır; seçmeliler A/B ile aynı hücrede (mavi).
    """
    body_rows: List[Dict[str, Any]] = []
    span_specs: List[Tuple[int, int, int, int]] = []

    for day in DAYS:
        day_start = len(body_rows)
        for si in range(N_TIME_SLOTS):
            body_rows.append({"day": day, "slot_idx": si, "sub_idx": 0})
        day_end = len(body_rows) - 1
        if day_end >= day_start:
            span_specs.append((0, day_start, 0, day_end))

    return body_rows, span_specs


def build_carsaf_pdf_bytes(
    schedule_df: pd.DataFrame,
    courses_df: Optional[pd.DataFrame] = None,
    title: Optional[str] = None,
    academic_year: Optional[str] = None,
) -> bytes:
    if academic_year:
        title = (
            "ISUBÜ TEKNOLOJİ FAKÜLTESİ BİLGİSAYAR MÜHENDİSLİĞİ BÖLÜMÜ "
            f"{academic_year} EĞİTİM ÖĞRETİM YILI GÜZ DÖNEMİ DERS PROGRAMI"
        )
    if not title:
        title = DEFAULT_TITLE

    font, font_bold = _register_fonts()
    body_style = ParagraphStyle(
        "carsaf_body",
        fontName=font,
        fontSize=6,
        leading=7,
        alignment=TA_CENTER,
        wordWrap="CJK",
        splitLongWords=True,
    )
    time_style = ParagraphStyle(
        "carsaf_time",
        fontName=font,
        fontSize=5.5,
        leading=6.5,
        alignment=TA_CENTER,
    )
    header_style = ParagraphStyle(
        "carsaf_header",
        fontName=font_bold,
        fontSize=8,
        leading=9.5,
        alignment=TA_CENTER,
    )
    title_style = ParagraphStyle(
        "carsaf_title",
        fontName=font_bold,
        fontSize=10,
        leading=12,
        alignment=TA_CENTER,
    )
    day_style = ParagraphStyle(
        "carsaf_day",
        fontName=font_bold,
        fontSize=7,
        leading=8,
        alignment=TA_CENTER,
    )

    slot_map = _build_slot_map(schedule_df, courses_df=courses_df)
    body_layout, span_specs = _build_body_layout(slot_map)
    n_body = len(body_layout)
    grid: List[List[Any]] = [["" for _ in range(N_COLS)] for _ in range(n_body)]

    page_w = PAGE_WIDTH
    usable = page_w - 2 * MARGIN_LR
    col_day = 12 * mm
    col_time = 16 * mm
    rest = usable - col_day - col_time
    pair_w = rest / N_GRADES
    col_widths = [col_day, col_time]
    for _ in range(N_GRADES):
        col_widths.append(pair_w * 0.68)
        col_widths.append(pair_w * 0.32)

    for ri, brow in enumerate(body_layout):
        day = brow["day"]
        si = brow["slot_idx"]
        sub = brow["sub_idx"]

        if ri == 0 or body_layout[ri - 1]["day"] != day:
            grid[ri][0] = Paragraph(
                _vertical_day_label(day).replace("\n", "<br/>"),
                day_style,
            )

        if sub == 0:
            grid[ri][1] = Paragraph(_slot_label(si), time_style)

        for grade in range(1, N_GRADES + 1):
            col_name = 2 + (grade - 1) * 2
            col_room = col_name + 1
            entries = slot_map.get((day, si, grade), {})
            if entries:
                grid[ri][col_name] = _course_paragraph(entries, body_style)
                grid[ri][col_room] = _room_paragraph(entries, body_style)

    row_heights_body: List[float] = []
    for ri in range(n_body):
        h = BODY_ROW_MM * mm
        for c in range(N_COLS):
            cell = grid[ri][c]
            if isinstance(cell, Paragraph):
                h = max(h, _para_height(cell, col_widths[c]))
        row_heights_body.append(h)

    row_heights: List[float] = [10 * mm, 7 * mm, 7 * mm] + row_heights_body

    title_row = [Paragraph(title, title_style)] + [""] * (N_COLS - 1)
    header1: List[Any] = [Paragraph("GÜN", header_style), Paragraph("SAAT", header_style)]
    for gl in GRADE_LABELS:
        header1.append(Paragraph(gl, header_style))
        header1.append("")
    header2: List[Any] = ["", ""]
    for _ in GRADE_LABELS:
        header2.append(Paragraph("A Şubesi", header_style))
        header2.append(Paragraph("Derslik", header_style))

    table_data = [title_row, header1, header2] + grid
    table = Table(
        table_data,
        colWidths=col_widths,
        rowHeights=row_heights,
        repeatRows=HEADER_ROWS,
    )

    style_cmds: List[Any] = [
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_GREY),
        ("BACKGROUND", (0, 1), (-1, 2), HEADER_GREY),
        ("SPAN", (0, 0), (-1, 0)),
        ("SPAN", (0, 1), (0, 2)),
        ("SPAN", (1, 1), (1, 2)),
    ]
    for gi in range(N_GRADES):
        c0 = 2 + gi * 2
        style_cmds.append(("SPAN", (c0, 1), (c0 + 1, 1)))
    for col, r0, col2, r1 in span_specs:
        style_cmds.append(("SPAN", (col, HEADER_ROWS + r0), (col2, HEADER_ROWS + r1)))

    style_cmds.extend(
        [
            ("GRID", (0, 0), (-1, -1), 0.4, GRID_COLOR),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]
    )
    table.setStyle(TableStyle(style_cmds))

    _wrap_w, table_height = table.wrap(page_w - 2 * MARGIN_LR, 1_000_000)
    page_height = table_height + MARGIN_TOP + MARGIN_BOTTOM + 16

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=(page_w, page_height),
        leftMargin=MARGIN_LR,
        rightMargin=MARGIN_LR,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
    )
    # Tek sayfa: sayfa yüksekliği = tablo yüksekliği (günler ayrı sayfaya taşmaz)
    doc.build([table])
    return buf.getvalue()
