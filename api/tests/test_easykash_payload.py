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
        self.assertEqual(plan_ids, ["pro", "pro_6m", "pro_1y", "lifetime"])
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


if __name__ == "__main__":
    unittest.main()
