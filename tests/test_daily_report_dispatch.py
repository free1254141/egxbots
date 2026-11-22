import os
from unittest.mock import MagicMock, patch

import api.daily_report_dispatch as daily_report_dispatch


def test_multipart_telegram_send_uses_relay_first_for_all_parts():
    split_marker = "🎯 <b>سادساً: رادار الإجماع الخوارزمي"
    long_head = ("• <b>COMI</b>: كوبون 1.00 ج.م\n" * 120).strip()
    long_tail = ("• <b>HRHO</b>: إشارة توافق خوارزمي\n" * 30).strip()
    html = f"{long_head}\n{split_marker}</b>\n{long_tail}"
    assert len(long_head) < 4000 < len(html)

    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append((url, json))
        resp = MagicMock()
        resp.json.return_value = {"ok": True, "result": {"message_id": 100 + len(calls)}}
        return resp

    with patch.dict(
        os.environ,
        {
            "ARTORO_AI_BOT": "bot-secret",
            "TELEGRAM_RELAY_URL": "https://relay.example.test/functions/v1/telegram-relay",
        },
        clear=False,
    ), patch("api.daily_report_dispatch.requests.post", side_effect=fake_post):
        ok, msg_id = daily_report_dispatch._telegram_send(
            "-1003906516349",
            html,
            [[{"text": "btn", "url": "https://egxbots.com"}]],
        )

    assert ok is True
    assert msg_id == 102
    assert len(calls) == 2
    assert calls[0][0].startswith("https://relay.example.test/")
    assert calls[1][0].startswith("https://relay.example.test/")
    assert "reply_markup" not in calls[0][1]
    assert "reply_markup" in calls[1][1]
    assert calls[1][1]["text"].startswith(split_marker)


def test_multipart_telegram_send_aborts_part2_if_part1_fails():
    split_marker = "🎯 <b>سادساً: رادار الإجماع الخوارزمي"
    long_head = ("• <b>COMI</b>: سطر طويل نسبياً للاختبار\n" * 160).strip()
    html = f"{long_head}\n{split_marker}</b>\n• <b>HRHO</b>"
    called_texts = []

    def always_fail(url, json=None, timeout=None):
        called_texts.append(json["text"][:30])
        resp = MagicMock()
        resp.json.return_value = {"ok": False, "description": "relay blocked"}
        return resp

    with patch.dict(
        os.environ,
        {
            "ARTORO_AI_BOT": "bot-secret",
            "TELEGRAM_RELAY_URL": "https://relay.example.test/functions/v1/telegram-relay",
        },
        clear=False,
    ), patch("api.daily_report_dispatch.requests.post", side_effect=always_fail), patch(
        "api.daily_report_dispatch.time.sleep", return_value=None
    ):
        ok, msg_id = daily_report_dispatch._telegram_send("-1003906516349", html, [])

    assert ok is False
    assert msg_id is None
    assert all(not t.startswith(split_marker[:10]) for t in called_texts)


def test_split_telegram_html_without_marker_splits_cleanly_on_newlines():
    line = "• <b>TEST</b> (شركة تجريبية): بيانات <code>2026-11-22</code>\n"
    text = (line * 95).strip()
    assert len(text) > 4000
    chunks = daily_report_dispatch._split_telegram_html(text, "NON_EXISTENT", max_len=4000)
    assert len(chunks) >= 2
    assert all(len(c) <= 4000 for c in chunks)
    assert all(c.endswith("</code>") for c in chunks)


def test_dynamic_html_fields_are_escaped():
    s = {
        "disclosures": [
            {
                "symbol": "A&B",
                "disclosure_type": "material_event",
                "title": "صفقة استحواذ <10% & زيادة رأس المال",
            }
        ],
        "dividends": [
            {
                "symbol": "C<D",
                "name_ar": "شركة س & ص",
                "amount": 1.25,
                "currency_ar": "ج.م",
                "yield_pct": 5.5,
                "ex_date": "2026-11-25",
                "pay_date": "2026-11-29",
                "verdict_ar": "🟢 ممتاز & قوي <15x",
                "pe_ratio": 10.0,
                "roe_pct": 20.0,
                "fund_score": 80,
            }
        ],
    }
    disc_out = daily_report_dispatch._disclosures_lines(s)
    div_out = daily_report_dispatch._dividends_lines(s)
    assert "A&amp;B" in disc_out and "&lt;10% &amp; زيادة" in disc_out
    assert "C&lt;D" in div_out and "شركة س &amp; ص" in div_out and "&amp; قوي &lt;15x" in div_out


def test_run_daily_report_dispatch_reports_partial_failure():
    fake_client = MagicMock()
    today = daily_report_dispatch._cairo_today()
    perf = {"asOf": today, "review": {"unusual": []}}
    traps = {"asOf": today, "bearTraps": [{"symbol": "HRHO"}], "bullTraps": []}

    with patch.object(daily_report_dispatch, "_load_snapshots", return_value=(perf, traps)), patch.object(
        daily_report_dispatch, "_load_disclosures", return_value=[]
    ), patch.object(daily_report_dispatch, "_load_upcoming_dividends_with_financials", return_value=[]), patch.object(
        daily_report_dispatch, "build_vip_html", return_value="VIP"
    ), patch.object(
        daily_report_dispatch, "build_free_telegram_html", return_value="FREE"
    ), patch.object(
        daily_report_dispatch, "_already_done", return_value=False
    ), patch.object(
        daily_report_dispatch, "_mark_done"
    ) as mock_mark, patch.object(
        daily_report_dispatch,
        "_telegram_send",
        side_effect=[(False, None), (True, 3639)],
    ), patch.dict(
        os.environ, {"DAILY_PROMO_EMAILS_ENABLED": "0"}, clear=False
    ):
        res = daily_report_dispatch.run_daily_report_dispatch(fake_client, dry_run=False)

    assert res["status"] == "partial_failure"
    assert res["failed_channels"] == ["vip_telegram"]
    assert res["channels"]["vip_telegram"] == {"ok": False, "info": None}
    assert res["channels"]["free_telegram"] == {"ok": True, "info": 3639}
    mock_mark.assert_called_once_with(fake_client, "free_telegram", today, {"info": 3639})
