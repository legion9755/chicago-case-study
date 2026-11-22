"""
Frontend logic without the UI: helpers, chart builders and the PNG/ZIP export.

    python -m unittest discover -s tests -v
"""
import io
import json
import unittest
import zipfile

import _support  # noqa: F401  (database copy + backend + environment)
from lib.api import api, error_message, is_no_match
from lib.charts import CHARTS, LIGHT, crimes_per_year, query_for, zip_all
from lib.export import FIGURES, render_png
from lib.records import changed_fields, explain


class Helpers(unittest.TestCase):
    def test_is_no_match(self):
        self.assertTrue(is_no_match(404, {"detail": "No crimes match the selected filters"}))
        self.assertFalse(is_no_match(404, {"detail": "Unknown resource 'analytics'"}))
        self.assertFalse(is_no_match(200, {}))

    def test_outdated_backend_message(self):
        self.assertIn("restart it", error_message(404, {"detail": "Unknown resource 'analytics'"}))

    def test_changed_fields(self):
        current = {"name": "A", "population": 10, "area": 1.5}
        self.assertEqual(changed_fields({"name": "A", "population": 12, "area": 1.5}, current), {"population": 12})
        self.assertEqual(changed_fields(current, current), {})

    def test_explain(self):
        title, msg = explain(400, {"detail": {"validation_errors": {"area": "could not convert string to float: 'x'"}}})
        self.assertEqual(title, "Please fix these fields")
        self.assertIn("must be a number", msg)
        self.assertEqual(explain(409, {"detail": "it is referenced by 3 crime record(s)"})[0], "Record in use")


class ChartBuilders(unittest.TestCase):
    def test_every_chart_builds(self):
        for c in CHARTS.values():
            with self.subTest(chart=c.key):
                status, r = api("GET", c.endpoint, params=query_for(c, {}))
                self.assertEqual(status, 200)
                option, table = c.build(r, LIGHT)
                self.assertIsNotNone(option)
                self.assertFalse(table.empty)
                self.assertTrue(c.insight(r))

    def test_year_chart_has_no_empty_series(self):
        _, r = api("GET", "/analytics/crimes-by-year")
        option, _ = crimes_per_year(r, LIGHT)
        self.assertEqual([s["name"] for s in option["series"]], ["Incomplete year"])   # no year is complete


class Export(unittest.TestCase):
    def test_every_chart_has_an_export_renderer(self):
        self.assertEqual(set(FIGURES), set(CHARTS))

    def test_png(self):
        _, r = api("GET", "/analytics/crimes-by-month")
        png = render_png("uc2_q3_crimes_by_month", json.dumps(r), r["insight"])
        self.assertTrue(png.startswith(b"\x89PNG"))

    def test_zip_has_every_chart(self):
        z = zipfile.ZipFile(io.BytesIO(zip_all(json.dumps({}))))
        names = set(z.namelist())
        self.assertEqual(names, {f"{k}.png" for k in CHARTS} | {"insights.txt"})


if __name__ == "__main__":
    unittest.main()
