"""
BİLGİSAYAR DERS GÖREVLENDİRME FORM 70 bahar.xlsx -> orjinal_dersler.csv + orjinal_salonlar.csv
"""
from __future__ import annotations

import os
import re

import pandas as pd

LAB_TEACHER = "Arş. Gör. Hüseyin Furkan ZENGİN"
SAMPLE_DIR = "sample_data"

# Uzun eşleşmeler önce (VII içinde II geçtiği için sıra önemli)
CLASS_ORDER = [
    ("VIII.YARIYIL", "4.Sınıf"),
    ("VII.YARIYIL", "4.Sınıf"),
    ("VI.YARIYIL", "3.Sınıf"),
    ("IV.YARIYIL", "2.Sınıf"),
    ("II.YARIYIL", "1.Sınıf"),
]

def find_xlsx() -> str:
    for f in os.listdir(SAMPLE_DIR):
        if f.endswith(".xlsx") and "70 bahar" in f.lower().replace("i̇", "i"):
            return os.path.join(SAMPLE_DIR, f)
    for f in os.listdir(SAMPLE_DIR):
        if f.endswith(".xlsx"):
            return os.path.join(SAMPLE_DIR, f)
    raise FileNotFoundError("Görevlendirme formu xlsx bulunamadı")


def parse_class_from_semester(cell) -> str | None:
    if pd.isna(cell):
        return None
    s = str(cell).strip().upper()
    for key, cls in CLASS_ORDER:
        if key in s:
            return cls
    return None


def semester_class_from_row(c0, c1) -> str | None:
    """Yarıyıl başlığı satırından sınıf etiketi (Unicode/encoding farklarına dayanıklı)."""
    c1s = str(c1).strip().upper() if not pd.isna(c1) else ""
    if "YARIYIL" in c1s:
        return parse_class_from_semester(c1)
    c0s = str(c0).strip().upper() if not pd.isna(c0) else ""
    if "DERS" in c0s and ("DÖNEM" in c0s or "DONEM" in c0s or "NEM" in c0s):
        return parse_class_from_semester(c1)
    return None


def is_course_code(val) -> bool:
    return bool(val) and bool(re.match(r"^[A-Z]{2,5}-\d{3,4}", str(val).strip()))


def _normalize_teacher_display(name: str) -> str:
    """Formdaki ünvan + isim; ünvan silinmez, yalnızca boşluk/nokta düzeni düzeltilir."""
    s = re.sub(r"\s+", " ", name.strip())
    s = re.sub(r"^Prof\.Dr\.\s*", "Prof. Dr. ", s, flags=re.I)
    s = re.sub(r"^Prof\.\s*Dr\.\s*", "Prof. Dr. ", s, flags=re.I)
    s = re.sub(r"^Doç\.Dr\.\s*", "Doç. Dr. ", s, flags=re.I)
    s = re.sub(r"^Doç\.\s*Dr\.\s*", "Doç. Dr. ", s, flags=re.I)
    s = re.sub(r"^Dr\.Öğr\.Üyesi\s*", "Dr. Öğr. Üyesi ", s, flags=re.I)
    s = re.sub(r"^Dr\.\s*Öğr\.\s*Üyesi\s*", "Dr. Öğr. Üyesi ", s, flags=re.I)
    s = re.sub(r"^Öğr\.\s*Gör\.\s*Dr\.\s*", "Öğr. Gör. Dr. ", s, flags=re.I)
    s = re.sub(r"^Arş\.\s*Gör\.\s*", "Arş. Gör. ", s, flags=re.I)
    return s


