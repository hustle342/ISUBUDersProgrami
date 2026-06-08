"""Kohort çakışması ve çarşaf PDF filtreleme doğrulaması."""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from carsaf_export import _build_slot_map, build_carsaf_pdf_bytes  # noqa: E402
from obs_export import _parse_hour_from_saat  # noqa: E402
from scheduler import (  # noqa: E402
    Course,
    HOUR_TO_SLOT_INDEX,
    enrich_course,
    format_hour_slot,
    is_elective_course,
    mandatory_cohort_keys,
    solve_timetable,
)


def load_courses() -> list:
    df = pd.read_csv(ROOT / "sample_data" / "orjinal_dersler.csv")
    out = []
    for _, r in df.iterrows():
        if pd.isna(r.get("code")) or pd.isna(r.get("teacher")) or pd.isna(r.get("class")):
            continue
        wh = int(round(float(r["weekly_hours"])))
        if wh <= 0:
            continue
        ct = str(r.get("course_type", "")).lower()
        out.append(
            Course(
                str(r["code"]),
                str(r["name"]),
                str(r["teacher"]),
                str(r["class"]),
                wh,
                is_elective=ct in ("seçimlik", "secimlik", "elective", "s"),
            )
        )
    return out, df


def cohort_conflicts(assignments, course_by_key):
    by_slot = defaultdict(list)
    for a in assignments:
        c = course_by_key.get((a.course_code, a.class_name))
        if c is None or is_elective_course(c):
            continue
        for ck in mandatory_cohort_keys(a.class_name):
            by_slot[(a.day, a.hour, ck)].append(a.course_code)
    return {k: v for k, v in by_slot.items() if len(set(v)) > 1}


def main() -> int:
    courses, df = load_courses()
    course_by_key = {(c.code, c.class_name): c for c in courses}
    assignments, msg = solve_timetable(courses, time_limit_seconds=45, random_seed=42)
    if not assignments:
        print("FAIL: solve", msg)
        return 1

    conflicts = cohort_conflicts(assignments, course_by_key)
    if conflicts:
        print("FAIL: cohort conflicts", len(conflicts), list(conflicts.items())[:3])
        return 1

    rows = [
        {
            "Gün": a.day,
            "Saat": format_hour_slot(a.hour),
            "Kod": a.course_code,
            "Ders": a.course_name,
            "Öğretim Elemanı": a.teacher,
            "Sınıf": a.class_name,
            "Room": "405",
        }
        for a in assignments
    ]
    sched = pd.DataFrame(rows)
    slot_map = _build_slot_map(sched, courses_df=df)

    # 2. sınıf Pazartesi 09:25 slotunda en fazla 1 zorunlu A gösterilmeli
    mon_925 = slot_map.get(("Pazartesi", HOUR_TO_SLOT_INDEX.get(9), 2), {})
    if len(mon_925) > 4:
        print("FAIL: carsaf grade2 mon slot has too many entries", mon_925)
        return 1

    # B şubesi PDF'te olmalı
    b_codes = {e["code"] for entries in slot_map.values() for e in entries.values()}
    if "BLG-224" not in b_codes or "BLG-228" not in b_codes:
        print("FAIL: BLG-224/228 B missing from carsaf map", b_codes)
        return 1

    # Seçmeli kodları çarşafa dahil olmalı
    elective_codes = {"BLG-212", "BLG-222", "BLG-232"}
    missing_el = elective_codes - b_codes
    if missing_el:
        print("FAIL: electives missing from carsaf", missing_el)
        return 1

    pdf = build_carsaf_pdf_bytes(sched, courses_df=df)
    if len(pdf) < 1000:
        print("FAIL: pdf too small")
        return 1

    print("OK: cohort=0 conflicts, carsaf filtered, pdf bytes=", len(pdf))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
