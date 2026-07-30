from __future__ import annotations

import json
import sys

from qrtc.carla_driving import load_driving_config, run_live_driving_test


def main() -> int:
    try:
        result = run_live_driving_test(load_driving_config())
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["assessment"]["passed"] else 1
    except (ImportError, RuntimeError, ValueError) as error:
        print(f"CARLA driving test failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
