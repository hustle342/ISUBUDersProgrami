# AI Ders Programı (Streamlit)

Bu proje, üniversite ders programını **sert** ve **yumuşak** kurallara göre otomatik oluşturur.

## Özellikler

- Streamlit arayüzü ile ders verisi girişi
- Sert kurallar:
  - Aynı hoca aynı anda iki yerde olamaz
  - Aynı sınıf aynı anda iki derste olamaz
  - Öğle arası 13:00-14:00 bloklu
- Yumuşak kurallar:
  - Hocanın derslerini mümkün olduğunca aynı güne toplama
  - Sınıfın derslerini mümkün olduğunca aynı güne toplama
- Sonucu tablo olarak gösterme ve CSV indirme

## Kurulum

```bash
pip install -r requirements.txt
```

Windows için önerilen adımlar:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Çalıştırma

```bash
python -m streamlit run app.py
```

## CSV formatı

Aşağıdaki sütunlar gereklidir:

- `code`
- `name`
- `teacher`
- `class`
- `weekly_hours`

Örnek dosya: `sample_data/courses.csv`
