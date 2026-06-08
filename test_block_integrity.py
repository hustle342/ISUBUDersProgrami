"""Kesintisiz ders bloku: çözücü ve taşıma planı."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from scheduler import (  # noqa: E402
    Course,
    enrich_course,
    find_block_violations,
    plan_course_block_move,
    plan_course_block_move_free,
    prepare_courses_for_solver,
    solve_timetable,
)


def load_courses(path: Path):
    df = pd.read_csv(path)
    out = []
    for _, r in df.iterrows():
        out.append(
            enrich_course(
                Course(
                    str(r["code"]),
                    str(r["name"]),
                    str(r["teacher"]),
                    str(r["class"]),
                    int(round(float(r["weekly_hours"]))),
                    str(r.get("department", "")),
                )
            )
        )
    return prepare_courses_for_solver(out)


def main():
    csv = ROOT / "sample_data" / "orjinal_dersler.csv"
    courses = load_courses(csv)
    assignments, msg = solve_timetable(courses, time_limit_seconds=15)
    assert assignments, msg
    rows = [
        {
            "id": i,
            "course_code": a.course_code,
            "class_name": a.class_name,
            "day": a.day,
            "hour": a.hour,
            "teacher": a.teacher,
            "room": "",
        }
        for i, a in enumerate(assignments)
    ]
    bad = find_block_violations(rows)
    assert not bad, bad

    anchor = next(r for r in rows if r["course_code"] == "BLG-228" and "||" in r["class_name"])
    planned, err = plan_course_block_move(rows, anchor["id"], "Salı", 14)
    assert not err, err
    assert len(planned) == 3, planned
    hours = sorted(p["hour"] for p in planned)
    assert hours == [14, 15, 16], hours

    # Sürükle-bırak yolu da kesintisiz blok üretmeli (göreli kaydırma yasak).
    free_planned = plan_course_block_move_free(rows, anchor["id"], "Salı", 9)
    assert len(free_planned) == 3, free_planned
    assert sorted(p["hour"] for p in free_planned) == [9, 10, 11], free_planned
    bad_free = plan_course_block_move_free(rows, anchor["id"], "Salı", 15)
    assert bad_free == [], "Öğle arasından geçmeyen 3 saatlik blok 15:00'te başlayamaz"

    print("OK: blok bütünlüğü", msg)


if __name__ == "__main__":
    main()
