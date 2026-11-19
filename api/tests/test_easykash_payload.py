import unittest
from decimal import Decimal
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from unittest.mock import MagicMock, patch

from api.easykash_payments import _direct_pay_payload, _hosted_checkout_url, _verify_callback, create_checkout, payment_config
from api.payment_common import plan_amount_egp, pro_discount, pro_regular_amount_egp


class EasyKashPayloadTests(unittest.TestCase):
    def test_hosted_url_is_canonicalized_and_strictly_validated(self):
        self.assertEqual(
            _hosted_checkout_url("https://easykash.net//DirectPayV1/ZVW5119"),
            "https://www.easykash.net/DirectPayV1/ZVW5119",
        )
        self.assertEqual(
            _hosted_checkout_url("https://www.easykash.net/DirectPayV1/ZVW5119"),
            "https://www.easykash.net/DirectPayV1/ZVW5119",
        )
        for invalid in (
            "https://easykash.net.evil.com/DirectPayV1/ZVW5119",
            "https://easykash.net@evil.com/DirectPayV1/ZVW5119",
            "http://easykash.net/DirectPayV1/ZVW5119",
            "https://www.easykash.net/login",
        ):
            with self.subTest(url=invalid), self.assertRaises(RuntimeError):
                _hosted_checkout_url(invalid)

    def test_hosted_checkout_defers_method_selection_and_excludes_installments(self):
        payload = _direct_pay_payload(
            Decimal("200.00"),
            "Test User",
            "test@example.com",
            "01012345678",
            "https://egxbots.com/pricing",
            "test-order",
        )

        self.assertNotIn("paymentOptions", payload)
        self.assertEqual(
            payload["paymentOptionsExcluded"],
            [3, 8, 9, 10, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 32, 33, 34],
        )
        for allowed_option in (1, 2, 4, 5, 6, 31, 35):
            self.assertNotIn(allowed_option, payload["paymentOptionsExcluded"])
        self.assertEqual(payload["currency"], "EGP")
        self.assertEqual(payload["amount"], 200.0)
        self.assertEqual(payload["customerReference"], "test-order")

    def test_checkout_lets_easykash_show_enabled_methods(self):
        database = MagicMock()
        database.table.return_value.insert.return_value.execute.return_value.data = [{"id": "test-order"}]
        provider = MagicMock()
        provider.status_code = 200
        provider.json.return_value = {"redirectUrl": "https://easykash.net/DirectPayV1/test"}
        with (
            patch("api.easykash_payments.is_payments_enabled", return_value=True),
            patch("api.easykash_payments.is_easykash_ready", return_value=True),
            patch("api.easykash_payments.plan_amount_egp", return_value=Decimal("200.00")),
            patch("api.easykash_payments._init_supabase"),
            patch("api.easykash_payments.supabase", database),
            patch("api.easykash_payments.requests.post", return_value=provider) as request,
            patch.dict("os.environ", {"EASYKASH_API_KEY": "test-key"}, clear=False),
        ):
            result = create_checkout("test-user", "pro", "test@example.com", "Test User", "01012345678")

        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["url"], "https://www.easykash.net/DirectPayV1/test")
        # The checkout call is sent before the optional admin notification,
        # which can issue a second HTTP POST in the same test.
        sent_payload = request.call_args_list[0].kwargs["json"]
        self.assertNotIn("paymentOptions", sent_payload)
        self.assertEqual(
            sent_payload["paymentOptionsExcluded"],
            [3, 8, 9, 10, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 32, 33, 34],
        )

    def test_callback_signature_uses_easykash_documented_field_order(self):
        secret = "unit-test-secret"
        payload = {
            "ProductCode": "TEST123",
            "Amount": "50.5",
            "ProductType": "Subscription",
            "PaymentMethod": "Credit & Debit Card",
            "status": "PAID",
            "easykashRef": "EK123",
            "customerReference": "customer-123",
        }
        signed_values = (
            payload["ProductCode"],
            payload["Amount"],
            payload["ProductType"],
            payload["PaymentMethod"],
            payload["status"],
            payload["easykashRef"],
            payload["customerReference"],
        )
        message = "".join(signed_values).encode("utf-8")
        payload["signatureHash"] = hmac.new(secret.encode(), message, hashlib.sha512).hexdigest()

        with patch.dict("os.environ", {"EASYKASH_CALLBACK_SECRET": secret}, clear=False):
            self.assertTrue(_verify_callback(payload))
            altered = {**payload, "Amount": "50.6"}
            self.assertFalse(_verify_callback(altered))


class ProDiscountTests(unittest.TestCase):
    FUTURE = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z")
    PAST = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat().replace("+00:00", "Z")

    def test_env_discount_active_applies_to_monthly_only(self):
        with (
            patch("api.payment_common.billing_settings", return_value={}),
            patch.dict(
                "os.environ",
                {
                    "PRO_DISCOUNT_PRICE_EGP": "50",
                    "PRO_DISCOUNT_ENDS_AT": self.FUTURE,
                    "PRO_PRICE_EGP": "200",
                    "PRO_6M_PRICE_EGP": "1000",
                    "PRO_1Y_PRICE_EGP": "1850",
                },
                clear=False,
            ),
        ):
            discount = pro_discount()
            self.assertTrue(discount["active"])
            self.assertEqual(discount["price_egp"], 50.0)
            self.assertEqual(plan_amount_egp("pro"), 50.0)
            self.assertEqual(plan_amount_egp("pro_6m"), 1000.0)
            self.assertEqual(plan_amount_egp("pro_1y"), 1850.0)
            self.assertEqual(pro_regular_amount_egp(), 200.0)

    def test_expired_discount_falls_back_to_base_price(self):
        with (
            patch("api.payment_common.billing_settings", return_value={}),
            patch.dict(
                "os.environ",
                {"PRO_DISCOUNT_PRICE_EGP": "50", "PRO_DISCOUNT_ENDS_AT": self.PAST, "PRO_PRICE_EGP": "200"},
                clear=False,
            ),
        ):
            self.assertFalse(pro_discount()["active"])
            self.assertEqual(plan_amount_egp("pro"), 200.0)

    def test_admin_settings_discount_takes_precedence_over_env(self):
        settings = {
            "discount_enabled": True,
            "discount_price_egp": 75,
            "discount_ends_at": self.FUTURE,
            "pro_price_egp": 250,
        }
        with (
            patch("api.payment_common.billing_settings", return_value=settings),
            patch.dict("os.environ", {"PRO_PRICE_EGP": "200"}, clear=False),
        ):
            self.assertEqual(pro_discount()["price_egp"], 75.0)
            self.assertEqual(plan_amount_egp("pro"), 75.0)
            self.assertEqual(pro_regular_amount_egp(), 250.0)

    def test_admin_disabled_flag_blocks_env_discount(self):
        with (
            patch("api.payment_common.billing_settings", return_value={"discount_enabled": False}),
            patch.dict(
                "os.environ",
                {"PRO_DISCOUNT_PRICE_EGP": "50", "PRO_DISCOUNT_ENDS_AT": self.FUTURE, "PRO_PRICE_EGP": "200"},
                clear=False,
            ),
        ):
            self.assertFalse(pro_discount()["active"])
            self.assertEqual(plan_amount_egp("pro"), 200.0)


class PaymentConfigTests(unittest.TestCase):
    def test_config_exposes_discount_and_has_no_test_plan(self):
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace("+00:00", "Z")
        with (
            patch("api.payment_common.billing_settings", return_value={}),
            patch("api.easykash_payments.is_payments_enabled", return_value=True),
            patch("api.easykash_payments.is_easykash_ready", return_value=True),
            patch.dict(
                "os.environ",
                {
                    "PRO_DISCOUNT_PRICE_EGP": "50",
                    "PRO_DISCOUNT_ENDS_AT": future,
                    "PRO_PRICE_EGP": "200",
                    "PRO_6M_PRICE_EGP": "1000",
                    "PRO_1Y_PRICE_EGP": "1850",
                },
                clear=False,
            ),
        ):
            config = payment_config()
        plan_ids = [plan["id"] for plan in config["plans"]]
        self.assertEqual(plan_ids, ["pro", "pro_6m", "pro_1y", "lifetime", "chat_only", "vip_only"])
        self.assertNotIn("pro_test", plan_ids)
        monthly = config["plans"][0]
        self.assertEqual(monthly["amount_egp"], 50)
        self.assertTrue(monthly["discount"]["active"])
        self.assertEqual(monthly["discount"]["original_amount_egp"], 200)
        self.assertEqual(config["plans"][1]["amount_egp"], 1000)


