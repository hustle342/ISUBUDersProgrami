"""BLG-224/228: ortak teorik (2.Sınıf); A/B yalnız lab. Diğer dersler aynen kalır."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "sample_data" / "orjinal_dersler.csv"

BLG_CODES = frozenset({"BLG-224", "BLG-224-LAB", "BLG-228", "BLG-228-LAB"})

CANONICAL_ROWS = [
    {
        "code": "BLG-224",
        "name": "Sayısal Sistem Tasarımı",
        "teacher": "Doç. Dr. Kıyas KAYAALP",
        "class": "2.Sınıf",
        "weekly_hours": 3.0,
        "enrolled": "",
        "department": "bilgisayar mühendisliği",
        "course_type": "zorunlu",
        "tur": "Z",
        "lab_hours": 0.0,
    },
    {
        "code": "BLG-224-LAB",
        "name": "Sayısal Sistem Tasarımı (A Grubu) (Laboratuvar)",
        "teacher": "Arş. Gör. Hüseyin Furkan ZENGİN",
        "class": "2.Sınıf-A",
        "weekly_hours": 1.0,
        "enrolled": "",
        "department": "bilgisayar mühendisliği",
        "course_type": "lab",
        "tur": "L",
        "lab_hours": 1.0,
    },
    {
        "code": "BLG-224-LAB",
        "name": "Sayısal Sistem Tasarımı (B Grubu) (Laboratuvar)",
        "teacher": "Arş. Gör. Hüseyin Furkan ZENGİN",
        "class": "2.Sınıf-B",
        "weekly_hours": 1.0,
        "enrolled": "",
        "department": "bilgisayar mühendisliği",
        "course_type": "lab",
        "tur": "L",
        "lab_hours": 1.0,
    },
    {
        "code": "BLG-228",
        "name": "Bilgisayar Programlama II",
        "teacher": "Dr. Öğr. Üyesi Serdar PAÇACI",
        "class": "2.Sınıf",
        "weekly_hours": 3.0,
        "enrolled": "",
        "department": "bilgisayar mühendisliği",
        "course_type": "zorunlu",
        "tur": "Z",
        "lab_hours": 0.0,
    },
    {
        "code": "BLG-228-LAB",
        "name": "Bilgisayar Programlama II (A Grubu) (Laboratuvar)",
        "teacher": "Arş. Gör. Hüseyin Furkan ZENGİN",
        "class": "2.Sınıf-A",
        "weekly_hours": 1.0,
        "enrolled": "",
        "department": "bilgisayar mühendisliği",
        "course_type": "lab",
        "tur": "L",
        "lab_hours": 1.0,
    },
    {
        "code": "BLG-228-LAB",
        "name": "Bilgisayar Programlama II (B Grubu) (Laboratuvar)",
        "teacher": "Arş. Gör. Hüseyin Furkan ZENGİN",
        "class": "2.Sınıf-B",
        "weekly_hours": 1.0,
        "enrolled": "",
        "department": "bilgisayar mühendisliği",
        "course_type": "lab",
        "tur": "L",
        "lab_hours": 1.0,
    },
]


def main() -> None:
    df = pd.read_csv(CSV_PATH)
    removed = int(df["code"].isin(BLG_CODES).sum())
    rest = df[~df["code"].isin(BLG_CODES)].copy()

    insert_at = None
    for i, code in enumerate(rest["code"].astype(str)):
        if code == "BLG-304":
            insert_at = i
            break
    if insert_at is None:
        insert_at = len(rest)

    blg_df = pd.DataFrame(CANONICAL_ROWS)
    out = pd.concat([rest.iloc[:insert_at], blg_df, rest.iloc[insert_at:]], ignore_index=True)
    out.to_csv(CSV_PATH, index=False, encoding="utf-8")
    print(f"Güncellendi: {CSV_PATH}")
    print(f"  BLG satırı kaldırıldı: {removed}")
    print(f"  BLG satırı eklendi: {len(CANONICAL_ROWS)} (2 ortak teorik + 4 lab A/B)")
    print(f"  Toplam ders: {len(out)}")


if __name__ == "__main__":
    main()
