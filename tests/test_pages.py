"""
Page tests with Streamlit's AppTest: every page renders, filters change the numbers, links and
empty states work. (Clicking table rows, map points and dialog buttons needs a real browser.)

    python -m unittest discover -s tests -v
"""
import unittest

import _support
from streamlit.testing.v1 import AppTest

ENTRYPOINT = str(_support.FRONTEND / "streamlit_app.py")


def metric(at: AppTest, label: str) -> str:
    return next(m.value for m in at.metric if m.label == label)


class Pages(unittest.TestCase):
    def open(self, page: str | None = None, **query: str) -> AppTest:
        at = AppTest.from_file(ENTRYPOINT, default_timeout=60)
        for key, value in query.items():
            at.query_params[key] = value
        at.run()
        if page:
            at.switch_page(page).run()
        self.assertFalse(at.exception, at.exception)
        return at

    # ---- Overview ------------------------------------------------------------
    def test_overview(self):
        at = self.open()
        self.assertEqual(metric(at, "Crimes"), "498")
        self.assertEqual(metric(at, "Community areas"), "70 of 77")
        self.assertEqual(len(at.get("echarts_chart")), 2)
        self.assertEqual(len(at.get("deck_gl_json_chart")), 1)
        self.assertEqual(at.get_by_key("overview_map").value, "Points")     # map opens on Points
        self.assertFalse(at.error)

    def test_overview_filters(self):
        at = self.open()
        at.multiselect(key="crime_type").select("THEFT").run()
        self.assertEqual(metric(at, "Crimes"), "105")
        at.get_by_key("crime_type").set_value([]).run()
        at.get_by_key("arrest").set_value("Yes").run()
        self.assertEqual(metric(at, "Crimes"), "124")
        self.assertEqual(metric(at, "Arrest rate"), "100.0%")

    def test_no_match_empty_state(self):
        at = self.open(crime_type="HOMICIDE", community="Loop")
        self.assertIn("Try a wider year range", at.info[0].value)
        self.assertFalse(at.metric)               # stops before the KPIs
        self.assertFalse(at.error)

    # ---- Insights ------------------------------------------------------------
    def test_insights_sections(self):
        at = self.open("app_pages/insights.py")
        self.assertEqual(len(at.get("echarts_chart")), 8)
        for section, charts in (("Statistical insights", 3), ("SQL views", 2)):
            at.get_by_key("section").set_value(section).run()
            self.assertFalse(at.exception)
            self.assertEqual(len(at.get("echarts_chart")), charts, section)

    # ---- Communities ---------------------------------------------------------
    def test_communities_directory(self):
        at = self.open("app_pages/communities.py")
        self.assertEqual(len(at.dataframe[0].value), 77)
        self.assertEqual(metric(at, "Areas with crimes"), "70 of 77")

    def test_community_detail(self):
        at = self.open("app_pages/communities.py", area="Austin")
        self.assertEqual(metric(at, "Crimes"), "34")
        self.assertEqual(at.header[0].value, "Austin")
        self.assertEqual(len(at.get("echarts_chart")), 2)
        at.button(key="back_to_directory").click().run()
        self.assertEqual(len(at.dataframe[0].value), 77)

    def test_community_without_crimes(self):
        at = self.open("app_pages/communities.py", area="Beverly")
        self.assertIn("No crimes in Beverly", at.info[0].value)

    # ---- Data admin / System -------------------------------------------------
    def test_admin(self):
        at = self.open("app_pages/admin.py")
        self.assertEqual(len(at.dataframe[0].value), 77)
        at.get_by_key("table").set_value("Police districts / stations").run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.dataframe[0].value), 22)

    def test_system(self):
        at = self.open("app_pages/system.py")
        self.assertFalse(at.error)


if __name__ == "__main__":
    unittest.main()