def parse_teacher(raw) -> str | None:
    """Formda hoca hücresi doluysa ünvanlı tam adı döner; boş/talep edildi/kod referansı ise None."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = str(raw).strip()
    if not s or s.lower() in ("talep edildi", "nan"):
        return None
    if is_course_code(s):
        return None
    low = s.lower()
    if "döküman" in low or "yürürlük" in low or "revizyon" in low:
        return None
    if "dersi verecek" in low or "bilgisayar mühendisliği" == low.strip():
        return None
    return _normalize_teacher_display(s)


def tur_is_elective(tur: str) -> bool:
    t = str(tur).strip().upper()
    return t == "S" or t.startswith("S ")


def extract_courses(df: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    current_class: str | None = None

    for i in range(len(df)):
        row = df.iloc[i]
        c0 = row[0] if len(row) > 0 else None
        c1 = row[1] if len(row) > 1 else None

        c0s = str(c0).strip() if not pd.isna(c0) else ""
        c1s = str(c1).strip() if not pd.isna(c1) else ""

        if "ESK" in c1s.upper() and "KODLU" in c1s.upper():
            break  # Eski kod eşlemeleri programda tekrar etmesin
        if c0s.startswith("UOS DERS") or c0s == "UOS DERSLERİ":
            current_class = "ÜOS Seçmeli"
            continue

        sem_class = semester_class_from_row(c0, c1)
        if sem_class:
            current_class = sem_class
            continue

        if str(c1).strip().upper() == "KODU":
            continue

        code = row[1] if len(row) > 1 else None
        if not is_course_code(code):
            continue
        if current_class is None:
            continue

        code_s = str(code).strip()
        name = row[2] if len(row) > 2 else code_s
        name_s = str(name).strip() if not pd.isna(name) else code_s
        tur = row[4] if len(row) > 4 else "Z"
        tur_s = str(tur).strip() if not pd.isna(tur) else "Z"

        def fnum(col_idx, default=0.0):
            v = row[col_idx] if len(row) > col_idx else None
            if pd.isna(v):
                return default
            try:
                return float(v)
            except Exception:
                return default

        theory = fnum(5)
        lab = fnum(7)
        krd = fnum(8)

        teacher_s = parse_teacher(row[10] if len(row) > 10 else "")
        if not teacher_s:
            continue

        enrolled = row[11] if len(row) > 11 else None
        enrolled_val = ""
        if not pd.isna(enrolled):
            try:
                enrolled_val = int(float(enrolled))
            except Exception:
                pass

        # A/B grup -> ayrı sınıf etiketi
        class_name = current_class
        grp = re.search(r"\(([AB])\s*Grubu\)", name_s, re.I)
        if grp:
            class_name = f"{current_class}-{grp.group(1).upper()}"

        elective = tur_is_elective(tur_s)
        dept = "seçimlik" if elective else "bilgisayar mühendisliği"
        if current_class == "ÜOS Seçmeli":
            dept = "üos seçmeli"

        if lab > 0:
            main_hours = theory if theory > 0 else max(0.0, krd - lab)
        else:
            main_hours = theory if theory > 0 else krd

        if main_hours > 0:
            rows.append(
                {
                    "code": code_s,
                    "name": name_s,
                    "teacher": teacher_s,
                    "class": class_name,
                    "weekly_hours": main_hours,
                    "enrolled": enrolled_val,
                    "department": dept,
                    "course_type": "seçimlik" if elective else "zorunlu",
                    "tur": tur_s,
                    "lab_hours": 0,
                }
            )

        if lab > 0:
            rows.append(
                {
                    "code": f"{code_s}-LAB",
                    "name": f"{name_s} (Laboratuvar)",
                    "teacher": LAB_TEACHER,
                    "class": class_name,
                    "weekly_hours": lab,
                    "enrolled": enrolled_val,
                    "department": dept,
                    "course_type": "lab",
                    "tur": "L",
                    "lab_hours": lab,
                }
            )

    return rows


def main():
    xlsx_path = find_xlsx()
    xl = pd.ExcelFile(xlsx_path)
    sheet = xl.sheet_names[1] if len(xl.sheet_names) > 1 else xl.sheet_names[0]
    df = pd.read_excel(xlsx_path, sheet_name=sheet, header=None)

    courses = extract_courses(df)
    out = pd.DataFrame(courses)
    out = out.drop_duplicates(subset=["code", "class", "course_type"], keep="first")
    out = out.sort_values(["class", "code"]).reset_index(drop=True)

    dersler_path = os.path.join(SAMPLE_DIR, "orjinal_dersler.csv")
    out.to_csv(dersler_path, index=False, encoding="utf-8")

    salon_src = os.path.join(SAMPLE_DIR, "SALONLAR.csv")
    salon_dst = os.path.join(SAMPLE_DIR, "orjinal_salonlar.csv")
    if os.path.exists(salon_src):
        rooms = None
        for enc in ("utf-8", "utf-8-sig", "cp1254", "latin1"):
            try:
                rooms = pd.read_csv(salon_src, encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        if rooms is None:
            raise UnicodeDecodeError("salon", b"", 0, 1, "SALONLAR.csv okunamadı")
        rooms.to_csv(salon_dst, index=False, encoding="utf-8")
    else:
        pd.DataFrame(
            [
                {"room": "403 NOLU LAB", "capacity": 60, "type": "Lab", "equipment": "Bilgisayar"},
                {"room": "404 NOLU LAB", "capacity": 40, "type": "Lab", "equipment": "Bilgisayar"},
                {"room": "414 NOLU DERSLİK", "capacity": 80, "type": "Derslik", "equipment": "Projeksiyon"},
            ]
        ).to_csv(salon_dst, index=False, encoding="utf-8")

    print(f"Yazıldı: {dersler_path} ({len(out)} satır)")
    print(f"Yazıldı: {salon_dst}")
    print("Seçimlik:", len(out[out["course_type"] == "seçimlik"]))
    print("Lab:", len(out[out["course_type"] == "lab"]))


if __name__ == "__main__":
    main()