class SaudiCheckoutParityTests(unittest.TestCase):
    def test_tasi_checkout_converts_sar_anchor_to_honest_egp_across_tiers(self):
        from api.easykash_payments import create_checkout

        expected_cases = [
            ("pro", 20, 255.0),         # 20 SAR * 12.75 = 255 EGP
            ("pro_6m", 100, 1275.0),   # 100 SAR * 12.75 = 1275 EGP
            ("pro_1y", 180, 2295.0),   # 180 SAR * 12.75 = 2295 EGP
            ("lifetime", 225, 2869.0), # round(225 * 12.75) = 2869 EGP
            ("b2b_pro", 150, 1913.0),  # ROUND_HALF_UP(150 * 12.75 = 1912.5) = 1913 EGP
        ]

        class _FakeQuery:
            def __init__(self, table, holder):
                self._table = table
                self._holder = holder

            def select(self, *_a, **_kw):
                return self

            def eq(self, *_a, **_kw):
                return self

            def insert(self, row):
                if self._table == "local_payment_orders":
                    self._holder["row"] = row
                return self

            def update(self, *_a, **_kw):
                return self

            def execute(self):
                if self._table == "local_payment_orders":
                    return type("Resp", (), {"data": [self._holder["row"]], "count": 0})()
                return type("Resp", (), {"data": [], "count": 0})()

        class _FakeSb:
            def __init__(self, holder):
                self._holder = holder

            def table(self, name):
                return _FakeQuery(name, self._holder)

        for plan_id, expected_sar, expected_egp in expected_cases:
            captured_payload = {}
            holder = {}

            def _fake_post(_url, json=None, **_kw):
                captured_payload.update(json or {})
                return type(
                    "Resp",
                    (),
                    {"status_code": 200, "json": staticmethod(lambda: {"redirectUrl": "https://easykash.net/DirectPayV1/testref"})},
                )()

            with (
                patch("api.easykash_payments.is_payments_enabled", return_value=True),
                patch("api.easykash_payments.is_easykash_ready", return_value=True),
                patch("api.easykash_payments._init_supabase"),
                patch("api.easykash_payments.supabase", _FakeSb(holder)),
                patch("api.easykash_payments.is_user_eligible_for_50_egp_renewal", return_value=False),
                patch("api.easykash_payments.is_user_eligible_for_100_egp_renewal", return_value=False),
                patch("api.easykash_payments.founders_offer_is_open", return_value=False),
                patch("api.payment_common.is_user_eligible_for_50_egp_renewal", return_value=False),
                patch("api.payment_common.is_user_eligible_for_100_egp_renewal", return_value=False),
                patch("api.payment_common.founders_offer_is_open", return_value=False),
                patch("api.payment_common.billing_settings", return_value={}),
                patch("api.easykash_payments._required_env", return_value="test-api-key"),
                patch("api.easykash_payments.requests.post", side_effect=_fake_post),
                patch.dict(
                    "os.environ",
                    {
                        "PRO_PRICE_EGP": "200",
                        "PRO_6M_PRICE_EGP": "1000",
                        "PRO_1Y_PRICE_EGP": "1800",
                        "NOTIFY_TELEGRAM_ON_PAYMENT": "false",
                    },
                    clear=False,
                ),
            ):
                res = create_checkout(
                    user_id="user-tasi-1",
                    plan_id=plan_id,
                    email="tasi@example.com",
                    name="TASI Tester",
                    mobile="+966501234567",
                    promo_code="",
                    market="tasi",
                )
            self.assertEqual(res["url"], "https://www.easykash.net/DirectPayV1/testref")
            self.assertEqual(float(holder["row"]["amount_egp"]), expected_egp)
            self.assertEqual(float(captured_payload["amount"]), expected_egp)
            self.assertIn(f"{expected_sar} SAR", holder["row"]["customer_note"])

    def test_tasi_checkout_applies_promo_percent_and_b2b_callback_no_unbound_local(self):
        from api.easykash_payments import create_checkout, process_callback

        captured_payload = {}
        holder = {}

        class _FakeQuery:
            def __init__(self, table):
                self._table = table

            def insert(self, row):
                if self._table == "local_payment_orders":
                    holder["row"] = row
                return self

            def update(self, *_a, **_kw):
                return self

            def eq(self, *_a, **_kw):
                return self

            def execute(self):
                if self._table == "local_payment_orders":
                    return type("Resp", (), {"data": [holder["row"]]})()
                return type("Resp", (), {"data": []})()

        class _FakeSb:
            def table(self, name):
                return _FakeQuery(name)

        promo_data = {
            "valid": True,
            "id": "aff-1",
            "code": "VIP15",
            "user_id": "other-user",
            "discount_percent": 15,
            "commission_percent": 10,
        }

        def _fake_post(_url, json=None, **_kw):
            captured_payload.update(json or {})
            return type(
                "Resp",
                (),
                {"status_code": 200, "json": staticmethod(lambda: {"redirectUrl": "https://easykash.net/DirectPayV1/ok"})},
            )()

        with (
            patch("api.easykash_payments.is_payments_enabled", return_value=True),
            patch("api.easykash_payments.is_easykash_ready", return_value=True),
            patch("api.easykash_payments._init_supabase"),
            patch("api.easykash_payments.supabase", _FakeSb()),
            patch("api.easykash_payments.is_user_eligible_for_50_egp_renewal", return_value=False),
            patch("api.easykash_payments.is_user_eligible_for_100_egp_renewal", return_value=False),
            patch("api.easykash_payments.founders_offer_is_open", return_value=False),
            patch("api.payment_common.is_user_eligible_for_50_egp_renewal", return_value=False),
            patch("api.payment_common.is_user_eligible_for_100_egp_renewal", return_value=False),
            patch("api.payment_common.founders_offer_is_open", return_value=False),
            patch("api.easykash_payments.validate_affiliate_code", return_value=promo_data),
            patch("api.payment_common.billing_settings", return_value={}),
            patch("api.easykash_payments._required_env", return_value="test-api-key"),
            patch("api.easykash_payments.requests.post", side_effect=_fake_post),
            patch.dict("os.environ", {"PRO_PRICE_EGP": "200", "NOTIFY_TELEGRAM_ON_PAYMENT": "false"}, clear=False),
        ):
            create_checkout(
                user_id="user-tasi-2",
                plan_id="pro",
                email="promo@example.com",
                name="Promo Tester",
                mobile="+966509998877",
                promo_code="VIP15",
                market="tasi",
            )
        # 255 EGP - round(255 * 0.15) = 217 EGP (~17 SAR)
        self.assertEqual(float(captured_payload["amount"]), 217.0)

        # Verify process_callback for B2B order when NOTIFY_TELEGRAM_ON_PAYMENT="true" does not raise UnboundLocalError
        order_uuid = "12345678-1234-4234-8234-123456789012"
        b2b_order = {
            "id": order_uuid,
            "user_id": "user-b2b-1",
            "plan_id": "b2b_pro",
            "amount_egp": 1913.0,
            "status": "pending",
            "provider": "easykash",
            "updated_at": "2026-11-15T00:00:00Z",
            "affiliate_id": None,
            "affiliate_code": None,
            "commission_amount_egp": 0,
            "commission_status": None,
            "discount_amount_egp": 0,
            "customer_note": "Market: tasi (~150 SAR)",
        }

        class _CbQuery:
            def __init__(self, table):
                self._table = table
                self._updates = None

            def select(self, *_a, **_kw):
                return self

            def eq(self, *_a, **_kw):
                return self

            def order(self, *_a, **_kw):
                return self

            def limit(self, *_a, **_kw):
                return self

            def maybe_single(self):
                return self

            def update(self, data):
                self._updates = data
                return self

            def execute(self):
                if self._table == "local_payment_orders":
                    if self._updates is None:
                        return type("R", (), {"data": b2b_order})()
                    return type("R", (), {"data": [b2b_order]})()
                if self._table == "b2b_group_licenses":
                    return type("R", (), {"data": {"expires_at": "2026-12-15T00:00:00Z"}})()
                return type("R", (), {"data": None})()

        class _CbSb:
            def table(self, name):
                return _CbQuery(name)

        sent_msgs = []
        callback_body = {
            "customerReference": order_uuid,
            "status": "PAID",
            "Amount": "1913",
            "ProductCode": "b2b_pro",
            "PaymentMethod": "CARD",
            "easykashRef": "EK-B2B-1",
            "ProductType": "subscription",
            "BuyerEmail": "b2b@example.com",
            "BuyerMobile": "+966501112222",
            "BuyerName": "Partner",
            "Timestamp": "20261115",
        }
        with (
            patch("api.easykash_payments._init_supabase"),
            patch("api.easykash_payments.supabase", _CbSb()),
            patch("api.easykash_payments._verify_callback", return_value=True),
            patch("api.easykash_payments.activate_subscription"),
            patch("api.support_chat.load_admin_chat_id", return_value="12345"),
            patch("api.support_chat.send_telegram_message", side_effect=lambda _cid, msg: sent_msgs.append(msg)),
            patch.dict("os.environ", {"NOTIFY_TELEGRAM_ON_PAYMENT": "true"}, clear=False),
        ):
            res = process_callback(callback_body)
        self.assertTrue(res["ok"])
        self.assertTrue(sent_msgs and "B2B_PRO" in sent_msgs[0])


