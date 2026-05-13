from __future__ import annotations

from collections import defaultdict
from types import SimpleNamespace

import pandas as pd
import streamlit as st
import math


def maybe_rerun():
    """Attempt to rerun the Streamlit script.

    Some Streamlit versions may not expose `st.experimental_rerun`. In that
    case we fall back to a safe `st.stop()` after toggling a session flag so
    the UI will refresh on the next interaction.
    """
    try:
        # preferred API
        st.experimental_rerun()
    except Exception:
        # best-effort fallback
        st.session_state["_need_rerun"] = st.session_state.get("_need_rerun", 0) + 1
        st.stop()


def safe_read_csv(uploaded_file):
    """Try reading an uploaded CSV with several common encodings (utf-8, cp1254, latin1).
    Returns a DataFrame or raises the last exception.
    """
    encodings = ["utf-8", "cp1254", "latin1"]
    last_exc = None
    for enc in encodings:
        try:
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file, sep=None, engine="python", encoding=enc)
            return df
        except Exception as e:
            last_exc = e
            continue
    # if all fail, re-raise the last error
    raise last_exc

from scheduler import Course, DAYS, HOURS, solve_timetable


RULE_PIECES = ["teacher", "day", "hour", "course", "class"]
RULE_PIECE_LABELS = {
    "teacher": "Öğretmen",
    "day": "Gün",
    "hour": "Saat",
    "course": "Ders",
    "class": "Sınıf",
}


def assign_rooms_to_schedule(assignments, rooms_df, class_info_df, over_pct: float = 0.0, use_mandatory_only: bool = False, enrolled_map=None):
    """
    Basit bir greedy salon ataması yapar:
    - assignments: list of SessionAssignment
    - rooms_df: DataFrame with columns ['room','capacity','type','equipment']
    - class_info_df: DataFrame with columns ['class_name','students','mandatory_attendance']
    - over_pct: percent to allow over capacity (0..100)
    - use_mandatory_only: if True use mandatory_attendance as student count
    Döndürür: DataFrame ile ek sütunlar (`Room`, `room_type`, `room_equipment`, `students`, `room_capacity`, `room_ok`, `over_by`).
    """
    # build mappings
    class_map = {}
    mand_map = {}
    for _, r in class_info_df.iterrows():
        cname = str(r.get("class_name", ""))
        try:
            class_map[cname] = int(r.get("students", 0)) if not pd.isna(r.get("students")) else 0
        except Exception:
            class_map[cname] = 0
        try:
            mand_map[cname] = int(r.get("mandatory_attendance", 0)) if not pd.isna(r.get("mandatory_attendance")) else 0
        except Exception:
            mand_map[cname] = 0

    # prepare rooms list with applied over_pct
    rooms = []
    for _, rr in rooms_df.iterrows():
        try:
            cap_raw = rr.get("capacity", 0)
            if isinstance(cap_raw, str):
                cap_raw = cap_raw.strip().replace(",", ".")
            cap = float(cap_raw)
        except Exception:
            cap = 0.0
        rooms.append(
            {
                "room": str(rr.get("room", "")),
                "raw_capacity": cap,
                "capacity": cap * (1.0 + float(over_pct) / 100.0),
                "type": str(rr.get("type", "Derslik")),
                "equipment": str(rr.get("equipment", "")),
            }
        )

    # group sessions by (day,hour)
    slot_map = defaultdict(list)
    for a in assignments:
        key = (a.day, a.hour)
        # priority for student count:
        # 1) if use_mandatory_only -> mandatory_attendance
        # 2) if enrolled_map provided and has course-level value -> use it
        # 3) fallback to class-level students from class_info_df
        if use_mandatory_only:
            students = mand_map.get(a.class_name, 0)
        else:
            students = None
            if enrolled_map:
                # try (course_code, class_name) then course_code
                students = enrolled_map.get((a.course_code, a.class_name)) if isinstance(enrolled_map, dict) else None
                if students is None:
                    students = enrolled_map.get(a.course_code) if isinstance(enrolled_map, dict) else None
            if students is None:
                students = class_map.get(a.class_name, 0)

        manual_room = getattr(a, "room", None)
        if manual_room is not None:
            manual_room = str(manual_room).strip()
            if not manual_room:
                manual_room = None

        slot_map[key].append({"assign": a, "students": students, "manual_room": manual_room})

    rows = []
    for (day, hour), sessions in slot_map.items():
        available = [{**r, "used": False} for r in rooms]
        sessions_sorted = sorted(sessions, key=lambda s: s["students"], reverse=True)
        for s in sessions_sorted:
            a = s["assign"]
            students = s["students"]
            manual_room = s.get("manual_room")
            placed = False

            # If user manually selected a room, honor it when available in this slot.
            if manual_room:
                cand_manual = next((r for r in available if (not r["used"]) and str(r.get("room", "")) == manual_room), None)
                if cand_manual is not None:
                    cand_manual["used"] = True
                    over_by_manual = max(0, students - cand_manual["capacity"])
                    rows.append(
                        {
                            "id": getattr(a, "id", None),
                            "Gün": day,
                            "Saat": f"{hour:02d}:00-{hour+1:02d}:00",
                            "Ders": a.course_name,
                            "Kod": a.course_code,
                            "Hoca": a.teacher.split(" || ")[0],
                            "Sınıf": a.class_name,
                            "Room": cand_manual["room"],
                            "room_type": cand_manual.get("type", "Derslik"),
                            "room_equipment": cand_manual.get("equipment", ""),
                            "room_ok": students <= cand_manual["capacity"],
                            "students": students,
                            "room_capacity": cand_manual.get("raw_capacity", cand_manual["capacity"]),
                            "over_by": int(math.ceil(over_by_manual)),
                        }
                    )
                    placed = True

            if placed:
                continue

            # try smallest sufficient room
            candidates = sorted([r for r in available if not r["used"]], key=lambda r: r["capacity"])
            for cand in candidates:
                if students <= cand["capacity"]:
                    cand["used"] = True
                    rows.append(
                        {
                            "id": getattr(a, "id", None),
                            "Gün": day,
                            "Saat": f"{hour:02d}:00-{hour+1:02d}:00",
                            "Ders": a.course_name,
                            "Kod": a.course_code,
                            "Hoca": a.teacher.split(" || ")[0],
                            "Sınıf": a.class_name,
                            "Room": cand["room"],
                            "room_type": cand.get("type", "Derslik"),
                            "room_equipment": cand.get("equipment", ""),
                            "room_ok": True,
                            "students": students,
                            "room_capacity": cand.get("raw_capacity", cand["capacity"]),
                            "over_by": 0,
                        }
                    )
                    placed = True
                    break

            if not placed:
                free_rooms = [r for r in available if not r["used"]]
                if free_rooms:
                    best = max(free_rooms, key=lambda r: r["capacity"])
                    best["used"] = True
                    over_by = max(0, students - best["capacity"])
                    rows.append(
                        {
                            "id": getattr(a, "id", None),
                            "Gün": day,
                            "Saat": f"{hour:02d}:00-{hour+1:02d}:00",
                            "Ders": a.course_name,
                            "Kod": a.course_code,
                            "Hoca": a.teacher.split(" || ")[0],
                            "Sınıf": a.class_name,
                            "Room": best["room"],
                            "room_type": best.get("type", "Derslik"),
                            "room_equipment": best.get("equipment", ""),
                            "room_ok": False,
                            "students": students,
                            "room_capacity": best.get("raw_capacity", best["capacity"]),
                            "over_by": int(math.ceil(over_by)),
                        }
                    )
                else:
                    rows.append(
                        {
                            "id": getattr(a, "id", None),
                            "Gün": day,
                            "Saat": f"{hour:02d}:00-{hour+1:02d}:00",
                            "Ders": a.course_name,
                            "Kod": a.course_code,
                            "Hoca": a.teacher.split(" || ")[0],
                            "Sınıf": a.class_name,
                            "Room": None,
                            "room_type": "",
                            "room_equipment": "",
                            "room_ok": False,
                            "students": students,
                            "room_capacity": 0,
                            "over_by": int(students),
                        }
                    )

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame()

    return df[
        [
            "id",
            "Gün",
            "Saat",
            "Kod",
            "Ders",
            "Hoca",
            "Sınıf",
            "Room",
            "room_type",
            "room_equipment",
            "students",
            "room_capacity",
            "room_ok",
            "over_by",
        ]
    ]


