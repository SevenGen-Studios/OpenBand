import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import build_analytics_config


class AnalyticsConfigTests(unittest.TestCase):
    def generate(self, environment):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "analytics-config.js"
            with mock.patch.object(build_analytics_config, "OUTPUT", output), mock.patch.dict(os.environ, environment, clear=True):
                build_analytics_config.build()
            source = output.read_text(encoding="utf-8")
        return json.loads(source.removeprefix("window.OPENBAND_ANALYTICS_CONFIG = Object.freeze(").removesuffix(");\n"))

    def test_missing_configuration_is_explicitly_disabled(self):
        config = self.generate({})
        self.assertFalse(config["enabled"])
        self.assertEqual(config["gaMeasurementId"], "")
        self.assertEqual(config["apiEndpoint"], "")

    def test_environment_can_enable_production_configuration(self):
        config = self.generate({
            "OPENBAND_ANALYTICS_ENABLED": "true",
            "OPENBAND_GA4_ID": "G-TEST123",
            "OPENBAND_ANALYTICS_ENDPOINT": "https://analytics.openband.ca/v1/events",
        })
        self.assertTrue(config["enabled"])
        self.assertEqual(config["gaMeasurementId"], "G-TEST123")

    def test_disable_switch_wins_over_configured_ids(self):
        config = self.generate({
            "OPENBAND_ANALYTICS_ENABLED": "false",
            "OPENBAND_GA4_ID": "G-TEST123",
        })
        self.assertFalse(config["enabled"])


if __name__ == "__main__":
    unittest.main()
