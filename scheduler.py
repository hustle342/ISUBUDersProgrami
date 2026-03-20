from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from ortools.sat.python import cp_model


DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]
HOURS = [9, 10, 11, 12, 14, 15, 16]  # son ders 16:00-17:00, en geç 17:00'da bitiyor


@dataclass
class Course:
    code: str
    name: str
    teacher: str
    class_name: str
    weekly_hours: int


@dataclass
class SessionAssignment:
    course_code: str
    course_name: str
    teacher: str
    class_name: str
    day: str
    hour: int


def build_slots() -> List[Tuple[str, int]]:
    return [(day, hour) for day in DAYS for hour in HOURS]


def solve_timetable(
    courses: List[Course],
    weight_teacher_day_compact: int = 8,
    weight_class_day_compact: int = 5,
    weight_teacher_gap: int = 4,
    weight_class_gap: int = 4,
    max_daily_hours: int = 6,
    teacher_unavailable_slots: Optional[Dict[str, Set[Tuple[str, int]]]] = None,
    hard_rules: Optional[List[Dict[str, Any]]] = None,
    time_limit_seconds: int = 8,
) -> Tuple[List[SessionAssignment], str]:
    if not courses:
        return [], "Çözülecek ders verisi yok."

    slots = build_slots()
    n_slots = len(slots)
    n_hours = len(HOURS)
    model = cp_model.CpModel()

    session_ids: List[Tuple[int, int]] = []
    for ci, course in enumerate(courses):
        for si in range(course.weekly_hours):
            session_ids.append((ci, si))

    x: Dict[Tuple[int, int, int], cp_model.IntVar] = {}
    for sid, (ci, si) in enumerate(session_ids):
        for slot_i in range(n_slots):
            x[(sid, ci, slot_i)] = model.NewBoolVar(f"x{sid}_{slot_i}")

    # Her oturum tam bir slota atanmalı.
    for sid, (ci, si) in enumerate(session_ids):
        model.Add(sum(x[(sid, ci, slot_i)] for slot_i in range(n_slots)) == 1)

    # ── SERT KURALLAR ──────────────────────────────────────────────────────────

    # Aynı hocanın aynı slotta iki dersi olamaz.
    teachers = sorted({c.teacher for c in courses})
    teacher_sessions: Dict[str, List[Tuple[int, int]]] = {t: [] for t in teachers}
    for sid, (ci, si) in enumerate(session_ids):
        teacher_sessions[courses[ci].teacher].append((sid, ci))

    for teacher, ts in teacher_sessions.items():
        for slot_i in range(n_slots):
            model.Add(sum(x[(sid, ci, slot_i)] for sid, ci in ts) <= 1)

    # Öğretmen bazlı yasak slotlar (chat kuralları gibi dış kısıtlar).
    if teacher_unavailable_slots:
        for teacher, ts in teacher_sessions.items():
            blocked = teacher_unavailable_slots.get(teacher, set())
            if not blocked:
                continue
            for slot_i, (day, hour) in enumerate(slots):
                if (day, hour) in blocked:
                    model.Add(sum(x[(sid, ci, slot_i)] for sid, ci in ts) == 0)

    # Aynı sınıfın aynı slotta iki dersi olamaz.
    classes = sorted({c.class_name for c in courses})
    class_sessions: Dict[str, List[Tuple[int, int]]] = {c: [] for c in classes}
    for sid, (ci, si) in enumerate(session_ids):
        class_sessions[courses[ci].class_name].append((sid, ci))

    for class_name, class_entries in class_sessions.items():
        for slot_i in range(n_slots):
            model.Add(sum(x[(sid, ci, slot_i)] for sid, ci in class_entries) <= 1)

    # Yapısal sert kurallar (öğretmen/gün/saat/ders/sınıf + olsun/olmasın).
    if hard_rules:
        for ridx, rule in enumerate(hard_rules):
            require = bool(rule.get("require", False))
            rule_teacher = rule.get("teacher")
            rule_day = rule.get("day")
            rule_hour = rule.get("hour")
            rule_course_code = rule.get("course_code")
            rule_class_name = rule.get("class_name")

            matched_literals = []
            for sid, (ci, si) in enumerate(session_ids):
                course = courses[ci]

                if rule_teacher and course.teacher != rule_teacher:
                    continue
                if rule_course_code and course.code != rule_course_code:
                    continue
                if rule_class_name and course.class_name != rule_class_name:
                    continue

                for slot_i, (day, hour) in enumerate(slots):
                    if rule_day and day != rule_day:
                        continue
                    if rule_hour is not None and hour != int(rule_hour):
                        continue
                    matched_literals.append(x[(sid, ci, slot_i)])

            if require:
                if not matched_literals:
                    return [], f"Kural-{ridx+1} için eşleşen yer bulunamadı (olsun)."
                model.Add(sum(matched_literals) >= 1)
            else:
                if matched_literals:
                    model.Add(sum(matched_literals) == 0)

    day_to_slot_indices: Dict[str, List[int]] = {day: [] for day in DAYS}
    for slot_i, (day, hour) in enumerate(slots):
        day_to_slot_indices[day].append(slot_i)

    # Günlük maksimum ders saati (yalnızca sınıflar için; öğrenci refahı).
    for class_name, class_entries in class_sessions.items():
        for day in DAYS:
            day_slots = day_to_slot_indices[day]
            model.Add(
                sum(x[(sid, ci, slot_i)] for sid, ci in class_entries for slot_i in day_slots)
                <= max_daily_hours
            )

    # ── YARDIMCI: session_at[ei, di, hi] ──────────────────────────────────────
    # 1 iff entity has a session at that hour index on that day.

    def build_session_at(entity_tag: str, entity_list, sessions_map) -> Dict:
        sa: Dict[Tuple[int, int, int], cp_model.IntVar] = {}
        for ei, entity in enumerate(entity_list):
            ent_sessions = sessions_map[entity]
            for di, day in enumerate(DAYS):
                for hi, slot_i in enumerate(day_to_slot_indices[day]):
                    v = model.NewBoolVar(f"sa{entity_tag}{ei}_{di}_{hi}")
                    sa[(ei, di, hi)] = v
                    cnt = sum(x[(sid, ci, slot_i)] for sid, ci in ent_sessions)
                    model.Add(cnt >= v)
                    model.Add(cnt <= len(ent_sessions) * v)
        return sa

    teacher_sa = build_session_at("t", teachers, teacher_sessions)
    class_sa = build_session_at("c", classes, class_sessions)

    # ── YUMUŞAK KURALLAR ───────────────────────────────────────────────────────

    objective_terms = []

    # Yumuşak 1: Hocanın ders gün sayısını azalt.
    for ei, teacher in enumerate(teachers):
        ts = teacher_sessions[teacher]
        for di, day in enumerate(DAYS):
            used = model.NewBoolVar(f"tdu{ei}_{di}")
            day_slots = day_to_slot_indices[day]
            day_sum = sum(x[(sid, ci, slot_i)] for sid, ci in ts for slot_i in day_slots)
            model.Add(day_sum >= used)
            model.Add(day_sum <= len(ts) * used)
            objective_terms.append(weight_teacher_day_compact * used)

    # Yumuşak 2: Sınıfın ders gün sayısını azalt.
    for ei, class_name in enumerate(classes):
        class_entries = class_sessions[class_name]
        for di, day in enumerate(DAYS):
            used = model.NewBoolVar(f"cdu{ei}_{di}")
            day_slots = day_to_slot_indices[day]
            day_sum = sum(x[(sid, ci, slot_i)] for sid, ci in class_entries for slot_i in day_slots)
            model.Add(day_sum >= used)
            model.Add(day_sum <= len(class_entries) * used)
            objective_terms.append(weight_class_day_compact * used)

    # Yumuşak 3 & 4: Boşluk minimizasyonu.
    # İki ders arasında boş kalan her saat slot'u penalize edilir.
    def add_gap_penalty(sa_dict, entity_list, entity_tag: str, weight: int) -> None:
        for ei in range(len(entity_list)):
            for di in range(len(DAYS)):
                for hi in range(1, n_hours - 1):  # sadece iç slotlar
                    s_at = sa_dict[(ei, di, hi)]

                    # Bu saatten önce ders var mı?
                    ab = model.NewBoolVar(f"ab{entity_tag}{ei}_{di}_{hi}")
                    model.Add(sum(sa_dict[(ei, di, h)] for h in range(hi)) >= ab)
                    model.Add(sum(sa_dict[(ei, di, h)] for h in range(hi)) <= n_hours * ab)

                    # Bu saatten sonra ders var mı?
                    aa = model.NewBoolVar(f"aa{entity_tag}{ei}_{di}_{hi}")
                    model.Add(sum(sa_dict[(ei, di, h)] for h in range(hi + 1, n_hours)) >= aa)
                    model.Add(sum(sa_dict[(ei, di, h)] for h in range(hi + 1, n_hours)) <= n_hours * aa)

                    # Boşluk: öncesi ve sonrası dolu ama bu slot boş
                    gap = model.NewBoolVar(f"gap{entity_tag}{ei}_{di}_{hi}")
                    model.Add(gap >= ab + aa - 1 - s_at)
                    objective_terms.append(weight * gap)

    if weight_teacher_gap > 0:
        add_gap_penalty(teacher_sa, teachers, "t", weight_teacher_gap)
    if weight_class_gap > 0:
        add_gap_penalty(class_sa, classes, "c", weight_class_gap)

    model.Minimize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 8

    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return [], "Verilen kısıtlarla uygun bir program bulunamadı."

    assignments: List[SessionAssignment] = []
    for sid, (ci, si) in enumerate(session_ids):
        for slot_i, (day, hour) in enumerate(slots):
            if solver.Value(x[(sid, ci, slot_i)]) == 1:
                course = courses[ci]
                assignments.append(
                    SessionAssignment(
                        course_code=course.code,
                        course_name=course.name,
                        teacher=course.teacher,
                        class_name=course.class_name,
                        day=day,
                        hour=hour,
                    )
                )
                break

    assignments.sort(key=lambda a: (DAYS.index(a.day), a.hour, a.class_name, a.teacher))

    status_text = "Optimal çözüm bulundu." if status == cp_model.OPTIMAL else "Uygun çözüm bulundu."
    return assignments, status_text
