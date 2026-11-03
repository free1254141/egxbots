import pytest
from fastapi.testclient import TestClient
from api.routers.voice import clean_text_for_speech, router
from fastapi import FastAPI

test_app = FastAPI()
test_app.include_router(router)
client = TestClient(test_app)

def test_clean_text_for_speech():
    sample = """
    ## 📊 تحليل سهم فوري (FWRY)
    **السعر الأخير:** 16.30 ج.م (+4.4% تغيّر الجلسة)

    | المؤشر | القيمة |
    |---|---|
    | RSI | 54.2 |

    💡 **ملخص تنفيذي:**
    السهم في مرحلة تجميع قوية فوق دعم 16 جنيه، والمؤشرات تستهدف مقاومة 17.50 ج.م.
    """
    cleaned = clean_text_for_speech(sample)
    assert "##" not in cleaned
    assert "**" not in cleaned
    assert "|" not in cleaned
    assert "جنيه" in cleaned
    assert "في المية" in cleaned
    # Ensure word تجميع was not mangled into ت جنيه يع
    assert "تجميع" in cleaned
    assert "FWRY" not in cleaned

def test_clean_text_removes_english_tickers_and_symbols():
    sample = "أبو قير للأسمدة (ABUK) 77.71 جنيه، هابط 3.59% مع سهم TMGH ومؤشر RSI 40 والبنك التجاري الدولي (COMI.CA)."
    cleaned = clean_text_for_speech(sample)
    assert "ABUK" not in cleaned
    assert "TMGH" not in cleaned
    assert "COMI" not in cleaned
    assert "RSI" not in cleaned
    assert "أبو قير للأسمدة" in cleaned
    assert "طلعت مصطفى" in cleaned
    assert "البنك التجاري الدولي" in cleaned
    assert "مؤشر القوة النسبية" in cleaned
    import re
    assert not re.search(r"[A-Za-z]", cleaned)

def test_clean_text_financial_numbers_and_dates():
    sample = "جلسة 03-11-2026 بنسبة 4.49:1 ومؤشر 1,200 مليون جنيه."
    cleaned = clean_text_for_speech(sample)
    assert "1.2 مليار جنيه" in cleaned
    assert "3 نوفمبر 2026" in cleaned
    assert "03-11-2026" not in cleaned
    assert "4.5 إلى 1" in cleaned

def test_clean_text_strips_market_breadth_preamble():
    sample = """أقوى أسهم التجميع والسيولة الذكية جلسة 03-11-2026
    سياق السوق: 184 سهم صاعد مقابل 41 هابط (نسبة 4.49:1)، وإجمالي تداول 6,750.79 مليون جنيه (92.65 في المية من متوسط 20 جلسة)، و88.55 في المية من السيولة دخلت أسهمها صاعدة. 28 سهما بانحدار حجمي.
    جدول أسهم التجميع (مرتبة بدرجة التجميع)
    | السهم | السعر | درجة التجميع |
    |---|---|---|
    | SEIG | 12.5 | 90 |
    | AFMC | 45.0 | 85 |
    قراءة سريعة - السعودية المصرية للاستثمار والتمويل: هو الأقوى نموذجيا بدرجة تجميع 90 وصفر تصريف.
    """
    cleaned = clean_text_for_speech(sample)
    assert "سياق السوق" not in cleaned
    assert "صاعد مقابل" not in cleaned
    assert "السعودية المصرية للاستثمار والتمويل" in cleaned
    assert "مطاحن الإسكندرية" in cleaned
    assert "6,750" not in cleaned

def test_voices_endpoint():
    res = client.get("/voice/voices")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "ar-EG-ShakirNeural" in data["voices"]
