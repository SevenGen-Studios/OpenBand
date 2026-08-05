"""Write the public, non-secret analytics runtime configuration."""

import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets" / "analytics-config.js"


def build():
    measurement_id = os.getenv("OPENBAND_GA4_ID", "").strip()
    endpoint = os.getenv("OPENBAND_ANALYTICS_ENDPOINT", "").strip()
    requested = os.getenv("OPENBAND_ANALYTICS_ENABLED", "false").lower() == "true"

    config = {
        "enabled": requested and bool(measurement_id or endpoint),
        "gaMeasurementId": measurement_id,
        "apiEndpoint": endpoint,
        "productionHosts": ["openband.ca", "www.openband.ca"],
        "debug": False,
    }
    OUTPUT.write_text(
        "window.OPENBAND_ANALYTICS_CONFIG = Object.freeze("
        + json.dumps(config, separators=(",", ":"))
        + ");\n",
        encoding="utf-8",
    )
    state = "enabled" if config["enabled"] else "disabled"
    try:
        display_path = OUTPUT.relative_to(ROOT)
    except ValueError:
        display_path = OUTPUT
    print(f"Wrote {display_path} ({state})")
    return True


if __name__ == "__main__":
    build()
