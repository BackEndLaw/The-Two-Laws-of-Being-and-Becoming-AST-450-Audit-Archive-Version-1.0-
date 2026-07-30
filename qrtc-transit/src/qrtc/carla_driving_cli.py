from __future__ import annotations

import sys

from qrtc.carla_driving import driving_result_json, load_driving_config


def main() -> int:
    try:
        result = driving_result_json(load_driving_config())
        print(result)
        return 0
    except (ImportError, RuntimeError, ValueError) as error:
        print(f"CARLA driving test failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
