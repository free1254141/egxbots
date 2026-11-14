import unittest
from unittest.mock import MagicMock, patch
import json
import time

from api.agentic_chat.tools_execution import (
    _sync_get_stock,
    _sync_get_market,
    _sync_get_recommendations,
    _sync_get_technical_scan,
    _sync_get_accumulation_stocks,
)
from api.agentic_chat.pipeline import run_agentic_chat_stream


class TestToolsExecutionAndTables(unittest.TestCase):

    @patch("api.agentic_chat.tools_execution._get_sb")
    def test_sync_get_stock_supports_and_clean_names(self, mock_get_sb):
        mock_sb = MagicMock()
        mock_get_sb.return_value = mock_sb

        # Mock stock_prices
        mock_sb.from_().select().eq().in_().order().limit().execute.return_value.data = [
            {"symbol": "COMI", "high": 90.0, "low": 85.0, "close": 88.0, "date": "2026-11-10"},
            {"symbol": "COMI", "high": 89.0, "low": 84.0, "close": 86.0, "date": "2026-11-09"},
        ]
        # Mock stocks table
        mock_sb.from_().select().eq().limit().execute.return_value.data = [
            {"symbol": "COMI", "name": "Commercial International Bank", "name_ar": "البنك التجاري الدولي, CIB"}
        ]
        # Mock stock_technical_indicators
        mock_sb.from_().select().eq().eq().order().limit().execute.return_value.data = [
            {
                "date": "2026-11-10",
                "close": 88.0,
                "change_pct": 2.3,
                "rsi_14": 55.0,
                "bb_upper": 92.0,
                "bb_lower": 83.0,
                "king_ai_score": 85.0,
                "egx_ai_score": 80.0,
            }
        ]

        res = _sync_get_stock(["COMI"])
        self.assertEqual(res["status"], "success")
        self.assertTrue(len(res["stocks"]) > 0)
        stock = res["stocks"][0]
        self.assertEqual(stock["symbol"], "COMI")
        # Name should be cleaned of ", CIB"
        self.assertEqual(stock["name_ar"], "البنك التجاري الدولي")
        self.assertEqual(stock["support_1"], 84.0)
        self.assertEqual(stock["resistance_1"], 90.0)
        self.assertEqual(stock["king_ai_score"], 85.0)
        self.assertIn("إيجابي", stock["verdict"])

    @patch("api.agentic_chat.tools_execution._get_sb")
    def test_sync_get_recommendations_valid_columns(self, mock_get_sb):
        mock_sb = MagicMock()
        mock_get_sb.return_value = mock_sb

        mock_sb.from_().select().in_().order().limit().execute.return_value.data = [
            {
                "id": 1,
                "symbol": "EKHO",
                "name": "Egyptian Kuwaiti Holding, القابضة المصرية الكويتية",
                "signal": "BUY",
                "entry_price": 0.85,
                "target_price": 1.05,
                "stop_loss": 0.78,
                "status": "open",
                "created_at": "2026-11-10T10:00:00Z",
                "model_name": "Wyckoff V3",
            }
        ]

        res = _sync_get_recommendations(status="open")
        self.assertEqual(res["status"], "success")
        self.assertEqual(len(res["recommendations"]), 1)
        rec = res["recommendations"][0]
        self.assertEqual(rec["symbol"], "EKHO")
        # Ensure strategy came from model_name
        self.assertEqual(rec["strategy"], "Wyckoff V3")
        # Name cleaned
        self.assertNotIn(",", rec["name"])

    @patch("api.agentic_chat.tools_execution._get_sb")
    def test_sync_get_technical_scan_and_accumulation(self, mock_get_sb):
        mock_sb = MagicMock()
        mock_get_sb.return_value = mock_sb

        # Mock stock_technical_indicators (both latest date probe and filtered scan)
        sample_rows = [
            {
                "symbol": "TMGH",
                "date": "2026-11-10",
                "close": 60.0,
                "change_pct": 1.5,
                "rsi_14": 52.0,
                "bb_upper": 65.0,
                "bb_lower": 55.0,
                "king_ai_score": 90.0,
                "egx_ai_score": 88.0,
            }
        ]
        mock_sb.from_().select().eq().order().limit().execute.return_value.data = sample_rows
        mock_sb.from_().select().eq().eq().order().limit().execute.return_value.data = sample_rows

        res = _sync_get_technical_scan(preset="top_gainers")
        self.assertEqual(res["status"], "success")
        self.assertTrue(len(res["stocks"]) > 0)
        s = res["stocks"][0]
        self.assertEqual(s["symbol"], "TMGH")
        self.assertEqual(s["support_1"], 55.0)
        self.assertEqual(s["resistance_1"], 65.0)
        self.assertEqual(s["king_ai_score"], 90.0)
        self.assertIn("إيجابي", s["verdict"])

    @patch("api.agentic_chat.tools_execution._get_sb")
    def test_sync_get_market_egx30_prices(self, mock_get_sb):
        mock_sb = MagicMock()
        mock_get_sb.return_value = mock_sb

        mock_sb.from_().select().eq().limit().execute.return_value.data = []
        mock_sb.from_().select().eq().order().limit().execute.return_value.data = [
            {"close": 31250.0, "date": "2026-11-10"},
            {"close": 30800.0, "date": "2026-11-09"},
        ]

        res = _sync_get_market()
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["egx30_close"], 31250.0)
        self.assertAlmostEqual(res["egx30_change_pct"], 1.46, places=2)
        self.assertEqual(res["date"], "2026-11-10")

    def test_pipeline_table_deduplication_and_headers(self):
        # Test merging logic extracted from pipeline
        tables_data = [
            {"symbol": "COMI", "name_ar": "البنك التجاري الدولي, CIB", "close": 88.0, "support_1": "—"},
            {"symbol": "comi", "name_ar": "البنك التجاري الدولي", "support_1": 84.0, "resistance_1": 90.0, "king_ai_score": 85.0},
            {"symbol": "TMGH", "name_ar": "مجموعة طلعت مصطفى, TMG", "close": 60.0, "support_1": 55.0, "resistance_1": 65.0},
        ]
        merged_stocks = {}
        for s in tables_data:
            if not isinstance(s, dict) or not s.get("symbol"):
                continue
            sym = str(s["symbol"]).upper().strip()
            if sym not in merged_stocks:
                merged_stocks[sym] = dict(s)
            else:
                for k, v in s.items():
                    if v is not None and v != "" and v != "—":
                        if merged_stocks[sym].get(k) is None or merged_stocks[sym].get(k) == "" or merged_stocks[sym].get(k) == "—":
                            merged_stocks[sym][k] = v

        stocks_with_symbol = list(merged_stocks.values())[:10]
        self.assertEqual(len(stocks_with_symbol), 2)
        comi = next(s for s in stocks_with_symbol if s["symbol"].upper() == "COMI")
        # COMI should have enriched support_1 = 84.0 instead of "—"
        self.assertEqual(comi["support_1"], 84.0)
        self.assertEqual(comi["close"], 88.0)

        # Header check: clean name
        headers = ["المعيار"] + [f"{(s.get('name_ar') or s.get('symbol')).split(',')[0].strip()} ({s.get('symbol')})" for s in stocks_with_symbol]
        self.assertEqual(headers[1], "البنك التجاري الدولي (COMI)")
        self.assertEqual(headers[2], "مجموعة طلعت مصطفى (TMGH)")



if __name__ == "__main__":
    unittest.main()
