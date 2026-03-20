from __future__ import annotations

from collections import defaultdict

import pandas as pd
import streamlit as st

from scheduler import Course, DAYS, HOURS, solve_timetable


RULE_PIECES = ["teacher", "day", "hour", "course", "class"]
RULE_PIECE_LABELS = {
    "teacher": "Öğretmen",
    "day": "Gün",
    "hour": "Saat",
    "course": "Ders",
    "class": "Sınıf",
}


st.set_page_config(page_title="AI Ders Programı", layout="wide")
st.title("Üniversite Ders Programı (Yapay Zeka Destekli)")
st.caption("Sert kurallar + yumuşak kurallar ile en uygun haftalık program")

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

st.subheader("Ders Verisi")
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
        raw_df = pd.read_csv(uploaded, sep=None, engine="python")
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
    use_container_width=True,
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

        courses.append(
            Course(
                code=str(row["code"]).strip(),
                name=str(row["name"]).strip(),
                teacher=str(row["teacher"]).strip(),
                class_name=str(row["class"]).strip(),
                weekly_hours=weekly_hours,
            )
        )

    if not courses:
        st.warning("Geçerli ders verisi bulunamadı.")
        st.stop()

    st.subheader("Kural Yapbozu (Offline)")
    st.caption("Parçaları sırayla ekle, alttan değerleri seç, en sonda olsun/olmasın belirle.")

    teacher_names = sorted({course.teacher for course in courses})
    class_names = sorted({course.class_name for course in courses})
    course_options = sorted({f"{course.code} | {course.name}" for course in courses})

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

    table_df = pd.DataFrame(
        [
            {
                "Gün": a.day,
                "Saat": f"{a.hour:02d}:00-{a.hour+1:02d}:00",
                "Ders": a.course_name,
                "Kod": a.course_code,
                "Hoca": a.teacher.split(" || ")[0],
                "Sınıf": a.class_name,
            }
            for a in assignments
        ]
    )

    st.subheader("Detaylı Liste")
    st.dataframe(table_df, use_container_width=True, hide_index=True)

    st.subheader("Haftalık Program Tablosu")
    pivot = table_df.copy()
    pivot["Hücre"] = (
        pivot["Kod"] + "\n" + pivot["Ders"] + "\n" + pivot["Hoca"] + " (" + pivot["Sınıf"] + ")"
    )
    weekly = pivot.pivot_table(index="Saat", columns="Gün", values="Hücre", aggfunc="first")

    day_order = [d for d in DAYS if d in weekly.columns]
    weekly = weekly.reindex(columns=day_order)

    hour_order = [f"{h:02d}:00-{h+1:02d}:00" for h in HOURS]
    weekly = weekly.reindex(hour_order)

    st.dataframe(weekly.fillna("-"), use_container_width=True)

    csv_bytes = table_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Programı CSV olarak indir",
        data=csv_bytes,
        file_name="ders_programi.csv",
        mime="text/csv",
    )

except Exception as exc:
    st.error(f"Program oluşturulurken hata oluştu: {exc}")