st.set_page_config(page_title="AI Ders Programı", layout="wide")
st.markdown(
    """
<style>
div[data-testid="stMarkdownContainer"] h1 {
    font-size: 2rem;
}
div[data-testid="stMarkdownContainer"] h3 {
    border-left: 5px solid #1f6feb;
    padding-left: 10px;
}
.guide-box {
    border: 1px solid #d0d7de;
    border-radius: 10px;
    padding: 12px 14px;
    background: #f6f8fa;
    margin-bottom: 10px;
}
</style>
""",
    unsafe_allow_html=True,
)

st.title("Ders Programı Asistanı")
st.caption("Teknik olmayan kullanıcılar için adım adım, anlaşılır ders programı ekranı")
st.markdown(
    """
<div class="guide-box">
<b>Hızlı Kullanım (3 adım)</b><br/>
1) Ders verisini girin veya CSV yükleyin.<br/>
2) İsterseniz kuralları ve salon bilgilerini ekleyin.<br/>
3) Aşağıdaki sürükle-bırak bölümünde düzenleyip sonucu listeden kontrol edin.
</div>
""",
    unsafe_allow_html=True,
)
st.markdown(
        """
### Kurallar
- Sert kurallar:
    - Aynı hoca aynı saatte iki farklı derste olamaz.
    - Aynı sınıf aynı saatte iki farklı derste olamaz.
    - Her dersin haftalık saat yükü kadar oturumu olmalı.
    - Öğle arası 13:00-14:00 saatleri otomatik blokludur.
    - Sınıf için günlük maksimum ders saati aşılamaz (sınav önlemek için).
- Yumuşak kurallar:
    - Aynı hocanın dersleri mümkün olduğunca daha az güne yayılsın.
    - Aynı sınıfın dersleri mümkün olduğunca daha az güne yayılsın.
    - Günlük programda dersler arasındaki boş saatler minimumda tutulsun.
"""
)


with st.sidebar:
    st.header("Optimizasyon Ayarları")
    teacher_weight = st.slider(
        "Hoca derslerini aynı güne toplama ağırlığı",
        min_value=1,
        max_value=20,
        value=8,
    )
    class_weight = st.slider(
        "Sınıf derslerini aynı güne toplama ağırlığı",
        min_value=1,
        max_value=20,
        value=5,
    )
    gap_weight = st.slider(
        "Boşluk cezası ağırlığı (hoca ve sınıf)",
        min_value=0,
        max_value=20,
        value=4,
        help="Dersler arasındaki boş saatleri azaltmak için kullanılır. 0 = kapalı.",
    )
    max_daily = st.slider(
        "Günlük maksimum ders saati (sınıf)",
        min_value=2,
        max_value=8,
        value=6,
        help="Bir sınıfın aynı gün içinde alabileceği maksimum ders saati.",
    )
    time_limit = st.slider(
        "Çözüm süresi sınırı (saniye)",
        min_value=2,
        max_value=30,
        value=8,
    )
    st.markdown("---")
    st.write("**Departman filtresi (opsiyonel)**")
    # placeholder for departments - will be initialized after CSV/editor
    st.session_state.setdefault("dept_selected", [])

st.subheader("1) Ders Verisini Girin")
default_df = pd.DataFrame(
    [
        {"code": "MAT101", "name": "Matematik I", "teacher": "Dr. Aylin", "class": "1A", "weekly_hours": 3},
        {"code": "FIZ101", "name": "Fizik I", "teacher": "Dr. Mehmet", "class": "1A", "weekly_hours": 2},
        {"code": "BLM101", "name": "Programlama", "teacher": "Dr. Aylin", "class": "1B", "weekly_hours": 3},
        {"code": "IST101", "name": "İstatistik", "teacher": "Dr. Ece", "class": "1B", "weekly_hours": 2},
        {"code": "YZM201", "name": "Veri Yapıları", "teacher": "Dr. Can", "class": "2A", "weekly_hours": 3},
        {"code": "YZM202", "name": "Algoritmalar", "teacher": "Dr. Can", "class": "2A", "weekly_hours": 2},
    ]
)

uploaded = st.file_uploader("CSV yükle (code,name,teacher,class,weekly_hours)", type=["csv"])
if uploaded is not None:
    try:
        raw_df = safe_read_csv(uploaded)
        raw_df.columns = [str(col).strip() for col in raw_df.columns]
    except Exception as exc:
        st.error(f"CSV okunamadı: {exc}")
        raw_df = default_df.copy()
else:
    raw_df = default_df.copy()

if "group" in raw_df.columns and "class" not in raw_df.columns:
    raw_df = raw_df.rename(columns={"group": "class"})

edited_df = st.data_editor(
    raw_df,
    num_rows="dynamic",
    width="stretch",
    hide_index=True,
)

required_cols = ["code", "name", "teacher", "class", "weekly_hours"]
missing = [c for c in required_cols if c not in edited_df.columns]
if missing:
    st.error(f"Eksik sütunlar: {', '.join(missing)}")
    st.stop()

st.caption("Program, veri veya ayarlar değiştiğinde otomatik güncellenir.")

if "builder_pieces" not in st.session_state:
    st.session_state.builder_pieces = []
if "puzzle_rules" not in st.session_state:
    st.session_state.puzzle_rules = []

