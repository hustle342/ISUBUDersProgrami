"""Optimizasyon kaydırıcılarının etkisini doğrular (Streamlit olmadan)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from scheduler import Course, schedule_class_day_report, solve_timetable  # noqa: E402


def load_class_courses(class_name: str = "1.Sınıf"):
    df = pd.read_csv(ROOT / "sample_data" / "orjinal_dersler.csv")
    courses = []
    for _, r in df[df["class"] == class_name].iterrows():
        wh = int(round(float(r["weekly_hours"])))
        if wh <= 0:
            continue
        ct = str(r.get("course_type", "")).lower()
        courses.append(
            Course(
                str(r["code"]),
                str(r["name"]),
                str(r["teacher"]),
                str(r["class"]),
                wh,
                is_elective=ct in ("seçimlik", "secimlik", "elective", "s"),
            )
        )
    return courses


def main():
    courses = load_class_courses()
    compact, _ = solve_timetable(
        courses,
        weight_class_day_compact=20,
        weight_class_day_spread=0,
        weight_teacher_gap=0,
        weight_class_gap=0,
        weight_teacher_day_compact=0,
        max_daily_hours=6,
        time_limit_seconds=40,
        random_seed=42,
    )
    spread_gap, _ = solve_timetable(
        courses,
        weight_class_day_compact=0,
        weight_class_day_spread=0,
        weight_teacher_gap=0,
        weight_class_gap=20,
        weight_teacher_day_compact=0,
        max_daily_hours=6,
        time_limit_seconds=40,
        random_seed=42,
    )
    rep_c = schedule_class_day_report(compact, courses, max_daily_hours=6)[0]
    rep_g = schedule_class_day_report(spread_gap, courses, max_daily_hours=6)[0]

    assert rep_c["free_days"] >= 1, f"compact: beklenen boş gün, gelen {rep_c}"
    assert rep_g["days_used"] >= rep_c["days_used"], "yüksek boşluk cezası daha fazla gün kullanmalı"

    print("OK: compact ->", rep_c)
    print("OK: gap20   ->", rep_g)


if __name__ == "__main__":
    main()
