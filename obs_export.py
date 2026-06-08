"""OBS ders programı PDF görünümüne uygun CSV dışa aktarma."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from scheduler import (
    DAYS,
    HOUR_TO_SLOT_INDEX,
    SLOT_INDEX_TO_HOUR,
    TIME_SLOTS,
    format_hour_slot,
    format_slot_label,
    parse_hour_from_saat_label,
)

COL_INSTRUCTOR = "Öğretim Elemanı"


def _schedule_instructor(row) -> str:
    val = row.get(COL_INSTRUCTOR, row.get("Hoca", ""))
    return str(val or "").strip().split(" || ")[0]

DEFAULT_BINA = "Merkez 100. Yıl Kampüs Binası"

DAY_TIME_COLUMNS: List[str] = []
for _day in DAYS:
    DAY_TIME_COLUMNS.extend([f"{_day} BAŞ SAATİ", f"{_day} BİT SAATİ"])

OBS_COLUMNS = ["SINIF", "ŞUBE", "DERS ADI", *DAY_TIME_COLUMNS, "BİNA", "DERSLİK", "TKr", "TSa", "ÖĞR. ÜYE"]


def parse_class_section(class_name: str) -> Tuple[str, str]:
    name = str(class_name).strip()
    m = re.match(r"^(?P<sinif>.+?)-(?P<sube>[AB])$", name, re.I)
    if m:
        return m.group("sinif").strip(), m.group("sube").upper()
    return name, "A"


def format_ders_adi(code: str, name: str) -> str:
    code = str(code).strip()
    name = str(name).strip()
    name = re.sub(r"\s*\(Laboratuvar\)\s*$", "", name, flags=re.I).strip()
    if name.upper().startswith(code.upper()):
        rest = name[len(code) :].lstrip("- ").strip()
        return f"{code}-{rest}" if rest else code
    return f"{code}-{name}" if name else code


def format_derslik(room: str, room_type: str = "") -> str:
    room = str(room or "").strip()
    if not room:
        return ""
    rtype = str(room_type or "").strip().lower()
    num = re.search(r"(\d+)", room)
    num_s = num.group(1) if num else ""

    if rtype == "lab" or "lab" in room.lower():
        return f"Bilgisayar Laboratuvarı ({num_s})" if num_s else room
    if "amfi" in room.lower():
        return f"Amfi ({num_s})" if num_s else room

    formatted = room.replace("NOLU", "Nolu").replace("DERSLÝK", "Derslik").replace("DERSLİK", "Derslik")
    return formatted


def _hour_end(hour: int) -> int:
    return hour + 1


def _fmt_time(hour: int) -> str:
    """Çözücü saat indeksinden OBS başlangıç saati (ör. 09:25)."""
    idx = HOUR_TO_SLOT_INDEX.get(int(hour))
    if idx is not None:
        return TIME_SLOTS[idx][0]
    return f"{int(hour):02d}:00"


def _fmt_end(hour: int) -> str:
    """Çözücü saat indeksinden OBS bitiş saati (ör. 10:10)."""
    idx = HOUR_TO_SLOT_INDEX.get(int(hour))
    if idx is not None:
        return TIME_SLOTS[idx][1]
    return f"{int(hour) + 1:02d}:00"


def _is_consecutive(prev: int, curr: int) -> bool:
    return curr == prev + 1 or (prev == 12 and curr == 14)


def merge_hour_blocks(hours: List[int]) -> List[Tuple[int, int]]:
    if not hours:
        return []
    uniq = sorted(set(int(h) for h in hours))
    blocks: List[Tuple[int, int]] = []
    start = prev = uniq[0]
    for h in uniq[1:]:
        if _is_consecutive(prev, h):
            prev = h
        else:
            blocks.append((start, prev))
            start = prev = h
    blocks.append((start, prev))
    return blocks


def _parse_hour_from_saat(saat_val: Any) -> Optional[int]:
    return parse_hour_from_saat_label(saat_val)


def _course_meta_lookup(course_df: Optional[pd.DataFrame]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    if course_df is None or course_df.empty:
        return {}
    lookup: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for _, row in course_df.iterrows():
        code = str(row.get("code", "")).strip()
        cls = str(row.get("class", "")).strip()
        if not code:
            continue
        try:
            weekly = float(row.get("weekly_hours", 0) or 0)
        except Exception:
            weekly = 0.0
        try:
            lab_h = float(row.get("lab_hours", 0) or 0)
        except Exception:
            lab_h = 0.0
        ctype = str(row.get("course_type", "")).strip().lower()
        lookup[(code, cls)] = {
            "name": str(row.get("name", "")).strip(),
            "teacher": str(row.get("teacher", "")).strip(),
            "weekly_hours": weekly,
            "lab_hours": lab_h,
            "course_type": ctype,
        }
        lookup.setdefault((code, ""), lookup[(code, cls)])
    return lookup


def _credits_for_row(code: str, meta: Dict[str, Any], is_lab: bool) -> Tuple[str, str]:
    weekly = meta.get("weekly_hours", 0) or 0
    lab_h = meta.get("lab_hours", 0) or 0
    if is_lab:
        tkr = ""
        tsa = _fmt_num(weekly) if weekly else ""
    else:
        tkr = _fmt_num(weekly)
        tsa = _fmt_num(lab_h) if lab_h > 0 else _fmt_num(weekly)
    return tkr, tsa


def _fmt_num(val: Any) -> str:
    try:
        f = float(val)
    except Exception:
        return ""
    if f == int(f):
        return str(int(f))
    return str(f)


def _sinif_sort_key(sinif: str, sube: str) -> Tuple:
    m = re.match(r"(\d+)", sinif)
    year = int(m.group(1)) if m else 99
    return (year, sinif, sube)


def _sort_obs_df(df: pd.DataFrame, sort_cols: List[str]) -> pd.DataFrame:
    if df.empty:
        return df
    keys = [c for c in sort_cols if c in df.columns]
    if not keys:
        return df
    return df.sort_values(keys).reset_index(drop=True)


def build_obs_export_df(
    schedule_df: pd.DataFrame,
    course_df: Optional[pd.DataFrame] = None,
    mode: str = "detail",
) -> pd.DataFrame:
    """
    Program satırlarından OBS PDF düzeninde tek tablo üretir.
    schedule_df: Gün, Saat, Kod, Ders, Öğretim Elemanı, Sınıf, Room (+ room_type opsiyonel)
    """
    if schedule_df is None or schedule_df.empty:
        return pd.DataFrame(columns=OBS_COLUMNS)

    meta_lookup = _course_meta_lookup(course_df)
    sessions: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}

    for _, row in schedule_df.iterrows():
        code = str(row.get("Kod", "")).strip()
        cls = str(row.get("Sınıf", "")).strip()
        if not code or not cls:
            continue
        day = str(row.get("Gün", "")).strip()
        hour = _parse_hour_from_saat(row.get("Saat"))
        if day not in DAYS or hour is None:
            continue

        key = (cls, code)
        sessions.setdefault(key, []).append(
            {
                "day": day,
                "hour": hour,
                "room": str(row.get("Room", "") or "").strip(),
                "room_type": str(row.get("room_type", "") or "").strip(),
                "teacher": _schedule_instructor(row),
                "name": str(row.get("Ders", "")).strip(),
            }
        )

    export_rows: List[Dict[str, str]] = []

    for (cls, code), items in sessions.items():
        sinif, sube = parse_class_section(cls)
        meta = meta_lookup.get((code, cls)) or meta_lookup.get((code, ""), {})
        is_lab = code.upper().endswith("-LAB") or str(meta.get("course_type", "")).lower() == "lab"
        ders_name = meta.get("name") or (items[0]["name"] if items else code)
        teacher = meta.get("teacher") or (items[0]["teacher"] if items else "")
        tkr, tsa = _credits_for_row(code, meta, is_lab)

        by_day: Dict[str, List[int]] = {d: [] for d in DAYS}
        room = ""
        room_type = ""
        for it in items:
            by_day[it["day"]].append(it["hour"])
            if it["room"]:
                room = it["room"]
                room_type = it.get("room_type", "")

        day_blocks: List[Tuple[str, List[Tuple[int, int]]]] = []
        for day in DAYS:
            blocks = merge_hour_blocks(by_day[day])
            if blocks:
                day_blocks.append((day, blocks))

        if not day_blocks:
            continue

        # Aynı günde birden fazla zaman bloğu varsa OBS'teki gibi ayrı satır
        max_rows = max(len(blocks) for _, blocks in day_blocks)
        block_matrix: List[Dict[str, Tuple[int, int]]] = []
        for i in range(max_rows):
            block_matrix.append({})

        for day, blocks in day_blocks:
            for i, block in enumerate(blocks):
                if i < len(block_matrix):
                    block_matrix[i][day] = block

        for block_map in block_matrix:
            if not block_map:
                continue
            row_out = {col: "" for col in OBS_COLUMNS}
            row_out["SINIF"] = sinif
            row_out["ŞUBE"] = sube
            row_out["DERS ADI"] = format_ders_adi(code, ders_name)
            row_out["BİNA"] = DEFAULT_BINA
            row_out["DERSLİK"] = format_derslik(room, room_type)
            row_out["TKr"] = tkr
            row_out["TSa"] = tsa
            row_out["ÖĞR. ÜYE"] = teacher

            for day in DAYS:
                block = block_map.get(day)
                if block:
                    row_out[f"{day} BAŞ SAATİ"] = _fmt_time(block[0])
                    row_out[f"{day} BİT SAATİ"] = _fmt_end(block[1])

            export_rows.append(row_out)

    if not export_rows:
        return _empty_for_mode(mode)

    out = pd.DataFrame(export_rows)
    return _apply_export_mode(out, schedule_df, mode)


def _empty_for_mode(mode: str) -> pd.DataFrame:
    if mode == "weekly":
        return pd.DataFrame(columns=["Saat"] + DAYS)
    if mode == "teacher":
        cols = ["ÖĞR. ÜYE", "DERS ADI", "SINIF", "ŞUBE", *DAY_TIME_COLUMNS, "DERSLİK"]
        return pd.DataFrame(columns=cols)
    if mode == "class":
        cols = ["SINIF", "ŞUBE", "DERS ADI", "ÖĞR. ÜYE", *DAY_TIME_COLUMNS, "DERSLİK"]
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(columns=OBS_COLUMNS)


def _apply_export_mode(full_df: pd.DataFrame, schedule_df: pd.DataFrame, mode: str) -> pd.DataFrame:
    mode = (mode or "detail").strip().lower()

    if mode == "detail":
        out = full_df.copy()
        out["_sort_sinif"] = out["SINIF"].map(lambda s: _sinif_sort_key(s, ""))
        out = out.sort_values(["_sort_sinif", "SINIF", "ŞUBE", "DERS ADI"]).drop(columns=["_sort_sinif"])
        return out[OBS_COLUMNS]

    if mode == "teacher":
        cols = ["ÖĞR. ÜYE", "DERS ADI", "SINIF", "ŞUBE", *DAY_TIME_COLUMNS, "DERSLİK"]
        out = full_df[[c for c in cols if c in full_df.columns]].copy()
        return _sort_obs_df(out, ["ÖĞR. ÜYE", "DERS ADI", "SINIF", "ŞUBE"])

    if mode == "class":
        cols = ["SINIF", "ŞUBE", "DERS ADI", "ÖĞR. ÜYE", *DAY_TIME_COLUMNS, "DERSLİK"]
        out = full_df[[c for c in cols if c in full_df.columns]].copy()
        out["_sort_sinif"] = out["SINIF"].map(lambda s: _sinif_sort_key(s, ""))
        out = out.sort_values(["_sort_sinif", "SINIF", "ŞUBE", "DERS ADI"]).drop(columns=["_sort_sinif"])
        return out[cols]

    if mode == "weekly":
        return build_obs_weekly_grid(schedule_df)

    return full_df[OBS_COLUMNS]


def build_obs_weekly_grid(schedule_df: pd.DataFrame) -> pd.DataFrame:
    """Haftalık özet: satır=saat dilimi, sütun=gün; hücrede kısa ders özeti."""
    if schedule_df is None or schedule_df.empty:
        return pd.DataFrame(columns=["Saat"] + DAYS)

    cells: Dict[Tuple[str, int], List[str]] = {}
    for _, row in schedule_df.iterrows():
        day = str(row.get("Gün", "")).strip()
        hour = _parse_hour_from_saat(row.get("Saat"))
        if day not in DAYS or hour is None:
            continue
        code = str(row.get("Kod", "")).strip()
        cls = str(row.get("Sınıf", "")).strip()
        room = format_derslik(str(row.get("Room", "") or ""), str(row.get("room_type", "") or ""))
        teacher = _schedule_instructor(row)
        sinif, sube = parse_class_section(cls)
        label = f"{code} ({sinif}-{sube})"
        if room:
            label += f" / {room}"
        if teacher:
            label += f" / {teacher}"
        cells.setdefault((day, hour), []).append(label)

    rows_out: List[Dict[str, str]] = []
    for idx in range(len(TIME_SLOTS)):
        row = {"Saat": format_slot_label(idx)}
        hour = SLOT_INDEX_TO_HOUR.get(idx)
        for day in DAYS:
            labels = cells.get((day, hour), []) if hour is not None else []
            row[day] = " | ".join(dict.fromkeys(labels)) if labels else ""
        if any(row[d] for d in DAYS):
            rows_out.append(row)

    return pd.DataFrame(rows_out, columns=["Saat"] + DAYS)


def build_obs_export_for_button(
    schedule_df: pd.DataFrame,
    course_df: Optional[pd.DataFrame] = None,
    button: str = "detail",
) -> pd.DataFrame:
    """button: detail | weekly | teacher | class"""
    mapping = {
        "detail": "detail",
        "detaylı": "detail",
        "detayli": "detail",
        "weekly": "weekly",
        "haftalik": "weekly",
        "haftalık": "weekly",
        "teacher": "teacher",
        "hoca": "teacher",
        "class": "class",
        "sinif": "class",
        "sınıf": "class",
    }
    mode = mapping.get(button.strip().lower(), "detail")
    return build_obs_export_df(schedule_df, course_df=course_df, mode=mode)


def obs_export_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")
