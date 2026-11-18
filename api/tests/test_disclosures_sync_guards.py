"""Regression tests for Saudi & EGX disclosures sync pipelines."""

import pytest

from api.saudi_disclosures_sync import (
    _classify_disclosure,
    _clean_saudi_title,
    _is_duplicate_saudi_event,
    _match_symbol,
)


@pytest.mark.parametrize(
    "headline,expected_sym",
    [
        ("أنابيب الشرق توقّع عقداً مع أرامكو السعودية بقيمة 46 مليون ريال", "1321"),
        ("أنابيب توقع عقداً مع أرامكو السعودية بقيمة 104 ملايين ريال", "2200"),
        ("سابك للمغذيات ترسي عقد مشروعها السابع بـ3.47 مليار دولار", "2020"),
        ("شركة تابعة لـ الأبحاث والإعلام توقع عقد خدمات رعاية وإعلان مع إس تي سي لمدة 3 سنوات", "4210"),
        ("تعلن شركة أرامكو السعودية لزيوت الأساس - لوبريف عن تشكيل لجنة تنفيذ المشاريع", "2223"),
        ("إم آي إس تبرم عقداً مع معادن بـ30.41 مليون دولار", "7200"),
        ("سلوشنز تُوقع عقد توفير خدمة الرسائل المدارة لبنك إس تي سي بقيمة 190 مليون ريال", "7202"),
    ],
)
def test_saudi_match_symbol_multi_company_headlines(headline, expected_sym):
    sym, _ = _match_symbol(headline, [])
    assert sym == expected_sym


@pytest.mark.parametrize(
    "headline",
    [
        "أرباح معادن تتراجع 24% في الربع الثالث إلى 1.68 مليار ريال",
        "انخفاض أرباح إس تي سي 12.4% إلى 3.6 مليار ريال في الربع الثالث",
        "أرباح سابك للمغذيات الزراعية تهبط 62% خلال الربع الثالث",
    ],
)
def test_saudi_classify_disclosure_bearish_earnings_drop(headline):
    d_type, sentiment, action_type, _ = _classify_disclosure(headline)
    assert d_type == "earnings"
    assert sentiment == "bearish"
    assert action_type == "general"


def test_saudi_classify_disclosure_dividend_uses_general_action_without_shares():
    d_type, sentiment, action_type, _ = _classify_disclosure(
        "أرامكو السعودية تقرر توزيع أرباح نقدية بقيمة 82.07 مليار ريال عن الربع الثالث"
    )
    assert d_type == "dividend"
    assert sentiment == "bullish"
    assert action_type == "general"


def test_saudi_clean_title_strips_rss_suffixes():
    cleaned = _clean_saudi_title(
        "سينومي سنترز توصي بزيادة رأس المال - ارقام : اخبار ومعلومات سوق الأسهم السعودي - تداول",
        "ارقام",
    )
    assert "ارقام" not in cleaned
    assert cleaned == "سينومي سنترز توصي بزيادة رأس المال"


def test_saudi_event_deduplication_blocks_cross_outlet_duplicates():
    existing = [
        {
            "symbol": "1211",
            "disclosure_type": "earnings",
            "disclosure_date": "2026-11-09",
            "title": "أرباح معادن تتراجع 23.7% في الربع الثالث إلى 448.6 مليون دولار",
            "sentiment": "bearish",
            "source_url": "https://example.com/news/1",
        },
        {
            "symbol": "2200",
            "disclosure_type": "material_event",
            "disclosure_date": "2026-11-16",
            "title": "العربية للأنابيب توقع عقداً مع أرامكو بقيمة 104 ملايين ريال",
            "sentiment": "bullish",
            "source_url": "https://example.com/news/2",
        },
    ]

    # Same earnings drop from another outlet/URL & slightly different phrasing -> blocked
    dup_earnings = {
        "symbol": "1211",
        "disclosure_type": "earnings",
        "disclosure_date": "2026-11-09",
        "title": "انخفاض أرباح معادن 24% إلى 1.7 مليار ريال بالربع الثالث",
        "sentiment": "bearish",
        "source_url": "https://other-outlet.com/news/99",
    }
    assert _is_duplicate_saudi_event(dup_earnings, existing) is True

    # Same 104M contract reported by a second outlet as material_event -> blocked
    dup_contract = {
        "symbol": "2200",
        "disclosure_type": "material_event",
        "disclosure_date": "2026-11-16",
        "title": "أنابيب توقع عقدا مع أرامكو السعودية بـ 104 ملايين ريال",
        "sentiment": "bullish",
        "source_url": "https://other-outlet.com/news/100",
    }
    assert _is_duplicate_saudi_event(dup_contract, existing) is True

    # Genuinely distinct contract with a different value on the same symbol -> allowed
    distinct_contract = {
        "symbol": "2200",
        "disclosure_type": "material_event",
        "disclosure_date": "2026-11-18",
        "title": "العربية للأنابيب تفوز بمناقصة توريد بقيمة 55 مليون ريال",
        "sentiment": "bullish",
        "source_url": "https://other-outlet.com/news/101",
    }
    assert _is_duplicate_saudi_event(distinct_contract, existing) is False
