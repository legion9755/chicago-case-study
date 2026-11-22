"""
Page tests with Streamlit's AppTest: every page renders, filters change the numbers and
empty states work. (Clicking table rows and dialog buttons needs a real browser.)

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

    # ---- Insights (start page) ----------------------------------------------
    def test_insights(self):
        at = self.open()
        self.assertEqual(metric(at, "Crimes"), "498")
        self.assertEqual(len(at.get("echarts_chart")), 8)
        self.assertFalse(at.error)

    def test_insights_filters(self):
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

    def test_insights_sections(self):
        at = self.open()
        for section, charts in (("Statistical insights", 3), ("SQL views", 2)):
            at.get_by_key("section").set_value(section).run()
            self.assertFalse(at.exception)
            self.assertEqual(len(at.get("echarts_chart")), charts, section)

    # ---- Data admin ----------------------------------------------------------
    def test_admin(self):
        at = self.open("app_pages/admin.py")
        self.assertEqual(len(at.dataframe[0].value), 77)
        at.get_by_key("table").set_value("Police districts / stations").run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.dataframe[0].value), 22)


if __name__ == "__main__":
    unittest.main()
