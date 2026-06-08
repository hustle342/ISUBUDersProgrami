"""Yapboz kural dönüşümü ve çözücü entegrasyonu — Streamlit olmadan test."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from scheduler import Course, solve_timetable  # noqa: E402

# app modülündeki dönüşüm fonksiyonları (Streamlit UI çalıştırılmaz)
from app import (  # noqa: E402
    _match_solver_teachers,
    _puzzle_rule_to_hard_rules,
    _puzzle_rules_fingerprint,
)


def load_two_teachers():
    path = ROOT / "sample_data" / "orjinal_dersler.csv"
    df = pd.read_csv(path)
    t1 = "Prof. Dr. Tuncay AYDOĞAN"
    t2 = "Dr. Öğr. Üyesi Cevriye ALTINTAŞ"
    rows = df[df["teacher"].isin([t1, t2])].head(6)
    courses = []
    for _, r in rows.iterrows():
        courses.append(
            Course(
                str(r["code"]),
                str(r["name"]),
                str(r["teacher"]),
                str(r["class"]),
                int(round(float(r["weekly_hours"]))),
            )
        )
    return courses, t1, t2


def main():
    courses, t1, t2 = load_two_teachers()
    solver_names = {c.teacher for c in courses}

    puzzle = [
        {
            "pieces": ["teacher", "day"],
            "values": {"teacher": [t1, t2], "day": ["Pazartesi", "Cuma"]},
            "require": True,
        }
    ]

    hard, warnings = _puzzle_rule_to_hard_rules(puzzle, solver_names)
    assert not warnings, warnings
    assert len(hard) == 4, f"beklenen 4 sert kural, gelen {len(hard)}: {hard}"

    assignments, msg = solve_timetable(courses, hard_rules=hard, time_limit_seconds=20)
    assert assignments, msg

    for teacher in (t1, t2):
        days = {a.day for a in assignments if a.teacher == teacher}
        assert "Pazartesi" in days and "Cuma" in days, (
            f"{teacher} Pazartesi/Cuma kuralını sağlamadı: {days}"
        )

    fp1 = _puzzle_rules_fingerprint(puzzle)
    fp2 = _puzzle_rules_fingerprint(puzzle + [{"pieces": ["day"], "values": {"day": ["Salı"]}, "require": True}])
    assert fp1 != fp2

    print("OK: 2 hoca x Pazartesi + Cuma kurallari calisiyor.")
    print("Sert kurallar:", hard)
    for a in assignments:
        print(f"  {a.teacher[:30]:30} {a.day:10} saat={a.hour} {a.course_code}")


if __name__ == "__main__":
    main()
