"""Offline compliance & pricing-split verification tests for all promotional/lifecycle emails."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import api.daily_report_dispatch as daily_report_dispatch
import api.marketing_lifecycle as ml
import jobs.send_failed_payment_recovery as failed_recovery
import jobs.send_founders_emails as founders_emails
import jobs.send_founders_final_48h_emails as final_48h
import jobs.send_new_signups_welcome as new_signups

REPO_ROOT = Path(__file__).resolve().parents[1]

BANNED_COPY_TERMS = (
    "انستاباي",
    "إنستاباي",
    "instapay",
    "01024359100",
    "200 ج.م",
    "استشارة شهرياً",
    "استشارة شهريا",
    "المستشار المالي",
    "المستشار الذكي",
    "الصفقات القصيرة",
    "صفقات وتوصيات",
    "قناة التوصيات",
    "مربحة",
)


def _assert_clean_copy(text: str) -> None:
    lowered = text.lower()
    for term in BANNED_COPY_TERMS:
        assert term.lower() not in lowered, f"Forbidden term {term!r} found in email copy"


class _FakeTableQuery:
    def __init__(self, rows_provider):
        self._rows_provider = rows_provider
        self._filters = {}
        self._in_filters = {}

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def in_(self, col, vals):
        self._in_filters[col] = set(vals)
        return self

    def gte(self, *_args, **_kwargs):
        return self

    def lte(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def maybe_single(self):
        self._single = True
        return self

    def insert(self, _row):
        return self

    def execute(self):
        data = self._rows_provider(self._filters, self._in_filters)
        if getattr(self, "_single", False):
            return SimpleNamespace(data=data[0] if isinstance(data, list) and data else (data or {}))
        return SimpleNamespace(data=data)


class _FakeMarketingDB:
    def __init__(self, *, orders=None, active_subs=None, trials=None, profile=None):
        self.orders = orders or []
        self.active_subs = active_subs or []
        self.trials = trials or []
        self.profile = profile or {"display_name": "عميل تجريبي"}

    def table(self, name: str):
        if name == "local_payment_orders":
            return _FakeTableQuery(lambda _f, _in: self.orders)
        if name == "subscriptions":
            def _sub_rows(filters, in_filters):
                uid = filters.get("user_id")
                allowed_plans = in_filters.get("plan_id")
                return [
                    s for s in self.active_subs
                    if (uid is None or s.get("user_id") == uid)
                    and (allowed_plans is None or s.get("plan_id") in allowed_plans)
                ]
            return _FakeTableQuery(_sub_rows)
        if name == "subscription_trials":
            return _FakeTableQuery(lambda _f, _in: self.trials)
        if name == "profiles":
            return _FakeTableQuery(lambda _f, _in: [self.profile])
        return _FakeTableQuery(lambda _f, _in: [])


def test_tiers_summary_html_regular_and_founders():
    regular = ml._build_tiers_summary_html(150, None)
    for snippet in ("100 ج.م", "150 ج.م", "750 ج.م", "1,350 ج.م", "25%", "EasyKash", "3D Secure"):
        assert snippet in regular
    _assert_clean_copy(regular)

    founder_50 = ml._build_tiers_summary_html(50, 50)
    for snippet in ("50 ج.م/شهر", "250 ج.م", "450 ج.م", "150 ج.م", "25%", "EasyKash"):
        assert snippet in founder_50
    _assert_clean_copy(founder_50)

    founder_100 = ml._build_tiers_summary_html(100, 100)
    for snippet in ("100 ج.م/شهر", "500 ج.م", "900 ج.م", "150 ج.م", "25%", "EasyKash"):
        assert snippet in founder_100
    _assert_clean_copy(founder_100)


def test_abandoned_checkout_tailored_and_skips_active_split_tiers():
    fake_db = _FakeMarketingDB(
        orders=[
            {"id": "ord-chat", "user_id": "u-chat", "plan_id": "chat_only"},
            {"id": "ord-vip", "user_id": "u-vip", "plan_id": "vip_only"},
            {"id": "ord-pro", "user_id": "u-pro", "plan_id": "pro"},
            {"id": "ord-skip", "user_id": "u-paid-chat", "plan_id": "pro"},
        ],
        active_subs=[
            {"id": "sub-1", "user_id": "u-paid-chat", "plan_id": "chat_only", "status": "active"},
        ],
    )
    sent = []

    def fake_send(email, subject, html, out=None):
        sent.append((email, subject, html))
        return True

    def fake_offer(uid):
        return (50, 50) if uid == "u-pro" else (150, None)

    with (
        patch.object(ml, "supabase", fake_db),
        patch.object(ml, "has_recent_message", return_value=False),
        patch.object(ml, "is_user_unsubscribed", return_value=False),
        patch.object(ml, "get_user_email", side_effect=lambda uid: f"{uid}@example.com"),
        patch.object(ml, "_resolve_user_pro_offer", side_effect=fake_offer),
        patch.object(ml, "send_resend_email", side_effect=fake_send),
        patch.object(ml, "record_marketing_message"),
    ):
        count = ml.process_abandoned_checkouts()

    assert count == 3
    sent_by_email = {e: (s, h) for e, s, h in sent}
    assert "u-paid-chat@example.com" not in sent_by_email

    chat_subj, chat_html = sent_by_email["u-chat@example.com"]
    assert "100 ج.م" in chat_subj
    assert "plan%3Dchat_only" in chat_html or "plan=chat_only" in chat_html
    assert "EasyKash" in chat_html
    _assert_clean_copy(chat_subj + chat_html)

    vip_subj, vip_html = sent_by_email["u-vip@example.com"]
    assert "100 ج.م" in vip_subj
    assert "plan%3Dvip_only" in vip_html or "plan=vip_only" in vip_html
    assert "EasyKash" in vip_html
    _assert_clean_copy(vip_subj + vip_html)

    pro_subj, pro_html = sent_by_email["u-pro@example.com"]
    assert "50 ج.م" in pro_subj
    assert "250 ج.م" in pro_html and "450 ج.م" in pro_html
    _assert_clean_copy(pro_subj + pro_html)


def test_trial_lifecycle_emails_are_fra_compliant_and_split_aware():
    fake_db = _FakeMarketingDB(
        trials=[{"user_id": "u-trial", "started_at": "2026-11-18T00:00:00Z", "expires_at": "2026-11-21T00:00:00Z"}],
    )
    sent = []

    def fake_send(email, subject, html, out=None):
        sent.append((subject, html))
        return True

    with (
        patch.object(ml, "supabase", fake_db),
        patch.object(ml, "has_recent_message", return_value=False),
        patch.object(ml, "is_user_unsubscribed", return_value=False),
        patch.object(ml, "get_user_email", return_value="trial@example.com"),
        patch.object(ml, "_resolve_user_pro_offer", return_value=(150, None)),
        patch.object(ml, "send_resend_email", side_effect=fake_send),
        patch.object(ml, "record_marketing_message"),
    ):
        assert ml.process_trial_expiring() == 1
        assert ml.process_trial_welcome() == 1
        assert ml.process_trial_day1() == 1
        assert ml.process_trial_day2() == 1

    assert len(sent) == 4
    expiring_subj, expiring_html = sent[0]
    assert "100 ج.م" in expiring_subj and "150 ج.م" in expiring_subj
    assert "750 ج.م" in expiring_html and "1,350 ج.م" in expiring_html
    assert "EasyKash" in expiring_html
    for subj, html in sent:
        _assert_clean_copy(subj + html)


def test_failed_payment_recovery_is_easykash_only_and_compliant():
    sent_emails = []
    sent_tg = []

    def fake_email(email, subject, html_body, out=None):
        sent_emails.append((subject, html_body))
        return True

    class _FakeResp:
        status_code = 200

        @staticmethod
        def json():
            return {"ok": True}

    def fake_tg_post(url, json=None, timeout=10):
        sent_tg.append(json["text"])
        return _FakeResp()

    with (
        patch.object(failed_recovery, "is_user_unsubscribed", return_value=False),
        patch.object(failed_recovery, "_resolve_user_pro_offer", return_value=(150, None)),
        patch.object(failed_recovery, "send_resend_email", side_effect=fake_email),
        patch.object(failed_recovery, "record_marketing_message") as mock_rec,
        patch.dict("os.environ", {"ARTORO_AI_BOT": "123:abc"}, clear=False),
        patch.object(failed_recovery.requests, "post", side_effect=fake_tg_post),
    ):
        assert failed_recovery.send_failed_payment_email("u1", "u1@example.com", "أحمد") is True
        assert failed_recovery.send_failed_payment_telegram(999, "أحمد") is True

    assert len(sent_emails) == 1
    assert len(sent_tg) == 1
    subj, html = sent_emails[0]
    for payload in (subj + html, sent_tg[0]):
        assert "EasyKash" in payload
        assert "3D Secure" in payload
        assert "100 ج.م" in payload and "150 ج.م" in payload
        _assert_clean_copy(payload)
    assert mock_rec.call_args.kwargs["metadata"]["campaign"] == "failed_payment_support_easykash"


def test_daily_report_dispatch_promo_copy():
    with patch("api.payment_common.current_pro_offer_copy", return_value=(150, False)):
        offer = daily_report_dispatch._offer_html()
        html = daily_report_dispatch.build_email_html(
            {
                "as_of": "2026-11-19",
                "top": {},
                "movers": [],
                "total": 0,
                "winners": 0,
                "bear": [],
                "bull": [],
                "unusual_stat": {},
                "springs_stat": {},
                "upthrusts_stat": {},
                "disclosures": [],
            },
            "https://egxbots.com/unsub",
            "https://egxbots.com",
        )
    for text in (offer, html):
        assert "100 ج.م" in text and "150 ج.م" in text
        assert "EasyKash" in text
        _assert_clean_copy(text)


def test_founders_and_signup_email_jobs_respect_50_100_150_matrix():
    captured = []

    def fake_send(email, subject, html, out=None):
        captured.append((subject, html))
        return True

    with (
        patch.object(founders_emails, "is_user_unsubscribed", return_value=False),
        patch.object(founders_emails, "has_recent_message", return_value=False),
        patch.object(founders_emails, "_safe_pro_price", return_value=150),
        patch.object(founders_emails, "send_resend_email", side_effect=fake_send),
        patch.object(founders_emails, "record_marketing_message"),
    ):
        with (
            patch.object(founders_emails, "is_user_eligible_for_50_egp_renewal", return_value=True),
            patch.object(founders_emails, "is_user_eligible_for_100_egp_renewal", return_value=False),
        ):
            assert founders_emails.send_renewal_reminder_email("u50", "u50@x.com", "أحمد", 2, "2026-11-25")
            assert founders_emails.send_expired_reactivation_email("u50", "u50@x.com", "أحمد", "2026-11-18")

        with (
            patch.object(founders_emails, "is_user_eligible_for_50_egp_renewal", return_value=False),
            patch.object(founders_emails, "is_user_eligible_for_100_egp_renewal", return_value=True),
        ):
            assert founders_emails.send_renewal_reminder_email("u100", "u100@x.com", "محمد", 2, "2026-11-25")

        with (
            patch.object(founders_emails, "is_user_eligible_for_50_egp_renewal", return_value=False),
            patch.object(founders_emails, "is_user_eligible_for_100_egp_renewal", return_value=False),
        ):
            assert founders_emails.send_renewal_reminder_email("u_chat", "c@x.com", "كريم", 2, "2026-11-25", plan_id="chat_only")
            assert founders_emails.send_renewal_reminder_email("u_vip", "v@x.com", "سارة", 2, "2026-11-25", plan_id="vip_only")
            assert founders_emails.send_founders_offer_email("u_free", "f@x.com", "طارق")

    with (
        patch.object(final_48h, "is_user_unsubscribed", return_value=False),
        patch.object(final_48h, "has_recent_message", return_value=False),
        patch.object(final_48h, "send_resend_email", side_effect=fake_send),
        patch.object(final_48h, "record_marketing_message"),
    ):
        assert final_48h.send_founders_final_48h_email("u48", "u48@x.com", "نادر", 12, True)

    with patch.object(new_signups, "_resolve_user_pro_offer", return_value=(150, None)):
        subj, html = new_signups.build_email("u_new", "new@x.com", "زياد")
        captured.append((subj, html))

    assert "50 ج.م" in captured[0][1] and "250 ج.م" in captured[0][1] and "450 ج.م" in captured[0][1]
    assert "50 ج.م" in captured[1][0] and "250 ج.م" in captured[1][1] and "450 ج.م" in captured[1][1]
    assert "100 ج.م" in captured[2][1] and "500 ج.م" in captured[2][1] and "900 ج.م" in captured[2][1]
    assert "الشات الذكي" in captured[3][0] and "100 ج.م" in captured[3][1]
    assert "تليجرام VIP" in captured[4][0] and "100 ج.م" in captured[4][1]
    for subj, html in captured:
        _assert_clean_copy(subj + html)


def test_static_campaign_dispatch_scripts_are_compliant():
    for rel_path in (
        "scripts/dispatch_winback_trial_campaign.py",
        "scripts/dispatch_filtered_founders_email.py",
    ):
        text = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
        _assert_clean_copy(text)
        assert "100 ج.م" in text
        assert "150 ج.م" in text
        assert "EasyKash" in text
        assert "FRA" in text
