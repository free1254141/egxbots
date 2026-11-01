"""
api/tests/test_automations_router.py — Unit Tests for Automations Router Endpoints.
"""

import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from api.main import app


class TestAutomationsRouter(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_sync_endpoint(self):
        with patch("api.routers.automations.sync_automations_cache", return_value=3):
            response = self.client.post("/automations/sync")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data["ok"])
            self.assertEqual(data["active_count"], 3)

    def test_status_endpoint(self):
        with patch("api.routers.automations.sync_automations_cache", return_value=5):
            response = self.client.get("/automations/status")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data["ok"])
            self.assertEqual(data["cached_automations"], 5)

    def test_test_run_not_found(self):
        with patch("api.routers.automations._supabase_request", return_value=[]):
            response = self.client.post("/automations/test-run", json={"automation_id": "non-existent-id"})
            self.assertEqual(response.status_code, 404)

    def test_test_run_success(self):
        fake_auto = {
            "id": "auto-xyz",
            "user_id": "u-xyz",
            "name": "Test Auto",
            "prompt": "Test query",
            "scheduled_time": "11:00",
        }
        with patch("api.routers.automations._supabase_request", return_value=[fake_auto]), \
             patch("api.routers.automations.execute_single_automation", return_value={"ok": True, "status": "success"}):
            response = self.client.post("/automations/test-run", json={"automation_id": "auto-xyz"})
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data["ok"])


if __name__ == "__main__":
    unittest.main()