try:
    courses = []
    for _, row in edited_df.iterrows():
        if pd.isna(row["code"]) or pd.isna(row["teacher"]) or pd.isna(row["class"]):
            continue

        try:
            weekly_hours = round(float(row["weekly_hours"]))
        except Exception:
            continue

        if weekly_hours <= 0:
            continue

        # department optional
        dept_val = ""
        if "department" in edited_df.columns and not pd.isna(row.get("department", "")):
            dept_val = str(row.get("department", "")).strip()

        # apply department filter if user selected any
        selected_depts = st.session_state.get("dept_selected", [])
        if selected_depts:
            if dept_val not in selected_depts:
                continue

        courses.append(
            Course(
                code=str(row["code"]).strip(),
                name=str(row["name"]).strip(),
                teacher=str(row["teacher"]).strip(),
                class_name=str(row["class"]).strip(),
                department=dept_val,
                weekly_hours=weekly_hours,
            )
        )

    if not courses:
        st.warning("Geçerli ders verisi bulunamadı.")
        st.stop()

    st.subheader("2) Kural Ekle (İsteğe Bağlı)")
    st.caption("Parçaları ekleyin, değerleri seçin, sonra kuralı 'olsun/olmasın' olarak kaydedin.")

    teacher_names = sorted({course.teacher for course in courses})
    class_names = sorted({course.class_name for course in courses})
    course_options = sorted({f"{course.code} | {course.name}" for course in courses})
    # derive department list from edited_df if present
    department_options = []
    if "department" in edited_df.columns:
        department_options = sorted({str(x).strip() for x in edited_df["department"].dropna() if str(x).strip()})
    if department_options:
        sel = st.sidebar.multiselect("Departmanları seç (boş = hepsi)", department_options, default=department_options)
        st.session_state["dept_selected"] = sel
    
    # --- Sınıf öğrenci sayıları ve salonlar (opsiyonel) ---
    st.subheader("3) Sınıf ve Salon Bilgileri (İsteğe Bağlı)")
    st.caption("Öğrenci sayısı ve salon kapasitesi girildiğinde kapasite kontrolü daha doğru olur.")

    class_info_df = pd.DataFrame(
        [
            {"class_name": cname, "students": 30, "mandatory_attendance": 0}
            for cname in class_names
        ]
    )

    edited_class_info = st.data_editor(
        class_info_df,
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        key="class_info_editor",
    )

    st.markdown("**Salonlar (rooms)**")
    default_rooms = pd.DataFrame([{"room": "Salon A", "capacity": 35}])
    uploaded_rooms = st.file_uploader("Salon CSV yükle (room,capacity)", type=["csv"], key="rooms_upload")
    if uploaded_rooms is not None:
        try:
            rooms_df = safe_read_csv(uploaded_rooms)
            rooms_df.columns = [str(c).strip() for c in rooms_df.columns]
            if "room" not in rooms_df.columns or "capacity" not in rooms_df.columns:
                st.warning("CSV'de 'room' ve 'capacity' sütunları olmalı. Varsayılan salon kullanılacak.")
                rooms_df = default_rooms.copy()
        except Exception:
            st.warning("Salon CSV okunamadı; varsayılan salon kullanılacak.")
            rooms_df = default_rooms.copy()
    else:
        rooms_df = default_rooms.copy()

    rooms_df = st.data_editor(rooms_df, num_rows="dynamic", width="stretch", hide_index=True, key="rooms_editor")

    over_percent = st.sidebar.slider(
        "Salon kapasitesi için izin verilen yüzde fazlalık",
        min_value=0,
        max_value=100,
        value=0,
        help="Örneğin 10% girerseniz salon kapasitesi *1.1 olarak değerlendirilir (opsiyonel).",
    )

    capacity_check_mandatory_only = st.checkbox(
        "Kapasite kontrolünü sadece devam zorunluluğu olan öğrenciler üzerinden yap",
        value=False,
    )

    listing_by = st.selectbox("Listelemeyi grupla:", ["Hoca", "Ders", "Sınıf", "Salon"], key="listing_by")

    st.markdown("**Kural Dikdörtgeni**")
    if st.session_state.builder_pieces:
        human_pieces = [RULE_PIECE_LABELS[piece] for piece in st.session_state.builder_pieces]
        st.info("  →  ".join(human_pieces))
    else:
        st.info("(Boş) Parçaları aşağıdaki butonlardan ekleyin.")

    st.markdown("**Yapboz Parçaları**")
    cols = st.columns(len(RULE_PIECES) + 1)
    for idx, piece in enumerate(RULE_PIECES):
        if cols[idx].button(RULE_PIECE_LABELS[piece], key=f"piece_{piece}"):
            if piece not in st.session_state.builder_pieces:
                st.session_state.builder_pieces.append(piece)
                st.rerun()
    if cols[-1].button("Parçaları Sıfırla", key="pieces_reset"):
        st.session_state.builder_pieces = []
        st.rerun()

    builder_values = {}
    if st.session_state.builder_pieces:
        st.markdown("**Parça Değerleri**")
        for piece in st.session_state.builder_pieces:
            if piece == "teacher":
                builder_values[piece] = st.selectbox("Öğretmen seç", teacher_names, key="builder_teacher")
            elif piece == "day":
                builder_values[piece] = st.selectbox("Gün seç", DAYS, key="builder_day")
            elif piece == "hour":
                hour_options = [f"{hour:02d}:00" for hour in HOURS]
                selected_hour = st.selectbox("Saat seç", hour_options, key="builder_hour")
                builder_values[piece] = int(selected_hour.split(":")[0])
            elif piece == "course":
                selected_course = st.selectbox("Ders seç", course_options, key="builder_course")
                builder_values[piece] = selected_course.split(" | ", 1)[0]
            elif piece == "class":
                builder_values[piece] = st.selectbox("Sınıf seç", class_names, key="builder_class")

        rule_action = st.radio("Kural tipi", ["olsun", "olmasın"], horizontal=True, key="builder_action")
        if st.button("Kuralı Ekle", key="add_puzzle_rule"):
            if not st.session_state.builder_pieces:
                st.warning("Önce en az bir parça eklemelisin.")
            else:
                rule = {
                    "pieces": list(st.session_state.builder_pieces),
                    "values": dict(builder_values),
                    "require": rule_action == "olsun",
                }
                st.session_state.puzzle_rules.append(rule)
                st.success("Kural eklendi.")

    if st.session_state.puzzle_rules:
        with st.expander("Aktif Yapboz Kuralları", expanded=True):
            for idx, rule in enumerate(st.session_state.puzzle_rules, start=1):
                parts = []
                for piece in rule["pieces"]:
                    label = RULE_PIECE_LABELS[piece]
                    value = rule["values"].get(piece)
                    if piece == "hour" and value is not None:
                        value = f"{int(value):02d}:00"
                    parts.append(f"{label}: {value}")
                suffix = "olsun" if rule["require"] else "olmasın"
                st.write(f"{idx}. {' | '.join(parts)} → {suffix}")

            if st.button("Tüm yapboz kurallarını temizle", key="clear_puzzle_rules"):
                st.session_state.puzzle_rules = []
                st.rerun()

    # Tek bir isimde toplanıp kapasiteyi aşan hoca etiketlerini sınıf bazında ayır.
    # Böylece "hoca havuzu" gibi kullanılan satırlar gereksiz şekilde çakışmaz.
    slots_per_week = len(DAYS) * len(HOURS)
    raw_teacher_loads = defaultdict(int)
    for course in courses:
        raw_teacher_loads[course.teacher] += course.weekly_hours

    overloaded_raw_teachers = {
        teacher for teacher, hours in raw_teacher_loads.items() if hours > slots_per_week
    }

    courses_for_solver = []
    pooled_count = 0
    for course in courses:
        teacher_label = course.teacher.strip()
        internal_teacher = teacher_label

        if teacher_label in overloaded_raw_teachers:
            internal_teacher = f"{teacher_label} || {course.class_name}"
            pooled_count += 1

        courses_for_solver.append(
            Course(
                code=course.code,
                name=course.name,
                teacher=internal_teacher,
                class_name=course.class_name,
                weekly_hours=course.weekly_hours,
            )
        )

    if pooled_count > 0:
        st.info(
            "Kapasiteyi aşan hoca etiketleri sınıf bazında ayrıştırılarak çözüldü "
            f"({pooled_count} ders satırı)."
        )

    teacher_loads = defaultdict(int)
    for course in courses_for_solver:
        teacher_loads[course.teacher] += course.weekly_hours

    overloaded = [(teacher, hours) for teacher, hours in teacher_loads.items() if hours > slots_per_week]
    if overloaded:
        overload_text = ", ".join(
            f"{teacher.split(' || ')[0]}: {hours} saat" for teacher, hours in overloaded
        )
        st.error(
            "Program kurulamadı: bazı hocaların haftalık yükü teknik kapasiteyi aşıyor "
            f"({slots_per_week} slot/hafta). {overload_text}"
        )
        st.stop()

    hard_rules = []
    solver_teacher_names = {course.teacher for course in courses_for_solver}
    for rule in st.session_state.puzzle_rules:
        values = rule.get("values", {})
        raw_teacher = values.get("teacher")

        matched_teachers = [None]
        if raw_teacher:
            matched_teachers = [
                name
                for name in solver_teacher_names
                if name == raw_teacher or name.startswith(f"{raw_teacher} || ")
            ]
            if not matched_teachers:
                matched_teachers = [raw_teacher]

        for teacher_name in matched_teachers:
            hard_rules.append(
                {
                    "teacher": teacher_name,
                    "day": values.get("day"),
                    "hour": values.get("hour"),
                    "course_code": values.get("course"),
                    "class_name": values.get("class"),
                    "require": bool(rule.get("require", False)),
                }
            )

    assignments, status_text = solve_timetable(
        courses_for_solver,
        weight_teacher_day_compact=teacher_weight,
        weight_class_day_compact=class_weight,
        weight_teacher_gap=gap_weight,
        weight_class_gap=gap_weight,
        max_daily_hours=max_daily,
        hard_rules=hard_rules,
        time_limit_seconds=time_limit,
    )

    if not assignments:
        st.error(status_text)
        st.stop()
    st.success(status_text)

    # persist solver assignments so user can manually adjust without re-solving
    # NOTE: reset stored assignments on each solve to reflect updated course data/uploads
    # ensure preserved moves and history exist
    st.session_state.setdefault("preserved_moves", {})
    st.session_state.setdefault("move_history", [])

    st.session_state.assignments_orig = [
        {
            "id": idx,
            "course_code": a.course_code,
            "course_name": a.course_name,
            "teacher": a.teacher,
            "department": getattr(a, "department", ""),
            "class_name": a.class_name,
            "day": a.day,
            "hour": a.hour,
            "room": getattr(a, "room", ""),
        }
        for idx, a in enumerate(assignments)
    ]
    # NOTE:
    # Do not auto-apply preserved manual moves after every solve. Otherwise,
    # optimization slider changes appear ineffective because old manual states
    # overwrite fresh solver results immediately.

    # copy for modifications
    # Keep user's saved manual edits across reruns, but if solver results
    # changed (e.g. optimization sliders/data/rules changed), refresh mod data.
    prev_mod = st.session_state.get("assignments_mod")
    reset_mod = False
    if not isinstance(prev_mod, list) or not prev_mod:
        reset_mod = True
    else:
        try:
            prev_sig = sorted(
                (
                    int(x.get("id")),
                    str(x.get("course_code", "")),
                    str(x.get("class_name", "")),
                    str(x.get("day", "")),
                    int(x.get("hour")),
                    str(x.get("room", "") or ""),
                )
                for x in prev_mod
            )
            new_sig = sorted(
                (
                    int(x.get("id")),
                    str(x.get("course_code", "")),
                    str(x.get("class_name", "")),
                    str(x.get("day", "")),
                    int(x.get("hour")),
                    str(x.get("room", "") or ""),
                )
                for x in st.session_state.assignments_orig
            )
            if prev_sig != new_sig:
                reset_mod = True
        except Exception:
            reset_mod = True

    if reset_mod:
        st.session_state.assignments_mod = [d.copy() for d in st.session_state.assignments_orig]

    # keep staged in sync when solver output changes (day/hour/room included)
    if "assignments_staged" not in st.session_state or not isinstance(st.session_state.get("assignments_staged"), list):
        st.session_state["assignments_staged"] = [d.copy() for d in st.session_state.get("assignments_mod", [])]
    else:
        # Only rebuild staged if IDs diverge (assignments added/removed by solver).
        # Do NOT rebuild based on day/hour/room differences — that would destroy drag-drop moves.
        try:
            mod_ids_sync = sorted(int(x.get("id")) for x in st.session_state.get("assignments_mod", []))
            staged_ids_sync = sorted(int(x.get("id")) for x in st.session_state.get("assignments_staged", []))
            if mod_ids_sync != staged_ids_sync:
                st.session_state["assignments_staged"] = [d.copy() for d in st.session_state.get("assignments_mod", [])]
        except Exception:
            st.session_state["assignments_staged"] = [d.copy() for d in st.session_state.get("assignments_mod", [])]

    # allow manual adjustments: move selected assignments to another slot
    st.subheader("4) Programı Düzenleyin")
    st.info("En kolay yöntem: 'Gerçek Sürükle-Bırak' bölümünden kartları taşıyın. Değişiklikler anında aşağıdaki listelere yansır.")
    with st.expander("Filtreler (gösterilecek satırları daralt)", expanded=False):
        # derive options from current assignments
        all_teachers = sorted({d["teacher"].split(" || ")[0] for d in st.session_state.assignments_mod})
        all_classes = sorted({d["class_name"] for d in st.session_state.assignments_mod})
        all_courses = sorted({d["course_code"] + ' | ' + d["course_name"] for d in st.session_state.assignments_mod})
        all_depts = sorted({d.get("department", "") for d in st.session_state.assignments_mod if d.get("department", "")})

        sel_teachers = st.multiselect("Öğretmen seç (boş = hepsi)", all_teachers, key="filter_teachers")
        sel_classes = st.multiselect("Sınıf seç (boş = hepsi)", all_classes, key="filter_classes")
        sel_courses = st.multiselect("Ders seç (boş = hepsi)", all_courses, key="filter_courses")
        sel_depts = st.multiselect("Departman seç (boş = hepsi)", all_depts, key="filter_depts")

    with st.expander("Alternatif: Manuel taşı (seç -> hedef gün/saat)", expanded=False):
        assign_options = [
            f"{d['id']}: {d['course_code']} {d['class_name']} — {d['day']} {d['hour']:02d}:00"
            for d in st.session_state.assignments_mod
        ]
        to_move = st.multiselect("Taşınacak oturum(lar)", assign_options, key="move_select")
        move_day = st.selectbox("Hedef gün", DAYS, index=0, key="move_day")
        move_hour = st.selectbox("Hedef saat", [f"{h:02d}:00" for h in HOURS], index=0, key="move_hour")
        force_move = st.checkbox("Çakışmaları zorla (uyarıları yoksay)", value=False, key="force_move_confirm")
        if st.button("Taşı", key="apply_move"):
            if not to_move:
                st.warning("Önce taşınacak oturumu seçiniz.")
            else:
                target_hour = int(move_hour.split(":")[0])
                ids = [int(x.split(":", 1)[0]) for x in to_move]

                # detect conflicts: for each target slot, any other assignment (not being moved)
                # that has same teacher or same class
                conflicts = []
                for mid in ids:
                    # find the assignment object being moved
                    src = next((d for d in st.session_state.assignments_mod if d["id"] == mid), None)
                    if src is None:
                        continue
                    for other in st.session_state.assignments_mod:
                        if other["id"] in ids:
                            continue
                        if other["day"] == move_day and other["hour"] == target_hour:
                            # teacher conflict
                            if other["teacher"].split(" || ")[0] == src["teacher"].split(" || ")[0]:
                                conflicts.append({"type": "teacher", "id": other["id"], "desc": f"Hoca çakışması: {other['teacher'].split(' || ')[0]} ile {other['course_code']}"})
                            # class conflict
                            if other["class_name"] == src["class_name"]:
                                conflicts.append({"type": "class", "id": other["id"], "desc": f"Sınıf çakışması: {other['class_name']} ile {other['course_code']}"})

                if conflicts and not force_move:
                    st.warning("Taşımaya devam etmek bazı çakışmalara neden olacak. 'Çakışmaları zorla' seçeneğini işaretleyerek zorla taşıyabilirsiniz.")
                    for c in conflicts[:10]:
                        st.write(f"- {c['desc']}")
                else:
                    moved = 0
                    change_record = []
                    for d in st.session_state.assignments_mod:
                        if d["id"] in ids:
                            prev = {"id": d["id"], "prev_day": d["day"], "prev_hour": d["hour"], "course_code": d["course_code"], "class_name": d["class_name"]}
                            change_record.append(prev)
                            d["day"] = move_day
                            d["hour"] = target_hour
                            # persist this manual move so it survives a re-solve
                            key = (d["course_code"], d["class_name"])
                            st.session_state["preserved_moves"][key] = {
                                "day": move_day,
                                "hour": target_hour,
                                "room": d.get("room", ""),
                            }
                            moved += 1

                    if moved > 0:
                        # push to history for undo
                        st.session_state["move_history"].append(change_record)
                        st.success(f"{moved} oturum taşındı.")
                    else:
                        st.info("Taşınacak bir oturum bulunamadı.")

        # Undo last move
        if st.button("Geri al (son hareket)", key="undo_move"):
            if st.session_state.get("move_history"):
                last = st.session_state["move_history"].pop()
                restored = 0
                for rec in last:
                    d = next((x for x in st.session_state.assignments_mod if x["id"] == rec["id"]), None)
                    if d:
                        d["day"] = rec["prev_day"]
                        d["hour"] = rec["prev_hour"]
                        # update preserved_moves accordingly (remove if matches original)
                        key = (d["course_code"], d["class_name"])
                        if key in st.session_state["preserved_moves"]:
                            # if restored equals original assignments_orig for this course, remove preserved
                            orig = next((o for o in st.session_state.assignments_orig if o["course_code"] == d["course_code"] and o["class_name"] == d["class_name"]), None)
                            if orig and orig["day"] == d["day"] and orig["hour"] == d["hour"]:
                                del st.session_state["preserved_moves"][key]
                            else:
                                st.session_state["preserved_moves"][key] = {
                                    "day": d["day"],
                                    "hour": d["hour"],
                                    "room": d.get("room", ""),
                                }
                        restored += 1
                st.success(f"{restored} oturum geri alındı.")
            else:
                st.info("Geri alınacak hareket yok.")

        # Reset to original assignments (requires checkbox confirmation)
        reset_confirm = st.checkbox("Onaylıyorum: tüm manuel değişiklikleri sıfırla (geri alınamaz)", value=False, key="reset_confirm_checkbox")
        if st.button("Sıfırla (Orijinale dön)", key="do_reset"):
            if not reset_confirm:
                st.warning("Sıfırlama işlemini onaylamak için onay kutusunu işaretleyin.")
            else:
                # clear preserved moves and history, restore assignments_mod from assignments_orig
                st.session_state["preserved_moves"] = {}
                st.session_state["move_history"] = []
                st.session_state["assignments_mod"] = [d.copy() for d in st.session_state["assignments_orig"]]
                st.success("Manuel değişiklikler temizlendi; orijinal atamalar geri yüklendi.")

        # Preview & commit preserved manual moves as hard rules and re-run solver
        preserved = st.session_state.get("preserved_moves", {})
        selected_preserved = []
        if preserved:
            st.markdown("**Kaydedilmiş manuel taşıma (preserved moves)**")
            preserved_list = [
                {
                    "course_code": code,
                    "class_name": cls,
                    "day": pm.get("day"),
                    "hour": pm.get("hour"),
                }
                for (code, cls), pm in preserved.items()
            ]
            try:
                st.dataframe(pd.DataFrame(preserved_list).fillna("-"), width="stretch")
            except Exception:
                for p in preserved_list:
                    st.write(f"- {p['course_code']} | {p['class_name']} → {p['day']} {p['hour']}:00")

            # selection control: choose which preserved moves to include; empty = all
            opts = [f"{p['course_code']} | {p['class_name']} — {p['day']} {int(p['hour']):02d}:00" for p in preserved_list]
            sel = st.multiselect("Commitlenecek hareketleri seç (boş = tümü)", opts, default=opts, key="preserved_select")

            # build selected keys list
            sel_keys = []
            label_to_key = {f"{p['course_code']} | {p['class_name']} — {p['day']} {int(p['hour']):02d}:00": (p['course_code'], p['class_name']) for p in preserved_list}
            for s in sel:
                if s in label_to_key:
                    sel_keys.append(label_to_key[s])

            if st.button("Önizle: Oluşturulacak sert kuralları göster", key="preview_rules"):
                extra_rules = []
                keys_to_use = sel_keys if sel_keys else list(preserved.keys())
                for key in keys_to_use:
                    pm = preserved.get(key)
                    extra_rules.append({
                        "teacher": None,
                        "day": pm.get("day"),
                        "hour": pm.get("hour"),
                        "course_code": key[0],
                        "class_name": key[1],
                        "require": True,
                    })
                # detect simple conflicts if these rules were applied (teacher/class double-booking)
                conflicts_preview = []
                for r in extra_rules:
                    # find source assignment details
                    src = next((x for x in st.session_state.get("assignments_mod", []) if x["course_code"] == r["course_code"] and x["class_name"] == r["class_name"]), None)
                    if not src:
                        continue
                    for other in st.session_state.get("assignments_mod", []):
                        if other["id"] == src["id"]:
                            continue
                        if other["day"] == r["day"] and other["hour"] == r["hour"]:
                            # teacher conflict
                            if other["teacher"].split(" || ")[0] == src["teacher"].split(" || ")[0]:
                                conflicts_preview.append(f"Hoca çakışması: {src['course_code']} ile {other['course_code']} aynı {r['day']} {int(r['hour']):02d}:00")
                            # class conflict
                            if other["class_name"] == src["class_name"]:
                                conflicts_preview.append(f"Sınıf çakışması: {src['class_name']} aynı {r['day']} {int(r['hour']):02d}:00")

                with st.expander("Önizleme: eklenecek sert kurallar", expanded=True):
                    for r in extra_rules:
                        st.write(f"- {r['course_code']} | {r['class_name']} → {r['day']} {int(r['hour']):02d}:00 (zorunlu)")
                    if conflicts_preview:
                        st.markdown("**Uyarılar (öngörülen çakışmalar)**")
                        for c in conflicts_preview:
                            st.write(f"- {c}")

            if st.button("Seçilen(leri) sert kurala çevir ve yeniden çöz", key="commit_and_resolve_selected"):
                keys_to_use = sel_keys if sel_keys else list(preserved.keys())
                if not keys_to_use:
                    st.info("Seçili bir hareket yok; işlem iptal edildi.")
                else:
                    extra_rules = []
                    for key in keys_to_use:
                        pm = preserved.get(key)
                        extra_rules.append({
                            "teacher": None,
                            "day": pm.get("day"),
                            "hour": pm.get("hour"),
                            "course_code": key[0],
                            "class_name": key[1],
                            "require": True,
                        })

                    combined_rules = list(hard_rules) + extra_rules
                    with st.spinner("Sert kurallarla yeniden çözülüyor..."):
                        new_assignments, new_status = solve_timetable(
                            courses_for_solver,
                            weight_teacher_day_compact=teacher_weight,
                            weight_class_day_compact=class_weight,
                            weight_teacher_gap=gap_weight,
                            weight_class_gap=gap_weight,
                            max_daily_hours=max_daily,
                            hard_rules=combined_rules,
                            time_limit_seconds=time_limit,
                        )

                    if not new_assignments:
                        st.error(f"Yeniden çözüm başarısız: {new_status}")
                    else:
                        st.success(new_status)
                        st.session_state.assignments_orig = [
                            {
                                "id": idx,
                                "course_code": a.course_code,
                                "course_name": a.course_name,
                                "teacher": a.teacher,
                                "department": getattr(a, "department", ""),
                                "class_name": a.class_name,
                                "day": a.day,
                                "hour": a.hour,
                                "room": getattr(a, "room", ""),
                            }
                            for idx, a in enumerate(new_assignments)
                        ]
                        # re-apply preserved for remaining keys
                        # remove committed keys from preserved_moves
                        keys_to_remove = keys_to_use if 'keys_to_use' in locals() else []
                        if keys_to_remove:
                            for k in keys_to_remove:
                                try:
                                    st.session_state["preserved_moves"].pop(k, None)
                                except Exception:
                                    pass
                        # re-apply preserved for remaining keys (if any)
                        if st.session_state.get("preserved_moves"):
                            preserved = st.session_state["preserved_moves"]
                            for d in st.session_state.assignments_orig:
                                key = (d["course_code"], d["class_name"])
                                if key in preserved:
                                    pm = preserved[key]
                                    d["day"] = pm.get("day", d["day"]) or d["day"]
                                    d["hour"] = pm.get("hour", d["hour"]) or d["hour"]
                                    d["room"] = pm.get("room", d.get("room", "")) or d.get("room", "")

                        st.session_state.assignments_mod = [d.copy() for d in st.session_state.assignments_orig]
                        st.session_state["move_history"] = []
                        maybe_rerun()
        else:
            st.info("Kaydedilmiş manuel taşıma yok.")

    # build dataframe from modified assignments
    # Use staged assignments if present so previews reflect temporary drag/click moves
    staged_present = st.session_state.get("assignments_staged")
    source_assigns = st.session_state.get("assignments_mod", [])
    if staged_present:
        # Only refresh staged if IDs diverge (assignments added/removed).
        # Do NOT refresh based on position differences — staged legitimately holds drag-drop moves.
        try:
            mod_ids = sorted(int(x.get("id")) for x in source_assigns)
            staged_ids = sorted(int(x.get("id")) for x in staged_present)
        except Exception:
            mod_ids = []
            staged_ids = []

        if mod_ids != staged_ids:
            st.session_state["assignments_staged"] = [d.copy() for d in source_assigns]
            staged_present = st.session_state.get("assignments_staged")

    def build_table_df(assignments_list):
        return pd.DataFrame(
            [
                {
                    "id": a.day if False else a.__dict__.get('id'),
                    "Gün": a.day,
                    "Saat": f"{a.hour:02d}:00-{a.hour+1:02d}:00",
                    "Ders": a.course_name,
                    "Kod": a.course_code,
                    "Hoca": a.teacher.split(" || ")[0],
                    "Departman": getattr(a, "department", ""),
                    "Sınıf": a.class_name,
                    "Room": getattr(a, "room", ""),
                }
                for a in assignments_list
            ]
        )

    current_assignments = [SimpleNamespace(**d) for d in (staged_present if staged_present is not None else source_assigns)]
    table_df = build_table_df(current_assignments)

    # Pre-seed room values so drag cards start with the same rooms shown in detailed list logic.
    try:
        pre_rooms_df = assign_rooms_to_schedule(
            current_assignments,
            rooms_df,
            edited_class_info,
            over_percent,
            capacity_check_mandatory_only,
            enrolled_map=None,
        )
        if pre_rooms_df is not None and not pre_rooms_df.empty and "id" in pre_rooms_df.columns:
            id_to_room = {
                int(r["id"]): str(r.get("Room", "") or "")
                for _, r in pre_rooms_df.iterrows()
                if pd.notna(r.get("id"))
            }
            if id_to_room:
                for row in st.session_state.get("assignments_mod", []):
                    rid = int(row.get("id")) if row.get("id") is not None else None
                    if rid is not None and (not str(row.get("room", "") or "")) and rid in id_to_room:
                        row["room"] = id_to_room[rid]
                for row in st.session_state.get("assignments_staged", []):
                    rid = int(row.get("id")) if row.get("id") is not None else None
                    if rid is not None and (not str(row.get("room", "") or "")) and rid in id_to_room:
                        row["room"] = id_to_room[rid]
    except Exception:
        pass

    # Real drag-and-drop component (uses custom Streamlit component).
    with st.expander("Gerçek Sürükle-Bırak (Önerilen)", expanded=True):
        try:
            from st_dragdrop_component import st_dragdrop

            st.caption("Kartı tutup uygun gün/saat hücresine bırakın. Salon kutusunu başka karta bırakarak salonları da değiştirebilirsiniz.")

            raw_assigns = st.session_state.get("assignments_staged") or st.session_state.get("assignments_mod", []) or []
            sanitized = []
            for d in raw_assigns:
                try:
                    sanitized.append(
                        {
                            "id": int(d.get("id")),
                            "course_code": str(d.get("course_code", "")),
                            "course_name": str(d.get("course_name", "")),
                            "teacher": str(d.get("teacher", "")),
                            "class_name": str(d.get("class_name", "")),
                            "day": str(d.get("day", "")),
                            "hour": int(d.get("hour")) if d.get("hour") is not None else None,
                            "room": str(d.get("room", "") or ""),
                        }
                    )
                except Exception:
                    continue

            # Fill missing rooms directly on sanitized list
            _room_err = ""
            try:
                _san_assigns = [SimpleNamespace(**s) for s in sanitized]
                _pre_df = assign_rooms_to_schedule(
                    _san_assigns,
                    rooms_df,
                    edited_class_info,
                    over_percent,
                    capacity_check_mandatory_only,
                    enrolled_map=None,
                )
                if _pre_df is not None and not _pre_df.empty and "id" in _pre_df.columns:
                    _id2room = {
                        int(r["id"]): str(r.get("Room", "") or "")
                        for _, r in _pre_df.iterrows()
                        if pd.notna(r.get("id"))
                    }
                    for item in sanitized:
                        if not item["room"] and item["id"] in _id2room:
                            item["room"] = _id2room[item["id"]]
            except Exception as _e:
                _room_err = str(_e)

            room_options = []
            try:
                if rooms_df is not None and not rooms_df.empty and "room" in rooms_df.columns:
                    room_options = [str(x).strip() for x in rooms_df["room"].dropna().tolist() if str(x).strip()]
            except Exception:
                room_options = []

            if _room_err:
                st.caption(f"[Salon ön-atama hatası: {_room_err}]")

            class_options = sorted({str(x.get("class_name", "")) for x in sanitized if str(x.get("class_name", ""))})
            moves = st_dragdrop(sanitized, DAYS, HOURS, room_options, class_options, height=700, key="dragdrop_component_main")

            if isinstance(moves, dict) and moves.get("error"):
                st.warning(f"Drag-drop bileşen hatası: {moves.get('error')}")
            elif isinstance(moves, list) and moves:
                staged = [d.copy() for d in (st.session_state.get("assignments_staged") or st.session_state.get("assignments_mod", []))]
                pending_map = {}
                changed = 0
                rejected = []
                staged_map = {}
                for srow in staged:
                    try:
                        staged_map[int(srow.get("id"))] = srow
                    except Exception:
                        continue

                for mv in moves:
                    try:
                        aid = int(mv.get("id"))
                        new_day = mv.get("day")
                        new_hour = int(mv.get("hour"))
                        new_room = str(mv.get("room", "") or "")
                        staged_row = staged_map.get(aid)
                        if not staged_row:
                            continue

                        prev_day = staged_row.get("day")
                        try:
                            prev_hour = int(staged_row.get("hour"))
                        except Exception:
                            prev_hour = staged_row.get("hour")
                        prev_room = str(staged_row.get("room", "") or "")

                        # Ignore repeats coming from component rerenders.
                        if prev_day == new_day and prev_hour == new_hour and prev_room == new_room:
                            continue

                        # Server-side conflict control for drag-drop consistency.
                        conflict = None
                        for other in staged:
                            if int(other.get("id")) == aid:
                                continue
                            try:
                                other_day = other.get("day")
                                other_hour = int(other.get("hour"))
                            except Exception:
                                continue
                            if other_day == new_day and other_hour == new_hour:
                                if str(other.get("class_name", "")) == str(staged_row.get("class_name", "")):
                                    conflict = f"Sınıf çakışması: {staged_row.get('class_name', '')}"
                                    break
                                if str(other.get("teacher", "")).split(" || ")[0] == str(staged_row.get("teacher", "")).split(" || ")[0]:
                                    conflict = f"Hoca çakışması: {str(staged_row.get('teacher', '')).split(' || ')[0]}"
                                    break
                        if conflict:
                            rejected.append(f"{staged_row.get('course_code', '')}: {conflict}")
                            continue

                        pending_map[aid] = {
                            "id": staged_row.get("id"),
                            "prev_day": prev_day,
                            "prev_hour": prev_hour,
                            "prev_room": prev_room,
                            "course_code": staged_row.get("course_code", ""),
                            "class_name": staged_row.get("class_name", ""),
                        }
                        staged_row["day"] = new_day
                        staged_row["hour"] = new_hour
                        staged_row["room"] = new_room
                        changed += 1
                    except Exception:
                        continue

                if rejected:
                    st.warning("Bazı sürükle-bırak değişiklikleri çakışma nedeniyle uygulanmadı:")
                    for msg in rejected[:8]:
                        st.write(f"- {msg}")

                if changed:
                    st.session_state["assignments_staged"] = staged
                    st.session_state["cell_pending_changes"] = list(pending_map.values())
                    # Refresh data sources in the same rerun so list/weekly table updates instantly.
                    current_assignments = [SimpleNamespace(**d) for d in st.session_state.get("assignments_staged", [])]
                    table_df = build_table_df(current_assignments)
                    st.success(f"{changed} değişiklik alındı.")
        except Exception as comp_exc:
            st.error(f"Gerçek sürükle-bırak bileşeni yüklenemedi: {comp_exc}")
            st.info("Geçici olarak 'Güvenli Taşıma (Streamlit)' bölümünü kullanabilirsiniz.")

    # debug: show current assignments_mod and table_df preview before room assignment
    # Debug outputs removed from UI. Set `st.session_state['debug']=True` and
    # add a guarded block here if you later want to re-enable debug printing.

    # Post-process: salon ataması ve kapasite kontrolü
    # build enrolled_map from uploaded/edited course data if present
    enrolled_map = {}
    if "enrolled" in edited_df.columns:
        for _, r in edited_df.iterrows():
            try:
                code = str(r.get("code", "")).strip()
                class_name = str(r.get("class", "")).strip()
                val = r.get("enrolled")
                if pd.notna(val):
                    enrolled_map[(code, class_name)] = int(val)
                    enrolled_map[code] = int(val)
            except Exception:
                continue

    rooms_assigned_df = assign_rooms_to_schedule(
        current_assignments,
        rooms_df,
        edited_class_info,
        over_percent,
        capacity_check_mandatory_only,
        enrolled_map=enrolled_map if enrolled_map else None,
    )

    # apply filters from the filter expander
    try:
        sel_teachers = st.session_state.get("filter_teachers", [])
        sel_classes = st.session_state.get("filter_classes", [])
        sel_courses = st.session_state.get("filter_courses", [])
        sel_depts = st.session_state.get("filter_depts", [])
    except Exception:
        sel_teachers = sel_classes = sel_courses = sel_depts = []

    def apply_filters_df(df):
        if df is None or df.empty:
            return df
        out = df.copy()
        if sel_teachers:
            out = out[out["Hoca"].isin(sel_teachers)]
        if sel_classes:
            out = out[out["Sınıf"].isin(sel_classes)]
        if sel_depts:
            out = out[out["Departman"].isin(sel_depts)]
        if sel_courses:
            # sel_courses are in format 'CODE | name'
            codes = [s.split(" | ", 1)[0] for s in sel_courses]
            out = out[out["Kod"].isin(codes)]
        return out

    filtered_rooms = apply_filters_df(rooms_assigned_df) if not rooms_assigned_df.empty else pd.DataFrame()
    filtered_table = apply_filters_df(table_df)

    st.subheader("5) Sonuçlar: Detaylı Liste")
    if not filtered_rooms.empty:
        st.dataframe(filtered_rooms.fillna("-"), width="stretch", hide_index=True)
    else:
        st.dataframe(filtered_table.fillna("-"), width="stretch", hide_index=True)

    # Özet: kapasite taşmaları
    if not rooms_assigned_df.empty:
        overflows = rooms_assigned_df[rooms_assigned_df["room_ok"] == False]
        st.markdown("**Kapasite Özetleri**")
        st.write(f"Toplam oturum: {len(rooms_assigned_df)}, Kapasiteyi aşan oturum: {len(overflows)}")
        if not overflows.empty:
            with st.expander("Kapasiteyi aşan oturumların örnekleri", expanded=False):
                st.dataframe(overflows.head(20).fillna("-"), width="stretch", hide_index=True)

    # Listelemeyi grupla ve göster
    st.subheader("6) Sonuçlar: Gruplu Liste")
    list_col_map = {"Hoca": "Hoca", "Ders": "Kod", "Sınıf": "Sınıf", "Salon": "Room"}
    group_col = list_col_map.get(listing_by, "Hoca")
    display_df = filtered_rooms if not filtered_rooms.empty else filtered_table
    if not display_df.empty:
        grouped = display_df.groupby(group_col)
        for name, group in grouped:
            with st.expander(f"{listing_by}: {name} ({len(group)} oturum)"):
                st.dataframe(group.sort_values(["Gün", "Saat"]).fillna("-"), width="stretch", hide_index=True)

    st.subheader("7) Sonuçlar: Haftalık Program")
    pivot = filtered_table.copy()
    pivot["Hücre"] = (
        pivot["Kod"] + "\n" + pivot["Ders"] + "\n" + pivot["Hoca"] + " (" + pivot["Sınıf"] + ")"
    )
    # if multiple assignments fall into same cell, join them so user sees all
    try:
        weekly = pivot.pivot_table(index="Saat", columns="Gün", values="Hücre", aggfunc=lambda x: "\n---\n".join(x.astype(str)))
    except Exception:
        weekly = pivot.pivot_table(index="Saat", columns="Gün", values="Hücre", aggfunc="first")

    day_order = [d for d in DAYS if d in weekly.columns]
    weekly = weekly.reindex(columns=day_order)

    hour_order = [f"{h:02d}:00-{h+1:02d}:00" for h in HOURS]
    weekly = weekly.reindex(hour_order)

    st.dataframe(weekly.fillna("-"), width="stretch")

    # Debug / diagnostics: show counts and any missing IDs
    with st.expander("Durum: atama sayıları ve eksik ID'ler (debug)", expanded=False):
        try:
            orig_ids = {int(x["id"]) for x in st.session_state.get("assignments_orig", [])}
        except Exception:
            orig_ids = set()
        try:
            mod_ids = {int(x["id"]) for x in st.session_state.get("assignments_mod", [])}
        except Exception:
            mod_ids = set()
        try:
            staged_ids = {int(x["id"]) for x in st.session_state.get("assignments_staged", [])}
        except Exception:
            staged_ids = set()

        st.write(f"Orijinal atama sayısı: {len(orig_ids)}")
        st.write(f"Geçerli mod atama sayısı: {len(mod_ids)}")
        st.write(f"Staged atama sayısı: {len(staged_ids)}")

        # IDs present in orig but missing in mod/staged
        missing_in_mod = sorted(list(orig_ids - mod_ids))
        missing_in_staged = sorted(list(orig_ids - staged_ids))
        if missing_in_mod:
            st.warning(f"Orijinalde olup modda eksik ID'ler: {missing_in_mod[:50]}")
        else:
            st.success("Orijinal → mod: tüm ID'ler mevcut")
        if staged_ids and missing_in_staged:
            st.warning(f"Orijinalde olup staged'de eksik ID'ler: {missing_in_staged[:50]}")
        elif staged_ids:
            st.success("Staged, orijinal atamalarla uyumlu")

    # Güvenli Streamlit-only taşıma: kaynak hücre seç -> hedef hücre seç -> Kaydet ile uygula
    with st.expander("Güvenli Taşıma (Streamlit) — hücre seç → hedef seç, Kaydet ile uygula", expanded=False):
        # staged copy: kullanıcı değişiklikleri burada tutulur; Kaydet ile assignments_mod'a uygulanır
        if "assignments_staged" not in st.session_state:
            st.session_state["assignments_staged"] = [d.copy() for d in st.session_state.get("assignments_mod", [])]

        staged = st.session_state["assignments_staged"]

        st.markdown("**Kullanım:** Önce taşımak istediğiniz dolu hücreye tıklayın (kaynak). Sonra hedef hücreye tıklayın. "
                    "Taşımalar geçici olarak kaydedilir; 'Kaydet' ile kalıcı yapılır veya 'İptal' ile geri alınır.")

        # helper: deterministic color by class
        def class_color(name: str) -> str:
            if not name:
                return "#eeeeee"
            h = 0
            for ch in name:
                h = (h * 31 + ord(ch)) % 360
            return f"hsl({h},65%,80%)"

        # show header row (hours column + days)
        header_cols = st.columns(len(DAYS) + 1)
        header_cols[0].write("Saat")
        for i, day in enumerate(DAYS):
            header_cols[i + 1].markdown(f"**{day}**")

        # ensure selection state
        sel = st.session_state.get("cell_sel")

        # render rows for each hour
        for hour in HOURS:
            row_cols = st.columns(len(DAYS) + 1)
            row_cols[0].write(f"{hour:02d}:00")
            for i, day in enumerate(DAYS):
                cell_assign = next((a for a in staged if a.get("day") == day and int(a.get("hour")) == hour), None)
                label = "" if cell_assign is None else f"{cell_assign.get('course_code')} ({cell_assign.get('class_name')})"
                btn_key = f"cell_btn__{day}__{hour}"

                # color box for class
                if cell_assign:
                    color = class_color(str(cell_assign.get("class_name", "")))
                    tooltip = f"{cell_assign.get('course_code')} | {cell_assign.get('course_name', '')}\n{cell_assign.get('teacher', '')}\nSınıf: {cell_assign.get('class_name', '')}".replace('"','')
                    row_cols[i + 1].markdown(f"<div style='background:{color};padding:6px;border-radius:6px;text-align:center' title='{tooltip}'>{label}</div>", unsafe_allow_html=True)
                else:
                    row_cols[i + 1].write("-")

                # mark selected source visually using emoji in label
                if sel and sel.get("type") == "source" and sel.get("id") is not None:
                    src = next((a for a in staged if a.get("id") == sel.get("id")), None)
                    if src and src.get("day") == day and int(src.get("hour")) == hour:
                        display_label = "🔵 " + (label or "-")
                    else:
                        display_label = label or "-"
                else:
                    display_label = label or "-"

                if row_cols[i + 1].button(display_label, key=btn_key):
                    # update focused cell details for side panel
                    if cell_assign:
                        st.session_state["cell_focus"] = {
                            "id": int(cell_assign.get("id")),
                            "course_code": cell_assign.get("course_code"),
                            "course_name": cell_assign.get("course_name"),
                            "teacher": cell_assign.get("teacher"),
                            "class_name": cell_assign.get("class_name"),
                            "day": day,
                            "hour": hour,
                        }

                    # click handling: if no source selected, this selects source
                    if not st.session_state.get("cell_sel"):
                        if cell_assign:
                            st.session_state["cell_sel"] = {"type": "source", "id": int(cell_assign.get("id")), "day": day, "hour": hour}
                            maybe_rerun()
                        else:
                            st.info("Boş hücre seçildi; önce dolu bir hücre seçin.")
                    else:
                        # source already selected -> treat this click as target
                        cur = st.session_state.get("cell_sel")
                        if cur.get("type") == "source":
                            src_id = cur.get("id")
                            src_row = next((a for a in staged if a.get("id") == src_id), None)
                            if not src_row:
                                st.warning("Kaynak bulunamadı; tekrar seçiniz.")
                            else:
                                # apply move to staged copy
                                prev = {"id": src_row["id"], "prev_day": src_row["day"], "prev_hour": int(src_row["hour"]), "course_code": src_row["course_code"], "class_name": src_row["class_name"]}
                                src_row["day"] = day
                                src_row["hour"] = hour
                                st.session_state.setdefault("cell_pending_changes", []).append(prev)
                                # clear selection and refresh view
                                st.session_state.pop("cell_sel", None)
                                maybe_rerun()

        # show pending changes and Save/Cancel controls
        pending = st.session_state.get("cell_pending_changes", [])
        if pending:
            st.markdown("**Bekleyen (geçici) değişiklikler:**")
            for rec in pending:
                prev_room = rec.get("prev_room", "")
                room_txt = f" | Salon: {prev_room}" if prev_room else ""
                st.write(f"- {rec['course_code']}: {rec['prev_day']} {int(rec['prev_hour']):02d}:00{room_txt} → yeni yer")

            c1, c2 = st.columns([1, 1])
            if c1.button("Kaydet (kalıcı)", key="cell_save"):
                applied = 0
                change_record = []
                pending_list = st.session_state.pop("cell_pending_changes", [])
                for rec in pending_list:
                    # find staged row and corresponding mod row
                    staged_row = next((a for a in st.session_state.get("assignments_staged", []) if a.get("id") == rec["id"]), None)
                    if not staged_row:
                        continue
                    mod_row = next((a for a in st.session_state.get("assignments_mod", []) if a.get("id") == rec["id"]), None)
                    if not mod_row:
                        continue
                    # record previous state for undo
                    change_record.append({"id": mod_row["id"], "prev_day": rec["prev_day"], "prev_hour": rec["prev_hour"], "course_code": mod_row["course_code"], "class_name": mod_row["class_name"]})
                    # apply staged -> mod
                    mod_row["day"] = staged_row["day"]
                    try:
                        mod_row["hour"] = int(staged_row["hour"])
                    except Exception:
                        mod_row["hour"] = staged_row["hour"]
                    mod_row["room"] = str(staged_row.get("room", "") or "")
                    # persist as preserved move
                    st.session_state.setdefault("preserved_moves", {})[(mod_row["course_code"], mod_row["class_name"])] = {"day": mod_row["day"], "hour": mod_row["hour"], "room": mod_row.get("room", "")}
                    applied += 1

                if applied:
                    st.session_state.setdefault("move_history", []).append(change_record)
                    st.success(f"{applied} değişiklik kalıcı yapıldı.")
                    # refresh staged copy to match assignments_mod
                    st.session_state["assignments_staged"] = [d.copy() for d in st.session_state.get("assignments_mod", [])]
                    maybe_rerun()
                else:
                    st.info("Kaydedilecek değişiklik bulunamadı.")

            if c2.button("İptal (geçici değişiklikleri geri al)", key="cell_cancel"):
                st.session_state.pop("cell_pending_changes", None)
                st.session_state["assignments_staged"] = [d.copy() for d in st.session_state.get("assignments_mod", [])]
                st.session_state.pop("cell_sel", None)
                st.info("Geçici değişiklikler iptal edildi.")

        # show detailed info for focused cell
        focus = st.session_state.get("cell_focus")
        if focus:
            with st.expander("Hücre Detayı", expanded=True):
                st.write(f"**Ders:** {focus.get('course_code')} — {focus.get('course_name')}")
                st.write(f"**Hoca:** {focus.get('teacher')}")
                st.write(f"**Sınıf:** {focus.get('class_name')}")
                st.write(f"**Zaman:** {focus.get('day')} {int(focus.get('hour')):02d}:00")

    st.subheader("İndirilebilir CSV Tabloları")
    st.caption("Programı daha anlaşılır kullanmanız için farklı görünümler ayrı CSV olarak indirilebilir.")

    # Exports should include full understandable program for all teachers/classes.
    export_base = rooms_assigned_df.copy() if not rooms_assigned_df.empty else table_df.copy()
    export_base = export_base.sort_values(["Gün", "Saat", "Hoca", "Sınıf", "Kod"]).reset_index(drop=True)

    detail_cols = [
        c
        for c in [
            "Gün",
            "Saat",
            "Kod",
            "Ders",
            "Hoca",
            "Sınıf",
            "Room",
            "students",
            "room_capacity",
            "room_ok",
            "over_by",
        ]
        if c in export_base.columns
    ]
    export_detail = export_base[detail_cols].copy().fillna("-")

    teacher_cols = [c for c in ["Hoca", "Gün", "Saat", "Kod", "Ders", "Sınıf", "Room"] if c in export_base.columns]
    export_teacher = export_base[teacher_cols].copy().sort_values(["Hoca", "Gün", "Saat"]).reset_index(drop=True).fillna("-")

    class_cols = [c for c in ["Sınıf", "Gün", "Saat", "Kod", "Ders", "Hoca", "Room"] if c in export_base.columns]
    export_class = export_base[class_cols].copy().sort_values(["Sınıf", "Gün", "Saat"]).reset_index(drop=True).fillna("-")

    export_weekly = weekly.fillna("-").reset_index().rename(columns={"index": "Saat"})
    export_weekly = export_weekly.applymap(lambda v: str(v).replace("\n", " | "))

    # Use semicolon delimiter for easier opening in Turkish Excel locales.
    detail_csv = export_detail.to_csv(index=False, sep=";").encode("utf-8-sig")
    weekly_csv = export_weekly.to_csv(index=False, sep=";").encode("utf-8-sig")
    teacher_csv = export_teacher.to_csv(index=False, sep=";").encode("utf-8-sig")
    class_csv = export_class.to_csv(index=False, sep=";").encode("utf-8-sig")

    d1, d2, d3, d4 = st.columns(4)
    d1.download_button(
        label="Detaylı Program CSV",
        data=detail_csv,
        file_name="program_detayli.csv",
        mime="text/csv",
    )
    d2.download_button(
        label="Haftalık Tablo CSV",
        data=weekly_csv,
        file_name="program_haftalik_tablo.csv",
        mime="text/csv",
    )
    d3.download_button(
        label="Hoca Bazlı CSV",
        data=teacher_csv,
        file_name="program_hoca_bazli.csv",
        mime="text/csv",
    )
    d4.download_button(
        label="Sınıf Bazlı CSV",
        data=class_csv,
        file_name="program_sinif_bazli.csv",
        mime="text/csv",
    )

except Exception as exc:
    st.error(f"Program oluşturulurken hata oluştu: {exc}")
