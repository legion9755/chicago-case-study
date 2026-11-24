"""
REST API tests (Flask test client, database copy).

    python -m unittest discover -s tests -v
"""
import unittest

import _support  # noqa: F401  (database copy + environment)

client = _support.app.test_client()

ANALYTICS = ["summary", "crimes-by-year", "categories", "arrest-rate-by-category", "arrest-rate-by-year",
             "heatmap", "crimes-by-month", "crimes-by-hour", "top-communities", "community-outliers",
             "correlation", "filters",
             "views/vw_crime_yearly", "views/vw_crime_by_category"]


class Analytics(unittest.TestCase):
    def test_health(self):
        r = client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json["status"], "ok")

    def test_every_endpoint_answers(self):
        for name in ANALYTICS:
            with self.subTest(endpoint=name):
                self.assertEqual(client.get(f"/api/analytics/{name}").status_code, 200)

    def test_summary_totals(self):
        s = client.get("/api/analytics/summary").json["data"]
        self.assertEqual(s["total_crimes"], 498)
        self.assertEqual(s["arrests"], 124)

    def test_arrest_filter_partitions_the_data(self):
        total = client.get("/api/analytics/summary").json["data"]["total_crimes"]
        yes = client.get("/api/analytics/summary?arrest=true").json["data"]["total_crimes"]
        no = client.get("/api/analytics/summary?arrest=false").json["data"]["total_crimes"]
        self.assertEqual(yes + no, total)

    def test_bad_flag_is_400(self):
        r = client.get("/api/analytics/summary?domestic=maybe")
        self.assertEqual(r.status_code, 400)
        self.assertIn("true or false", r.json["detail"])

    def test_no_match_is_404_with_message(self):
        r = client.get("/api/analytics/summary?crime_type=HOMICIDE&community=32")
        self.assertEqual(r.status_code, 404)
        self.assertIn("match", r.json["detail"])

    def test_insight_wording(self):
        r = client.get("/api/analytics/arrest-rate-by-year").json
        self.assertIn("only 1 year has ≥30 crimes", r["insight"])
        self.assertNotIn("(s)", r["insight"])
        r = client.get("/api/analytics/arrest-rate-by-category").json
        self.assertIn("from 100% for Narcotics to 0% for", r["insight"])
        self.assertNotRegex(r["insight"], r"\d\.0%")             # one format: 100%, not 100.0%

    def test_unknown_view_is_404(self):
        self.assertEqual(client.get("/api/analytics/views/nope").status_code, 404)


class Crud(unittest.TestCase):
    """Create → read → update → replace → delete on the database copy."""

    def test_round_trip(self):
        base = "/api/communities"
        r = client.post(base, json={"community_code": 950, "community_name": "Test Area", "population": 100})
        self.assertEqual(r.status_code, 201, r.json)
        self.assertEqual(client.post(base, json={"community_code": 950, "community_name": "Dup"}).status_code, 409)
        self.assertEqual(client.get(f"{base}/950").json["community_name"], "Test Area")

        r = client.patch(f"{base}/950", json={"population": 250})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json["changed_fields"], {"population": {"old": 100, "new": 250}})

        r = client.put(f"{base}/950", json={"community_name": "Renamed"})
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json["item"]["population"])           # PUT: unspecified fields become NULL

        self.assertEqual(client.delete(f"{base}/950").status_code, 200)
        self.assertEqual(client.get(f"{base}/950").status_code, 404)

    def test_validation_errors(self):
        r = client.post("/api/communities", json={"community_code": 951, "community_name": "x", "area_sqmile": "abc"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("area_sqmile", r.json["detail"]["validation_errors"])
        r = client.post("/api/communities", json={"community_code": 952})
        self.assertIn("community_name", r.json["detail"]["validation_errors"])

    def test_referenced_record_cannot_be_deleted(self):
        r = client.delete("/api/communities/25")
        self.assertEqual(r.status_code, 409)
        self.assertIn("referenced by", r.json["detail"])
        self.assertEqual(client.get("/api/communities/25").status_code, 200)


if __name__ == "__main__":
    unittest.main()
