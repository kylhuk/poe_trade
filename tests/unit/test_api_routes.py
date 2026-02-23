import unittest

from fastapi.testclient import TestClient

from poe_trade.api import get_app

client = TestClient(get_app())


class ApiRoutesTest(unittest.TestCase):
    def test_health_and_meta(self):
        health = client.get("/healthz")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json().get("status"), "ok")

        services = client.get("/v1/meta/services")
        self.assertEqual(services.status_code, 200)
        self.assertIn("services", services.json())

    def test_item_analyze_contract(self):
        payload = {
            "source": "cli",
            "text": "divine orb documented",
            "league": "Sanctum",
        }
        response = client.post("/v1/item/analyze", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["parsed"]["fp_loose"], "divine")
        self.assertIn("price", data)
        self.assertIn("craft", data)
        self.assertIn("flags", data)

    def test_pricing_endpoints(self):
        snapshot = client.post(
            "/v1/pricing/snapshot-estimate",
            json={"items": [{"league": "Sanctum", "fp_loose": "divine", "count": 1}]},
        )
        self.assertEqual(snapshot.status_code, 200)
        estimates = snapshot.json()["estimates"]
        self.assertTrue(estimates)
        self.assertEqual(estimates[0]["fp_loose"], "divine")
        estimate = estimates[0]
        self.assertEqual(estimate["count"], 1)
        self.assertEqual(estimate["total_est"], estimate["price"]["est"])
        multi = client.post(
            "/v1/pricing/snapshot-estimate",
            json={"items": [{"league": "Sanctum", "fp_loose": "divine", "count": 3}]},
        ).json()["estimates"][0]
        self.assertEqual(multi["count"], 3)
        expected_total = round(multi["price"]["est"] * multi["count"], 3)
        self.assertEqual(multi["total_est"], expected_total)

        item = client.get("/v1/pricing/item-estimate", params={"fp_loose": "divine", "league": "Sanctum"})
        self.assertEqual(item.status_code, 200)
        self.assertEqual(item.json()["fp_loose"], "divine")

    def test_flips_crafts_endpoints(self):
        flips = client.get("/v1/flips")
        self.assertEqual(flips.status_code, 200)
        self.assertTrue(flips.json().get("flips"))
        flips_top = client.get("/v1/flips/top")
        self.assertEqual(flips_top.status_code, 200)
        self.assertEqual(flips_top.json().get("flips"), flips.json().get("flips"))

        crafts = client.get("/v1/crafts")
        self.assertEqual(crafts.status_code, 200)
        self.assertTrue(crafts.json().get("crafts"))
        crafts_top = client.get("/v1/crafts/top")
        self.assertEqual(crafts_top.status_code, 200)
        self.assertEqual(crafts_top.json().get("crafts"), crafts.json().get("crafts"))

    def test_sessions_flow(self):
        session_id = "test-session"
        start_payload = {
            "session_id": session_id,
            "realm": "pc",
            "league": "Sanctum",
            "start_snapshot": "start-001",
            "start_value": 10.0,
        }
        start_resp = client.post("/v1/sessions/start", json=start_payload)
        self.assertEqual(start_resp.status_code, 200)
        self.assertEqual(start_resp.json().get("status"), "started")

        end_payload = {
            "session_id": session_id,
            "end_snapshot": "end-001",
            "end_value": 22.5,
        }
        end_resp = client.post("/v1/sessions/end", json=end_payload)
        self.assertEqual(end_resp.status_code, 200)
        self.assertEqual(end_resp.json().get("status"), "ended")

        leaderboard = client.get("/v1/sessions/leaderboard")
        self.assertEqual(leaderboard.status_code, 200)
        leaderboard_ids = {entry["session_id"] for entry in leaderboard.json().get("leaderboard", [])}
        self.assertIn(session_id, leaderboard_ids)

    def test_strategy_and_advisor(self):
        strategies = client.get("/v1/strategies/backtest")
        self.assertEqual(strategies.status_code, 200)
        self.assertTrue(strategies.json().get("strategies"))

        advisor = client.post("/v1/advisor/daily-plan", json={})
        self.assertEqual(advisor.status_code, 200)
        plan_items = advisor.json().get("plan_items", [])
        self.assertTrue(plan_items)
        self.assertTrue(plan_items[0]["tool_ref"].startswith("tool:"))

    def test_atlas_endpoints(self):
        builds = client.get("/v1/atlas/builds")
        self.assertEqual(builds.status_code, 200)
        build_list = builds.json()
        self.assertTrue(build_list)
        build_id = build_list[0]["build_id"]

        detail = client.get(f"/v1/atlas/builds/{build_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertIn("nodes", detail.json())

        detail_alias = client.get(f"/v1/builds/{build_id}")
        self.assertEqual(detail_alias.status_code, 200)
        self.assertEqual(detail_alias.json().get("build_id"), build_id)

        export = client.get(f"/v1/atlas/builds/{build_id}/export")
        self.assertEqual(export.status_code, 200)
        self.assertEqual(export.json().get("build_id"), build_id)

        export_alias = client.get(f"/v1/builds/{build_id}/export")
        self.assertEqual(export_alias.status_code, 200)
        self.assertEqual(export_alias.json().get("build_id"), build_id)

        run = client.post("/v1/atlas/runs", json={"build_id": build_id})
        self.assertEqual(run.status_code, 200)
        run_data = run.json()
        self.assertIn("run_id", run_data)
        self.assertTrue(run_data["tool_ref"].endswith(run_data["run_id"]))

        surprise = client.post("/v1/atlas/surprise")
        self.assertEqual(surprise.status_code, 200)
        self.assertIn("tool_ref", surprise.json())
        self.assertIn("templates", surprise.json().get("message", ""))

        coach = client.post("/v1/atlas/coach/plan")
        self.assertEqual(coach.status_code, 200)
        self.assertTrue(coach.json().get("actions"))
        instruction = coach.json().get("actions", [])[0]["instruction"]
        self.assertIn("target_power", instruction)


    def test_compatibility_routes(self):
        payload = {"items": [{"league": "Sanctum", "fp_loose": "divine", "count": 1}]}
        stash = client.post("/v1/stash/price", json=payload)
        self.assertEqual(stash.status_code, 200)
        stash_estimate = stash.json()["estimates"][0]
        self.assertEqual(stash_estimate["fp_loose"], "divine")
        search = client.get("/v1/builds/search", params={"q": "anything"})
        self.assertEqual(search.status_code, 200)
        self.assertTrue(search.json())

    def test_ops_dashboard_route(self):
        dashboard = client.get("/v1/ops/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        payload = dashboard.json()
        self.assertIn("ingest_rate", payload)
        self.assertTrue(payload.get("checkpoint_health"))
        self.assertTrue(payload.get("slo_status"))
        self.assertEqual(payload["checkpoint_health"][0]["cursor_name"], "stash_cursor")

    def test_flip_craft_timestamps_are_deterministic(self):
        first_flips = client.get("/v1/flips").json().get("flips", [])
        second_flips = client.get("/v1/flips").json().get("flips", [])
        self.assertTrue(first_flips)
        self.assertEqual(first_flips[0]["detected_at"], second_flips[0]["detected_at"])
        self.assertEqual(first_flips[0]["expiry_ts"], second_flips[0]["expiry_ts"])
        first_crafts = client.get("/v1/crafts").json().get("crafts", [])
        second_crafts = client.get("/v1/crafts").json().get("crafts", [])
        self.assertTrue(first_crafts)
        self.assertEqual(first_crafts[0]["detected_at"], second_crafts[0]["detected_at"])