class SplitPlanCheckoutAndEntitlementTests(unittest.TestCase):
    def test_split_and_bundle_checkout_egypt_tasi_and_founders_preservation(self):
        from api.easykash_payments import create_checkout

        class _FakeQuery:
            def __init__(self, table, holder):
                self._table = table
                self._holder = holder

            def select(self, *_a, **_kw):
                return self

            def eq(self, *_a, **_kw):
                return self

            def insert(self, row):
                if self._table == "local_payment_orders":
                    self._holder["row"] = row
                return self

            def update(self, *_a, **_kw):
                return self

            def execute(self):
                if self._table == "local_payment_orders":
                    return type("Resp", (), {"data": [self._holder["row"]], "count": 0})()
                return type("Resp", (), {"data": [], "count": 0})()

        class _FakeSb:
            def __init__(self, holder):
                self._holder = holder

            def table(self, name):
                return _FakeQuery(name, self._holder)

        cases = [
            # (market, plan_id, gf50, gf100, expected_charge_egp, note_substr)
            ("egx", "chat_only", False, False, 100.0, None),
            ("egx", "vip_only", False, False, 100.0, None),
            ("egx", "pro", False, False, 150.0, None),
            ("egx", "pro_6m", False, False, 750.0, None),
            ("egx", "pro_1y", False, False, 1350.0, None),
            ("tasi", "chat_only", False, False, 128.0, "10 SAR"),
            ("tasi", "vip_only", False, False, 128.0, "10 SAR"),
            ("tasi", "pro", False, False, 191.0, "15 SAR"),
            ("tasi", "pro_6m", False, False, 956.0, "75 SAR"),
            ("tasi", "pro_1y", False, False, 1721.0, "135 SAR"),
            # Founders 50 & 100 keep Full Bundle pricing even when offer is closed
            ("egx", "pro", True, False, 50.0, None),
            ("egx", "pro_6m", True, False, 250.0, None),
            ("egx", "pro_1y", True, False, 450.0, None),
            ("egx", "pro", False, True, 100.0, None),
            ("egx", "pro_6m", False, True, 500.0, None),
            ("egx", "pro_1y", False, True, 900.0, None),
            ("tasi", "pro", True, False, 64.0, "5 SAR"),
            ("tasi", "pro", False, True, 128.0, "10 SAR"),
            ("tasi", "pro_6m", False, True, 638.0, "50 SAR"),
        ]

        for market, plan_id, gf50, gf100, expected_egp, note_substr in cases:
            captured_payload = {}
            holder = {}

            def _fake_post(_url, json=None, **_kw):
                captured_payload.update(json or {})
                return type(
                    "Resp",
                    (),
                    {"status_code": 200, "json": staticmethod(lambda: {"redirectUrl": "https://easykash.net/DirectPayV1/splitref"})},
                )()

            with (
                patch("api.easykash_payments.is_payments_enabled", return_value=True),
                patch("api.easykash_payments.is_easykash_ready", return_value=True),
                patch("api.easykash_payments._init_supabase"),
                patch("api.easykash_payments.supabase", _FakeSb(holder)),
                patch("api.easykash_payments.is_user_eligible_for_50_egp_renewal", return_value=gf50),
                patch("api.easykash_payments.is_user_eligible_for_100_egp_renewal", return_value=gf100),
                patch("api.easykash_payments.founders_offer_is_open", return_value=False),
                patch("api.payment_common.is_user_eligible_for_50_egp_renewal", return_value=gf50),
                patch("api.payment_common.is_user_eligible_for_100_egp_renewal", return_value=gf100),
                patch("api.payment_common.founders_offer_is_open", return_value=False),
                patch("api.payment_common.billing_settings", return_value={}),
                patch("api.easykash_payments._required_env", return_value="test-api-key"),
                patch("api.easykash_payments.requests.post", side_effect=_fake_post),
                patch.dict(
                    "os.environ",
                    {
                        "PRO_PRICE_EGP": "150",
                        "PRO_6M_PRICE_EGP": "750",
                        "PRO_1Y_PRICE_EGP": "1350",
                        "CHAT_ONLY_PRICE_EGP": "100",
                        "VIP_ONLY_PRICE_EGP": "100",
                        "NOTIFY_TELEGRAM_ON_PAYMENT": "false",
                    },
                    clear=False,
                ),
            ):
                mobile = "+966501234567" if market == "tasi" else "01012345678"
                res = create_checkout(
                    user_id=f"u-{market}-{plan_id}",
                    plan_id=plan_id,
                    email="split@example.com",
                    name="Split Tester",
                    mobile=mobile,
                    promo_code="",
                    market=market,
                )
            self.assertEqual(res["url"], "https://www.easykash.net/DirectPayV1/splitref")
            self.assertEqual(float(holder["row"]["amount_egp"]), expected_egp)
            self.assertEqual(float(captured_payload["amount"]), expected_egp)
            if note_substr:
                self.assertIn(note_substr, holder["row"]["customer_note"])

    def test_process_callback_skips_vip_invite_for_chat_only_and_issues_for_vip_and_pro(self):
        from api.easykash_payments import process_callback

        for plan_id, expected_vip in [("chat_only", False), ("vip_only", True), ("pro", True)]:
            order_uuid = f"22345678-1234-4234-8234-12345678900{1 if plan_id == 'chat_only' else (2 if plan_id == 'vip_only' else 3)}"
            order_row = {
                "id": order_uuid,
                "user_id": f"u-{plan_id}",
                "plan_id": plan_id,
                "amount_egp": 100.0 if plan_id != "pro" else 150.0,
                "status": "pending",
                "provider": "easykash",
                "updated_at": "2026-11-19T00:00:00Z",
                "affiliate_id": None,
                "affiliate_code": None,
                "commission_amount_egp": 0,
                "commission_status": None,
                "discount_amount_egp": 0,
                "customer_note": "",
            }

            class _SplitCbQuery:
                def __init__(self, table):
                    self._table = table
                    self._updates = None

                def select(self, *_a, **_kw):
                    return self

                def eq(self, *_a, **_kw):
                    return self

                def in_(self, *_a, **_kw):
                    return self

                def order(self, *_a, **_kw):
                    return self

                def limit(self, *_a, **_kw):
                    return self

                def maybe_single(self):
                    return self

                def update(self, data):
                    self._updates = data
                    return self

                def execute(self):
                    if self._table == "local_payment_orders":
                        if self._updates is None:
                            return type("R", (), {"data": order_row})()
                        return type("R", (), {"data": [order_row]})()
                    if self._table == "subscriptions":
                        return type("R", (), {"data": {"current_period_end": "2026-12-19T00:00:00Z"}})()
                    return type("R", (), {"data": None})()

            class _SplitCbSb:
                def table(self, name):
                    return _SplitCbQuery(name)

            invite_calls = []
            welcome_calls = []

            def _fake_ensure(uid, sub_end):
                invite_calls.append((uid, sub_end))
                return {"invite_link": "https://t.me/+fakevip"}

            def _fake_welcome(uid, invite_link="", plan_name="Pro", subscription_end=None, include_vip_invite=True):
                welcome_calls.append((uid, invite_link, plan_name, include_vip_invite))
                return True

            callback_body = {
                "customerReference": order_uuid,
                "status": "PAID",
                "Amount": str(int(order_row["amount_egp"])),
                "ProductCode": plan_id,
                "PaymentMethod": "CARD",
                "easykashRef": f"EK-{plan_id.upper()}",
                "ProductType": "subscription",
                "BuyerEmail": "split@example.com",
                "BuyerMobile": "01012345678",
                "BuyerName": "Split User",
                "Timestamp": "20261119",
            }
            with (
                patch("api.easykash_payments._init_supabase"),
                patch("api.easykash_payments.supabase", _SplitCbSb()),
                patch("api.easykash_payments._verify_callback", return_value=True),
                patch("api.easykash_payments.activate_subscription"),
                patch("api.easykash_payments.ensure_pro_invite", side_effect=_fake_ensure),
                patch("api.telegram_pro_invites.send_pro_welcome_to_user_telegram", side_effect=_fake_welcome),
                patch.dict("os.environ", {"NOTIFY_TELEGRAM_ON_PAYMENT": "false"}, clear=False),
            ):
                res = process_callback(callback_body)

            self.assertTrue(res["ok"])
            self.assertEqual(len(invite_calls), 1 if expected_vip else 0, f"failed for {plan_id}")
            self.assertEqual(len(welcome_calls), 1)
            self.assertEqual(welcome_calls[0][3], expected_vip)
            if not expected_vip:
                self.assertEqual(welcome_calls[0][1], "")

    def test_split_plan_entitlement_isolation(self):
        from datetime import datetime, timezone, timedelta
        from api.perf_utils import has_active_chat_pro, has_active_vip_telegram
        from api.plan_limits import plan_limits

        now = datetime.now(timezone.utc)
        future_iso = (now + timedelta(days=20)).isoformat()
        past_iso = (now - timedelta(days=5)).isoformat()

        chat_rows = [{"plan_id": "chat_only", "status": "active", "current_period_end": future_iso}]
        vip_rows = [{"plan_id": "vip_only", "status": "active", "current_period_end": future_iso}]
        pro_rows = [{"plan_id": "pro", "status": "active", "current_period_end": future_iso}]
        lifetime_rows = [{"plan_id": "lifetime", "status": "active", "current_period_end": None}]
        expired_rows = [{"plan_id": "vip_only", "status": "active", "current_period_end": past_iso}]

        self.assertTrue(has_active_chat_pro(chat_rows, now=now))
        self.assertFalse(has_active_vip_telegram(chat_rows, now=now))

        self.assertFalse(has_active_chat_pro(vip_rows, now=now))
        self.assertTrue(has_active_vip_telegram(vip_rows, now=now))

        self.assertTrue(has_active_chat_pro(pro_rows, now=now))
        self.assertTrue(has_active_vip_telegram(pro_rows, now=now))

        self.assertTrue(has_active_chat_pro(lifetime_rows, now=now))
        self.assertTrue(has_active_vip_telegram(lifetime_rows, now=now))

        self.assertFalse(has_active_chat_pro(expired_rows, now=now))
        self.assertFalse(has_active_vip_telegram(expired_rows, now=now))
        self.assertFalse(has_active_chat_pro([], now=now))
        self.assertFalse(has_active_vip_telegram([], now=now))

        chat_lim = plan_limits("chat_only")
        self.assertEqual(chat_lim["name"], "chat_only")
        self.assertEqual(chat_lim["chat_messages_per_month"], 350)
        self.assertEqual(chat_lim["signal_delay_days"], 0)
        self.assertGreaterEqual(chat_lim["portfolio_stocks"], 10)
        self.assertEqual(chat_lim["price_egp"], 100)

        vip_lim = plan_limits("vip_only")
        self.assertEqual(vip_lim["name"], "vip_only")
        self.assertEqual(vip_lim["chat_messages_per_month"], 10)
        self.assertEqual(vip_lim["signal_delay_days"], 0)
        self.assertEqual(vip_lim["portfolio_stocks"], 5)
        self.assertEqual(vip_lim["price_egp"], 100)

        pro_lim = plan_limits("pro")
        self.assertEqual(pro_lim["name"], "pro")
        self.assertEqual(pro_lim["chat_messages_per_month"], 350)
        self.assertEqual(pro_lim["signal_delay_days"], 0)
        self.assertEqual(pro_lim["price_egp"], 150)

    def test_vip_only_cannot_unlock_chat_automations_portfolio_or_vision(self):
        from datetime import datetime, timezone, timedelta
        from fastapi.testclient import TestClient
        import api.scheduled_automations_worker as worker
        from api.perf_utils import _get_user_plan_flags, _VIEWER_PLAN_CACHE
        from api.routers.offload_user import _portfolio_limit_for_user
        from api.agentic_chat.router import router as chat_router
        from fastapi import FastAPI

        future_iso = (datetime.now(timezone.utc) + timedelta(days=20)).isoformat()

        # 1. scheduled_automations_worker._is_user_pro rejects vip_only, accepts chat_only
        def _fake_sb_req(endpoint, **_kw):
            if endpoint.startswith("profiles"):
                return [{"telegram_chat_id": "777777"}]
            if "u-vip-only" in endpoint:
                return [{"plan_id": "vip_only", "current_period_end": future_iso}]
            if "u-chat-only" in endpoint:
                return [{"plan_id": "chat_only", "current_period_end": future_iso}]
            return []

        with patch.object(worker, "_supabase_request", side_effect=_fake_sb_req):
            self.assertFalse(worker._is_user_pro("u-vip-only"))
            self.assertTrue(worker._is_user_pro("u-chat-only"))

        # 2. _portfolio_limit_for_user keeps vip_only at 5, grants chat_only 15 (Pro limit)
        class _SubQuery:
            def __init__(self, rows):
                self._rows = rows

            def select(self, *_a, **_kw):
                return self

            def eq(self, *_a, **_kw):
                return self

            def in_(self, *_a, **_kw):
                return self

            def order(self, *_a, **_kw):
                return self

            def limit(self, *_a, **_kw):
                return self

            def execute(self):
                return type("R", (), {"data": self._rows})()

        class _FakeSbForPlan:
            def __init__(self, rows):
                self._rows = rows

            def table(self, _name):
                return _SubQuery(self._rows)

        with patch("api.routers.offload_user.is_payments_enabled", return_value=True):
            is_vip_chat, vip_limit = _portfolio_limit_for_user(
                _FakeSbForPlan([{"plan_id": "vip_only", "status": "active", "current_period_end": future_iso}]),
                "u-vip-only",
            )
            is_chat_chat, chat_limit = _portfolio_limit_for_user(
                _FakeSbForPlan([{"plan_id": "chat_only", "status": "active", "current_period_end": future_iso}]),
                "u-chat-only",
            )
        self.assertFalse(is_vip_chat)
        self.assertEqual(vip_limit, 5)
        self.assertTrue(is_chat_chat)
        self.assertGreaterEqual(chat_limit, 10)

        # 3. _get_user_plan_flags returns strictly isolated booleans for vip_only vs chat_only
        _VIEWER_PLAN_CACHE.delete("u-vip-flags")
        _VIEWER_PLAN_CACHE.delete("u-chat-flags")
        vip_sb = _FakeSbForPlan([{"plan_id": "vip_only", "status": "active", "current_period_end": future_iso}])
        chat_sb = _FakeSbForPlan([{"plan_id": "chat_only", "status": "active", "current_period_end": future_iso}])
        with (
            patch("api.perf_utils.is_payments_enabled", return_value=True),
            patch("api.perf_utils.is_unlimited_chat_user", return_value=False),
            patch("api.perf_utils.get_primary_supabase", return_value=vip_sb),
        ):
            vip_flags = _get_user_plan_flags("u-vip-flags", "vip@example.com")
        with (
            patch("api.perf_utils.is_payments_enabled", return_value=True),
            patch("api.perf_utils.is_unlimited_chat_user", return_value=False),
            patch("api.perf_utils.get_primary_supabase", return_value=chat_sb),
        ):
            chat_flags = _get_user_plan_flags("u-chat-flags", "chat@example.com")
        _VIEWER_PLAN_CACHE.delete("u-vip-flags")
        _VIEWER_PLAN_CACHE.delete("u-chat-flags")

        self.assertEqual(vip_flags, {"pro": True, "has_chat_pro": False, "has_vip_access": True})
        self.assertEqual(chat_flags, {"pro": True, "has_chat_pro": True, "has_vip_access": False})

        # 4. /api/ai-chat rejects attached Vision AI images from non-chat-pro users (e.g. vip_only)
        test_app = FastAPI()
        test_app.include_router(chat_router, prefix="/api/ai-chat")
        client = TestClient(test_app)
        with (
            patch("api.agentic_chat.router.get_authenticated_user", return_value={"id": "u-vip-vision", "email": "vip@example.com"}),
            patch("api.agentic_chat.router._init_supabase"),
            patch("api.agentic_chat.router.has_chat_pro_user", return_value=False),
        ):
            resp = client.post(
                "/api/ai-chat",
                json={"message": "حلل الشارت", "images": ["data:image/png;base64,AAA"]},
            )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json().get("error"), "PRO_REQUIRED")

    def test_duration_slider_pricing_all_12_months_and_validation(self):
        from api.payment_common import duration_days_for_months, plan_amount_egp

        expected_pro = {
            1: (30, 150.0), 2: (60, 285.0), 3: (90, 405.0), 4: (120, 525.0),
            5: (150, 645.0), 6: (180, 750.0), 7: (210, 855.0), 8: (240, 960.0),
            9: (270, 1065.0), 10: (300, 1170.0), 11: (330, 1260.0), 12: (365, 1350.0),
        }
        expected_100 = {
            1: 100.0, 2: 190.0, 3: 270.0, 4: 350.0, 5: 430.0, 6: 500.0,
            7: 570.0, 8: 640.0, 9: 710.0, 10: 780.0, 11: 840.0, 12: 900.0,
        }
        expected_50 = {
            1: 50.0, 2: 95.0, 3: 135.0, 4: 175.0, 5: 215.0, 6: 250.0,
            7: 285.0, 8: 320.0, 9: 355.0, 10: 390.0, 11: 420.0, 12: 450.0,
        }

        with (
            patch("api.payment_common.billing_settings", return_value={}),
            patch("api.payment_common.founders_offer_is_open", return_value=False),
            patch("api.payment_common.pro_discount", return_value={"active": False}),
            patch("api.payment_common.is_user_eligible_for_50_egp_renewal", return_value=False),
            patch("api.payment_common.is_user_eligible_for_100_egp_renewal", return_value=False),
            patch.dict("os.environ", {"PRO_PRICE_EGP": "150", "CHAT_ONLY_PRICE_EGP": "100", "VIP_ONLY_PRICE_EGP": "100"}, clear=False),
        ):
            for months, (days, pro_egp) in expected_pro.items():
                self.assertEqual(duration_days_for_months(months), days)
                self.assertEqual(plan_amount_egp("pro", user_id="u-reg", duration_months=months), pro_egp)
                self.assertEqual(plan_amount_egp("chat_only", user_id="u-reg", duration_months=months), expected_100[months])
                self.assertEqual(plan_amount_egp("vip_only", user_id="u-reg", duration_months=months), expected_100[months])

        with (
            patch("api.payment_common.billing_settings", return_value={}),
            patch("api.payment_common.founders_offer_is_open", return_value=False),
            patch("api.payment_common.is_user_eligible_for_50_egp_renewal", return_value=True),
            patch("api.payment_common.is_user_eligible_for_100_egp_renewal", return_value=False),
        ):
            for months, f50_egp in expected_50.items():
                self.assertEqual(plan_amount_egp("pro", user_id="u-f50", duration_months=months), f50_egp)

        with (
            patch("api.payment_common.billing_settings", return_value={}),
            patch("api.payment_common.founders_offer_is_open", return_value=False),
            patch("api.payment_common.is_user_eligible_for_50_egp_renewal", return_value=False),
            patch("api.payment_common.is_user_eligible_for_100_egp_renewal", return_value=True),
        ):
            for months, f100_egp in expected_100.items():
                self.assertEqual(plan_amount_egp("pro", user_id="u-f100", duration_months=months), f100_egp)

        for bad_months in (0, 13, -1, True):
            with self.assertRaises(ValueError):
                plan_amount_egp("chat_only", duration_months=bad_months)

    def test_create_checkout_multi_month_stores_duration_days_and_callback_activates(self):
        from api.easykash_payments import create_checkout, process_callback

        class _FakeQuery:
            def __init__(self, table_name, holder):
                self._table = table_name
                self._holder = holder
                self._data = None

            def select(self, *_a, **_kw):
                return self

            def eq(self, *_a, **_kw):
                return self

            def insert(self, payload):
                if self._table == "local_payment_orders":
                    self._holder["row"] = payload
                return self

            def update(self, payload):
                if self._table == "local_payment_orders":
                    self._holder["updated"] = payload
                return self

            def execute(self):
                if self._table == "local_payment_orders":
                    return type("R", (), {"data": [self._holder.get("row", {})]})()
                return type("R", (), {"data": []})()

        class _FakeSb:
            def __init__(self, holder):
                self._holder = holder

            def table(self, name):
                return _FakeQuery(name, self._holder)

        checkout_cases = [
            # (market, plan_id, months, gf50, expected_days, expected_egp, expected_sar)
            ("egx", "chat_only", 3, False, 90, 270.0, None),
            ("egx", "vip_only", 6, False, 180, 500.0, None),
            ("egx", "pro", 4, False, 120, 525.0, None),
            ("egx", "pro", 6, True, 180, 250.0, None),
            ("tasi", "chat_only", 3, False, 90, 344.0, 27),
            ("tasi", "pro", 2, False, 60, 370.0, 29),
        ]

        for market, plan_id, months, gf50, expected_days, expected_egp, expected_sar in checkout_cases:
            holder = {}
            captured_payload = {}

            def _fake_post(_url, json=None, **_kw):
                captured_payload.update(json or {})
                return type(
                    "Resp",
                    (),
                    {"status_code": 200, "json": staticmethod(lambda: {"redirectUrl": "https://easykash.net/DirectPayV1/dur99"})},
                )()

            with (
                patch("api.easykash_payments.is_payments_enabled", return_value=True),
                patch("api.easykash_payments.is_easykash_ready", return_value=True),
                patch("api.easykash_payments._init_supabase"),
                patch("api.easykash_payments.supabase", _FakeSb(holder)),
                patch("api.easykash_payments.is_user_eligible_for_50_egp_renewal", return_value=gf50),
                patch("api.easykash_payments.is_user_eligible_for_100_egp_renewal", return_value=False),
                patch("api.easykash_payments.founders_offer_is_open", return_value=False),
                patch("api.payment_common.is_user_eligible_for_50_egp_renewal", return_value=gf50),
                patch("api.payment_common.is_user_eligible_for_100_egp_renewal", return_value=False),
                patch("api.payment_common.founders_offer_is_open", return_value=False),
                patch("api.payment_common.billing_settings", return_value={}),
                patch("api.easykash_payments._required_env", return_value="test-api-key"),
                patch("api.easykash_payments.requests.post", side_effect=_fake_post),
                patch.dict("os.environ", {"PRO_PRICE_EGP": "150", "CHAT_ONLY_PRICE_EGP": "100", "VIP_ONLY_PRICE_EGP": "100", "NOTIFY_TELEGRAM_ON_PAYMENT": "false"}, clear=False),
            ):
                mobile = "+966501234567" if market == "tasi" else "01012345678"
                res = create_checkout(
                    user_id=f"u-{market}-{plan_id}-{months}",
                    plan_id=plan_id,
                    email="dur@example.com",
                    name="Duration User",
                    mobile=mobile,
                    market=market,
                    duration_months=months,
                )

            self.assertEqual(res["duration_months"], months)
            self.assertEqual(res["duration_days"], expected_days)
            self.assertEqual(float(holder["row"]["duration_days"]), expected_days)
            self.assertEqual(float(holder["row"]["amount_egp"]), expected_egp)
            self.assertEqual(float(captured_payload["amount"]), expected_egp)
            if expected_sar is not None:
                self.assertEqual(res["display_amount_sar"], expected_sar)
                self.assertIn(f"{expected_sar} SAR", holder["row"]["customer_note"])

        # process_callback forwards stored duration_days=90 to activate_subscription
        order_uuid = "32345678-1234-4234-8234-123456789001"
        order_row = {
            "id": order_uuid,
            "user_id": "u-dur-cb",
            "plan_id": "chat_only",
            "amount_egp": 270.0,
            "duration_days": 90,
            "status": "pending",
            "provider": "easykash",
            "updated_at": "2026-11-19T00:00:00Z",
            "affiliate_id": None,
            "affiliate_code": None,
            "commission_amount_egp": 0,
            "commission_status": None,
            "discount_amount_egp": 0,
            "customer_note": "",
        }

        class _DurCbQuery:
            def __init__(self, table):
                self._table = table
                self._updates = None

            def select(self, *_a, **_kw):
                return self

            def eq(self, *_a, **_kw):
                return self

            def in_(self, *_a, **_kw):
                return self

            def order(self, *_a, **_kw):
                return self

            def limit(self, *_a, **_kw):
                return self

            def maybe_single(self):
                return self

            def update(self, data):
                self._updates = data
                return self

            def execute(self):
                if self._table == "local_payment_orders":
                    return type("R", (), {"data": order_row if self._updates is None else [order_row]})()
                if self._table == "subscriptions":
                    return type("R", (), {"data": {"current_period_end": "2027-02-17T00:00:00Z"}})()
                return type("R", (), {"data": None})()

        class _DurCbSb:
            def table(self, name):
                return _DurCbQuery(name)

        activate_calls = []

        def _fake_activate(uid, pid, provider="easykash", payment_order_id=None, duration_days=None):
            activate_calls.append((uid, pid, provider, payment_order_id, duration_days))

        cb_payload = {
            "customerReference": order_uuid,
            "status": "PAID",
            "Amount": "270",
            "ProductCode": "chat_only",
            "PaymentMethod": "CARD",
            "easykashRef": "EK-DUR-90",
            "ProductType": "subscription",
            "BuyerEmail": "dur@example.com",
            "BuyerMobile": "01012345678",
            "BuyerName": "Duration User",
            "Timestamp": "20261119",
        }
        with (
            patch("api.easykash_payments._init_supabase"),
            patch("api.easykash_payments.supabase", _DurCbSb()),
            patch("api.easykash_payments._verify_callback", return_value=True),
            patch("api.easykash_payments.activate_subscription", side_effect=_fake_activate),
            patch("api.telegram_pro_invites.send_pro_welcome_to_user_telegram", return_value=True),
            patch.dict("os.environ", {"NOTIFY_TELEGRAM_ON_PAYMENT": "false"}, clear=False),
        ):
            cb_res = process_callback(cb_payload)

        self.assertTrue(cb_res.get("ok"))
        self.assertEqual(len(activate_calls), 1)
        self.assertEqual(activate_calls[0], ("u-dur-cb", "chat_only", "easykash", order_uuid, 90))

    def test_uae_and_qatar_checkout_rates_and_market_notes(self):
        from api.easykash_payments import create_checkout

        class _GccFakeQuery:
            def __init__(self, table_name, holder):
                self._table = table_name
                self._holder = holder

            def select(self, *_a, **_kw):
                return self

            def eq(self, *_a, **_kw):
                return self

            def insert(self, payload):
                if self._table == "local_payment_orders":
                    self._holder["row"] = payload
                return self

            def update(self, _payload):
                return self

            def execute(self):
                if self._table == "local_payment_orders":
                    return type("R", (), {"data": [self._holder.get("row", {})]})()
                return type("R", (), {"data": []})()

        class _GccFakeSb:
            def __init__(self, holder):
                self._holder = holder

            def table(self, name):
                return _GccFakeQuery(name, self._holder)

        gcc_cases = [
            # (market, mobile, plan_id, months, expected_egp, expected_display, expected_ccy)
            ("uae", "+971501234567", "chat_only", 1, 130.0, 10, "AED"),
            ("uae", "+971501234567", "pro", 1, 195.0, 15, "AED"),
            ("uae", "+971501234567", "pro", 3, 533.0, 41, "AED"),
            ("qatar", "+97450123456", "chat_only", 1, 132.0, 10, "QAR"),
            ("qatar", "+97450123456", "pro", 1, 197.0, 15, "QAR"),
            ("qatar", "+97450123456", "pro", 3, 539.0, 41, "QAR"),
            ("uae", "+971501234567", "b2b_starter", None, 1300.0, 100, "AED"),
            ("qatar", "+97450123456", "b2b_pro", None, 1973.0, 150, "QAR"),
        ]

        for market, mobile, plan_id, months, expected_egp, expected_display, expected_ccy in gcc_cases:
            holder = {}
            captured_payload = {}

            def _fake_post(_url, json=None, **_kw):
                captured_payload.update(json or {})
                return type(
                    "Resp",
                    (),
                    {"status_code": 200, "json": staticmethod(lambda: {"redirectUrl": "https://easykash.net/DirectPayV1/gcc99"})},
                )()

            with (
                patch("api.easykash_payments.is_payments_enabled", return_value=True),
                patch("api.easykash_payments.is_easykash_ready", return_value=True),
                patch("api.easykash_payments._init_supabase"),
                patch("api.easykash_payments.supabase", _GccFakeSb(holder)),
                patch("api.easykash_payments.is_user_eligible_for_50_egp_renewal", return_value=False),
                patch("api.easykash_payments.is_user_eligible_for_100_egp_renewal", return_value=False),
                patch("api.easykash_payments.founders_offer_is_open", return_value=False),
                patch("api.payment_common.is_user_eligible_for_50_egp_renewal", return_value=False),
                patch("api.payment_common.is_user_eligible_for_100_egp_renewal", return_value=False),
                patch("api.payment_common.founders_offer_is_open", return_value=False),
                patch("api.payment_common.billing_settings", return_value={}),
                patch("api.easykash_payments._required_env", return_value="test-api-key"),
                patch("api.easykash_payments.requests.post", side_effect=_fake_post),
                patch.dict("os.environ", {"PRO_PRICE_EGP": "150", "CHAT_ONLY_PRICE_EGP": "100", "VIP_ONLY_PRICE_EGP": "100", "NOTIFY_TELEGRAM_ON_PAYMENT": "false"}, clear=False),
            ):
                res = create_checkout(
                    user_id=f"u-{market}-{plan_id}-{months}",
                    plan_id=plan_id,
                    email="gcc@example.com",
                    name="GCC Tester",
                    mobile=mobile,
                    market=market,
                    duration_months=months,
                )

            self.assertEqual(res["market"], market)
            self.assertEqual(res["display_amount"], expected_display)
            self.assertEqual(res["display_currency"], expected_ccy)
            self.assertNotIn("display_amount_sar", res)
            self.assertEqual(float(holder["row"]["amount_egp"]), expected_egp)
            self.assertEqual(float(captured_payload["amount"]), expected_egp)
            self.assertIn(f"Market: {market} (~{expected_display} {expected_ccy})", holder["row"]["customer_note"])

    def test_active_subscription_transition_guards_prevent_downgrade_and_wipeout(self):
        from datetime import datetime, timezone, timedelta
        from api.easykash_payments import create_checkout

        future_end = (datetime.now(timezone.utc) + timedelta(days=20)).isoformat()

        def _make_sb(active_plan):
            class _Q:
                def __init__(self, tbl):
                    self._tbl = tbl
                    self._row = {}

                def select(self, *_a, **_kw): return self
                def eq(self, *_a, **_kw): return self
                def order(self, *_a, **_kw): return self
                def limit(self, *_a, **_kw): return self
                def insert(self, payload):
                    self._row = payload
                    return self
                def update(self, _payload): return self
                def execute(self):
                    if self._tbl == "subscriptions":
                        return type("R", (), {"data": [{"plan_id": active_plan, "status": "active", "current_period_end": future_end}]})()
                    if self._tbl == "local_payment_orders":
                        return type("R", (), {"data": [self._row or {"id": "o1"}]})()
                    return type("R", (), {"data": []})()

            class _Sb:
                def table(self, name): return _Q(name)

            return _Sb()

        blocked_pairs = [
            ("lifetime", "pro"),
            ("lifetime", "chat_only"),
            ("pro", "chat_only"),
            ("pro", "vip_only"),
            ("chat_only", "vip_only"),
            ("vip_only", "chat_only"),
        ]
        for current_plan, requested_plan in blocked_pairs:
            with (
                patch("api.easykash_payments.is_payments_enabled", return_value=True),
                patch("api.easykash_payments.is_easykash_ready", return_value=True),
                patch("api.easykash_payments._init_supabase"),
                patch("api.easykash_payments.supabase", _make_sb(current_plan)),
            ):
                with self.assertRaises(ValueError, msg=f"Expected block for {current_plan} -> {requested_plan}"):
                    create_checkout(
                        user_id="u-guard",
                        plan_id=requested_plan,
                        email="g@example.com",
                        name="Guard",
                        mobile="01012345678",
                    )

        # Allowed upgrade (chat_only -> pro) and same-plan renewal (chat_only -> chat_only) must succeed
        for current_plan, requested_plan in [("chat_only", "pro"), ("vip_only", "pro"), ("chat_only", "chat_only")]:
            def _fake_post(_url, json=None, **_kw):
                return type("Resp", (), {"status_code": 200, "json": staticmethod(lambda: {"redirectUrl": "https://easykash.net/DirectPayV1/ok123"})})()

            with (
                patch("api.easykash_payments.is_payments_enabled", return_value=True),
                patch("api.easykash_payments.is_easykash_ready", return_value=True),
                patch("api.easykash_payments._init_supabase"),
                patch("api.easykash_payments.supabase", _make_sb(current_plan)),
                patch("api.easykash_payments.is_user_eligible_for_50_egp_renewal", return_value=False),
                patch("api.easykash_payments.is_user_eligible_for_100_egp_renewal", return_value=False),
                patch("api.easykash_payments.founders_offer_is_open", return_value=False),
                patch("api.payment_common.is_user_eligible_for_50_egp_renewal", return_value=False),
                patch("api.payment_common.is_user_eligible_for_100_egp_renewal", return_value=False),
                patch("api.payment_common.founders_offer_is_open", return_value=False),
                patch("api.payment_common.billing_settings", return_value={}),
                patch("api.easykash_payments._required_env", return_value="test-api-key"),
                patch("api.easykash_payments.requests.post", side_effect=_fake_post),
                patch.dict("os.environ", {"PRO_PRICE_EGP": "150", "CHAT_ONLY_PRICE_EGP": "100", "NOTIFY_TELEGRAM_ON_PAYMENT": "false"}, clear=False),
            ):
                res = create_checkout(
                    user_id="u-guard",
                    plan_id=requested_plan,
                    email="g@example.com",
                    name="Guard",
                    mobile="01012345678",
                )
                self.assertEqual(res["status"], "pending")

    def test_callback_and_sync_preserve_market_note_and_verify_inquire_amount(self):
        from api.easykash_payments import process_callback, sync_easykash_order_status

        order_uuid = "42345678-1234-4234-8234-123456789001"
        saved_updates = []
        order_row = {
            "id": order_uuid,
            "user_id": "u-uae-note",
            "plan_id": "chat_only",
            "amount_egp": 130.0,
            "duration_days": 30,
            "status": "pending",
            "provider": "easykash",
            "updated_at": "2026-11-19T00:00:00Z",
            "customer_note": "Market: uae (~10 AED)",
            "affiliate_id": None,
            "affiliate_code": None,
            "commission_amount_egp": 0,
            "commission_status": None,
            "discount_amount_egp": 0,
        }

        class _NoteQ:
            def __init__(self, tbl):
                self._tbl = tbl
                self._upd = None

            def select(self, *_a, **_kw): return self
            def eq(self, *_a, **_kw): return self
            def in_(self, *_a, **_kw): return self
            def order(self, *_a, **_kw): return self
            def limit(self, *_a, **_kw): return self
            def maybe_single(self): return self
            def update(self, data):
                self._upd = data
                saved_updates.append(dict(data))
                return self
            def execute(self):
                if self._tbl == "local_payment_orders":
                    return type("R", (), {"data": order_row if self._upd is None else [order_row]})()
                if self._tbl == "subscriptions":
                    return type("R", (), {"data": {"current_period_end": "2026-12-19T00:00:00Z"}})()
                return type("R", (), {"data": None})()

        class _NoteSb:
            def table(self, name): return _NoteQ(name)

        # 1. process_callback preserves "Market: uae (~10 AED)" alongside EasyKash reference
        with (
            patch("api.easykash_payments._init_supabase"),
            patch("api.easykash_payments.supabase", _NoteSb()),
            patch("api.easykash_payments._verify_callback", return_value=True),
            patch("api.easykash_payments.activate_subscription"),
            patch("api.telegram_pro_invites.send_pro_welcome_to_user_telegram", return_value=True),
            patch.dict("os.environ", {"NOTIFY_TELEGRAM_ON_PAYMENT": "false"}, clear=False),
        ):
            res = process_callback({
                "customerReference": order_uuid,
                "status": "PAID",
                "Amount": "130",
                "ProductCode": "chat_only",
                "PaymentMethod": "CARD",
                "easykashRef": "EK-UAE-10",
                "ProductType": "subscription",
                "BuyerEmail": "uae@example.com",
                "BuyerMobile": "+971501234567",
                "BuyerName": "UAE User",
                "Timestamp": "20261119",
            })
        self.assertTrue(res.get("ok"))
        approved_updates = [u for u in saved_updates if u.get("status") == "approved"]
        self.assertEqual(len(approved_updates), 1)
        self.assertIn("Market: uae (~10 AED)", approved_updates[0]["customer_note"])
        self.assertIn("EasyKash reference: EK-UAE-10", approved_updates[0]["customer_note"])

        # 2. sync_easykash_order_status rejects mismatched Amount from inquire API
        order_bad = dict(order_row)
        activate_spy = []
        with (
            patch("api.easykash_payments.supabase", _NoteSb()),
            patch("api.easykash_payments.activate_subscription", side_effect=lambda *a, **kw: activate_spy.append(1)),
            patch("api.easykash_payments.requests.post", return_value=type("R", (), {"status_code": 200, "json": staticmethod(lambda: {"status": "PAID", "Amount": "50", "easykashRef": "EK-BAD", "PaymentMethod": "CARD"})})()),
            patch.dict("os.environ", {"EASYKASH_API_KEY": "k"}, clear=False),
        ):
            synced = sync_easykash_order_status(order_bad)
        self.assertEqual(synced["status"], "pending")
        self.assertEqual(len(activate_spy), 0)

    def test_payment_gateway_security_hardening_all_eight_audit_fixes(self):
        from datetime import datetime, timezone
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.direct_wallet_payments import is_direct_wallet_enabled
        from api.routers import direct_wallet as dw_router
        from api.routers import easykash as ek_router
        from api.easykash_payments import sync_easykash_order_status
        from api.payment_common import (
            activate_subscription,
            is_user_eligible_for_50_egp_renewal,
            is_user_eligible_for_100_egp_renewal,
        )

        # 1. Direct wallet kill-switch is permanently False & router returns 410 / no phone leak
        with patch.dict("os.environ", {"PAYMENTS_ENABLED": "true"}, clear=False):
            self.assertFalse(is_direct_wallet_enabled())
        app = FastAPI()
        app.include_router(dw_router.router)
        app.include_router(ek_router.router)
        client = TestClient(app)

        dw_cfg = client.get("/payment/direct-wallet/config")
        self.assertEqual(dw_cfg.status_code, 200)
        self.assertFalse(dw_cfg.json()["enabled"])
        self.assertNotIn("recipient_wallet", dw_cfg.json())

        dw_post = client.post(
            "/payment/direct-wallet/confirm",
            json={"user_id": "u1", "plan_id": "lifetime", "sender_mobile": "01012345678", "transaction_id": "FAKE999"},
        )
        self.assertEqual(dw_post.status_code, 410)

        # 2. /payment/easykash/config ignores unauthenticated ?user_id= probing
        seen_uids = []
        with patch("api.routers.easykash.payment_config", side_effect=lambda user_id=None: (seen_uids.append(user_id), {"enabled": True})[1]):
            res_cfg = client.get("/payment/easykash/config?user_id=victim-uuid")
            self.assertEqual(res_cfg.status_code, 200)
        self.assertEqual(seen_uids, [None])

        # 3. Promo-discounted orders cannot leak Founder 50 or Founder 100 eligibility
        class _CouponOrdersSb:
            def __init__(self, rows):
                self._rows = rows

            def table(self, name):
                outer = self

                class _Q:
                    def __init__(self):
                        self._filters = []

                    def select(self, *_a, **_kw): return self
                    def eq(self, col, val): self._filters.append(("eq", col, val)); return self
                    def in_(self, col, vals): self._filters.append(("in", col, list(vals))); return self
                    def lte(self, col, val): self._filters.append(("lte", col, val)); return self
                    def lt(self, *_a, **_kw): return self
                    def order(self, *_a, **_kw): return self
                    def limit(self, *_a, **_kw): return self

                    def execute(self):
                        if name == "founders_offer_members":
                            return type("R", (), {"data": []})()
                        if name == "subscriptions":
                            return type("R", (), {"data": [{"status": "active", "current_period_end": "2099-01-01T00:00:00Z"}]})()
                        if name == "local_payment_orders":
                            matched = []
                            for r in outer._rows:
                                ok = True
                                for kind, col, val in self._filters:
                                    if kind == "eq" and r.get(col) != val:
                                        ok = False
                                    elif kind == "in" and r.get(col) not in val:
                                        ok = False
                                    elif kind == "lte" and not (r.get(col) is not None and r.get(col) <= val):
                                        ok = False
                                if ok:
                                    matched.append(r)
                            return type("R", (), {"data": matched})()
                        return type("R", (), {"data": []})()

                return _Q()

        coupon_rows = [
            {"id": "o1", "user_id": "u-split", "plan_id": "chat_only", "amount_egp": 50.0, "status": "approved", "discount_amount_egp": 50.0},
            {"id": "o2", "user_id": "u-promo", "plan_id": "pro", "amount_egp": 90.0, "status": "approved", "discount_amount_egp": 60.0},
        ]
        with patch("api.payment_common.supabase", _CouponOrdersSb(coupon_rows)), patch("api.payment_common._init_supabase"):
            self.assertFalse(is_user_eligible_for_50_egp_renewal("u-split"))
            self.assertFalse(is_user_eligible_for_100_egp_renewal("u-promo"))

        # 4. sync_easykash_order_status respects active 300s submitted lease AND never overwrites an approved order on stale FAILED
        now_iso = datetime.now(timezone.utc).isoformat()
        order_sub = {
            "id": "22222222-2222-4222-8222-222222222222",
            "user_id": "u-sub",
            "plan_id": "pro",
            "amount_egp": 150.0,
            "duration_days": 30,
            "status": "submitted",
            "updated_at": now_iso,
            "customer_note": "Market: uae (~15 AED)",
        }
        activate_calls = []
        with (
            patch("api.easykash_payments.activate_subscription", side_effect=lambda *a, **kw: activate_calls.append(1)),
            patch("api.easykash_payments.requests.post", return_value=type("R", (), {"status_code": 200, "json": staticmethod(lambda: {"status": "PAID", "Amount": "150", "easykashRef": "EK-SUB", "PaymentMethod": "CARD"})})()),
            patch.dict("os.environ", {"EASYKASH_API_KEY": "k"}, clear=False),
        ):
            res_sub = sync_easykash_order_status(dict(order_sub))
        self.assertEqual(res_sub["status"], "submitted")
        self.assertEqual(len(activate_calls), 0)

        # Stale FAILED inquiry returns empty update (because row is already approved in DB) -> must not flip local status
        class _ApprovedRaceSb:
            def table(self, _name):
                class _Q:
                    def update(self, *_a, **_kw): return self
                    def eq(self, *_a, **_kw): return self
                    def in_(self, *_a, **_kw): return self
                    def execute(self): return type("R", (), {"data": []})()
                return _Q()

        order_race = {**order_sub, "status": "pending"}
        with (
            patch("api.easykash_payments.supabase", _ApprovedRaceSb()),
            patch("api.easykash_payments.requests.post", return_value=type("R", (), {"status_code": 200, "json": staticmethod(lambda: {"status": "FAILED", "easykashRef": "EK-STALE", "PaymentMethod": "CARD"})})()),
            patch.dict("os.environ", {"EASYKASH_API_KEY": "k"}, clear=False),
        ):
            res_race = sync_easykash_order_status(dict(order_race))
        self.assertEqual(res_race["status"], "pending")

        # 5. activate_subscription passes monthly catalog cents (not 1350 EGP annual total) for pro_1y
        rpc_calls = []
        class _RpcSb:
            def rpc(self, fn, params):
                rpc_calls.append((fn, params))
                return type("E", (), {"execute": lambda self: type("R", (), {"data": None})()})()

        with (
            patch("api.payment_common.supabase", _RpcSb()),
            patch("api.payment_common._init_supabase"),
            patch("api.payment_common.pro_regular_amount_egp", return_value=150.0),
            patch("api.payment_common.founders_offer_is_open", return_value=False),
        ):
            activate_subscription("u-1y", "pro_1y", payment_order_id="33333333-3333-4333-8333-333333333333", duration_days=365)
        self.assertEqual(len(rpc_calls), 1)
        self.assertEqual(rpc_calls[0][1]["p_plan_id"], "pro")
        self.assertEqual(rpc_calls[0][1]["p_price_monthly_cents"], 15000)

        # 6. POST /payment/direct-wallet/confirm with empty {} returns 410 (not 422)
        dw_empty = client.post("/payment/direct-wallet/confirm", json={})
        self.assertEqual(dw_empty.status_code, 410)

        # 7. _has_non_coupon_order fails closed on non-numeric discount_amount_egp
        from api.payment_common import _has_non_coupon_order
        self.assertFalse(_has_non_coupon_order([{"id": "x", "discount_amount_egp": "not-a-number"}]))
        self.assertTrue(_has_non_coupon_order([{"id": "x", "discount_amount_egp": 0}]))
        self.assertTrue(_has_non_coupon_order([{"id": "x", "discount_amount_egp": None}]))

        # 8. sync_easykash_order_status must NOT clobber an active (<300s) submitted lease on FAILED/EXPIRED (even naive timestamp)
        naive_recent = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        submitted_active = {**order_sub, "updated_at": naive_recent}
        update_calls = []

        class _NoClobberSb:
            def table(self, _name):
                class _Q:
                    def update(self, payload): update_calls.append(payload); return self
                    def eq(self, *_a, **_kw): return self
                    def execute(self): return type("R", (), {"data": [{"id": submitted_active["id"]}]})()
                return _Q()

        for ek_st in ("FAILED", "EXPIRED"):
            with (
                patch("api.easykash_payments.supabase", _NoClobberSb()),
                patch("api.easykash_payments.requests.post", return_value=type("R", (), {"status_code": 200, "json": staticmethod(lambda s=ek_st: {"status": s, "easykashRef": "EK-R", "PaymentMethod": "CARD"})})()),
                patch.dict("os.environ", {"EASYKASH_API_KEY": "k"}, clear=False),
            ):
                out = sync_easykash_order_status(dict(submitted_active))
            self.assertEqual(out["status"], "submitted")
        self.assertEqual(update_calls, [])

        # 9. order_status uses .limit(1) (never .maybe_single()) and survives ensure_pro_invite failure
        from api.easykash_payments import order_status as ek_order_status

        class _NoMaybeSingleSb:
            def table(self, name):
                class _Q:
                    def select(self, *_a, **_kw): return self
                    def eq(self, *_a, **_kw): return self
                    def in_(self, *_a, **_kw): return self
                    def order(self, *_a, **_kw): return self
                    def limit(self, *_a, **_kw): return self
                    def maybe_single(self):
                        raise AssertionError("maybe_single() is forbidden under postgrest==0.16.11")
                    def execute(self):
                        if name == "local_payment_orders":
                            return type("R", (), {"data": [{
                                "id": "44444444-4444-4444-8444-444444444444",
                                "user_id": "u-ok",
                                "plan_id": "pro",
                                "amount_egp": 150.0,
                                "duration_days": 30,
                                "status": "approved",
                                "provider": "easykash",
                                "updated_at": now_iso,
                                "telegram_invite_link": "https://t.me/+fallback",
                                "telegram_invite_expires_at": None,
                                "customer_note": "tg_welcomed",
                                "affiliate_id": None,
                                "affiliate_code": None,
                                "commission_amount_egp": 0,
                                "commission_status": "none",
                            }]})()
                        if name == "subscriptions":
                            return type("R", (), {"data": [{"current_period_end": "2099-01-01T00:00:00Z"}]})()
                        return type("R", (), {"data": []})()
                return _Q()

        with (
            patch("api.easykash_payments.supabase", _NoMaybeSingleSb()),
            patch("api.easykash_payments._init_supabase"),
            patch("api.easykash_payments.ensure_pro_invite", side_effect=RuntimeError("telegram down")),
        ):
            st = ek_order_status("44444444-4444-4444-8444-444444444444", "u-ok")
        self.assertEqual(st["status"], "approved")
        self.assertEqual(st["telegram_pro_url"], "https://t.me/+fallback")

        # 10. payment_config sets founders_lock_rate == 50 on pro_6m & pro_1y for grandfathered-50 users
        from api.easykash_payments import payment_config as ek_payment_config
        with (
            patch("api.payment_common.is_user_eligible_for_50_egp_renewal", return_value=True),
            patch("api.payment_common.is_user_eligible_for_100_egp_renewal", return_value=False),
            patch("api.payment_common.founders_offer_is_open", return_value=False),
            patch("api.payment_common.billing_settings", return_value={}),
            patch("api.easykash_payments.billing_settings", return_value={}),
            patch("api.easykash_payments.pro_discount", return_value={"active": False, "price_egp": None, "ends_at": None}),
            patch("api.easykash_payments.supabase", None),
        ):
            cfg50 = ek_payment_config(user_id="founder-50-user")
        p50 = {p["id"]: p for p in cfg50["plans"]}
        self.assertEqual(p50["pro_6m"]["amount_egp"], 250)
        self.assertEqual(p50["pro_6m"]["founders_lock_rate"], 50)
        self.assertEqual(p50["pro_1y"]["amount_egp"], 450)
        self.assertEqual(p50["pro_1y"]["founders_lock_rate"], 50)


if __name__ == "__main__":
    unittest.main()
