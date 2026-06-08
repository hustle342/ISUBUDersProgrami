"""Proje sağlık taraması — sonuçlar debug-876524.log dosyasına yazılır."""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from debug_log import debug_log  # noqa: E402
from scheduler import (  # noqa: E402
    Course,
    is_elective_course,
    overloaded_classes,
    solve_timetable,
)
from obs_export import build_obs_export_for_button  # noqa: E402
from carsaf_export import build_carsaf_pdf_bytes  # noqa: E402


def load_courses_from_csv() -> list:
    df = pd.read_csv(ROOT / "sample_data" / "orjinal_dersler.csv")
    courses = []
    for _, r in df.iterrows():
        if pd.isna(r.get("code")) or pd.isna(r.get("teacher")) or pd.isna(r.get("class")):
            continue
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


def main() -> int:
    run_id = "health-scan"
    errors = 0

    debug_log("test_project_health.py:start", "health scan started", {"root": str(ROOT)}, run_id=run_id, hypothesis_id="C")

    # H-C: imports
    try:
        import app  # noqa: F401
        debug_log("test_project_health.py:import_app", "app import ok", {}, run_id=run_id, hypothesis_id="C")
    except Exception as exc:
        errors += 1
        debug_log(
            "test_project_health.py:import_app",
            "app import FAILED",
            {"error": str(exc), "tb": traceback.format_exc()[-500:]},
            run_id=run_id,
            hypothesis_id="C",
        )

    courses = load_courses_from_csv()
    over = overloaded_classes(courses, 6)
    debug_log(
        "test_project_health.py:load",
        "courses loaded",
        {"n_courses": len(courses), "overloaded_classes": len(over)},
        run_id=run_id,
        hypothesis_id="D",
    )

    # H-A: solver default-like settings
    for label, kwargs, tlim in [
        ("defaults_35s", dict(weight_class_day_compact=12, weight_teacher_day_compact=8, weight_class_day_spread=0, weight_teacher_gap=2, weight_class_gap=2), 35),
        ("tight_15s", dict(weight_class_day_compact=20, weight_teacher_day_compact=8, weight_class_day_spread=0, weight_teacher_gap=2, weight_class_gap=2), 15),
    ]:
        try:
            a, msg = solve_timetable(
                courses,
                max_daily_hours=6,
                time_limit_seconds=tlim,
                random_seed=42,
                **kwargs,
            )
            ok = len(a) > 0
            debug_log(
                "test_project_health.py:solve",
                f"solve {label}",
                {"ok": ok, "n_assignments": len(a), "msg": msg[:120], "time_limit": tlim},
                run_id=run_id,
                hypothesis_id="A",
            )
            if not ok:
                errors += 1
        except Exception as exc:
            errors += 1
            debug_log(
                "test_project_health.py:solve",
                f"solve {label} EXCEPTION",
                {"error": str(exc)},
                run_id=run_id,
                hypothesis_id="A",
            )

    # H-B: puzzle rules
    try:
        from app import _puzzle_rule_to_hard_rules, _match_solver_teachers  # noqa: E402

        t1 = courses[0].teacher
        puzzle = [
            {
                "pieces": ["teacher", "day"],
                "values": {"teacher": [t1], "day": ["Pazartesi", "Cuma"]},
                "require": True,
            }
        ]
        solver_names = {c.teacher for c in courses}
        hard, warns = _puzzle_rule_to_hard_rules(puzzle, solver_names)
        debug_log(
            "test_project_health.py:puzzle",
            "puzzle conversion",
            {"hard_rules": len(hard), "warnings": warns},
            run_id=run_id,
            hypothesis_id="B",
        )
        a2, msg2 = solve_timetable(courses, hard_rules=hard, time_limit_seconds=35, random_seed=42)
        debug_log(
            "test_project_health.py:puzzle_solve",
            "solve with puzzle rules",
            {"ok": len(a2) > 0, "msg": msg2[:80]},
            run_id=run_id,
            hypothesis_id="B",
        )
        if len(a2) == 0:
            errors += 1
    except Exception as exc:
        errors += 1
        debug_log(
            "test_project_health.py:puzzle",
            "puzzle FAILED",
            {"error": str(exc)},
            run_id=run_id,
            hypothesis_id="B",
        )

    # H-D: exports
    a, _ = solve_timetable(courses, time_limit_seconds=25, random_seed=1)
    if a:
        rows = [
            {
                "Gün": x.day,
                "Saat": f"{x.hour:02d}:00",
                "Kod": x.course_code,
                "Ders": x.course_name,
                "Öğretim Elemanı": x.teacher,
                "Sınıf": x.class_name,
                "Room": "",
            }
            for x in a[:5]
        ]
        df = pd.DataFrame(rows)
        try:
            obs = build_obs_export_for_button(df, None, "detail")
            debug_log(
                "test_project_health.py:obs",
                "obs export",
                {"rows": len(obs), "empty": obs.empty},
                run_id=run_id,
                hypothesis_id="D",
            )
        except Exception as exc:
            errors += 1
            debug_log("test_project_health.py:obs", "obs FAILED", {"error": str(exc)}, run_id=run_id, hypothesis_id="D")
        try:
            pdf = build_carsaf_pdf_bytes(df)
            debug_log(
                "test_project_health.py:pdf",
                "carsaf pdf",
                {"bytes": len(pdf)},
                run_id=run_id,
                hypothesis_id="D",
            )
        except Exception as exc:
            errors += 1
            debug_log("test_project_health.py:pdf", "pdf FAILED", {"error": str(exc)}, run_id=run_id, hypothesis_id="D")

    debug_log(
        "test_project_health.py:done",
        "health scan finished",
        {"errors": errors},
        run_id=run_id,
        hypothesis_id="C",
    )
    print(f"Health scan done. errors={errors}. See debug-876524.log")
    return errors


if __name__ == "__main__":
    raise SystemExit(main())
