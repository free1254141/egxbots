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

def test_voices_endpoint():
    res = client.get("/voice/voices")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "ar-EG-ShakirNeural" in data["voices"]
