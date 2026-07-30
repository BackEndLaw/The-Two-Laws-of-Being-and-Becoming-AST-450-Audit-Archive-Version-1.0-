from __future__ import annotations

import sys

from qrtc.carla_live import load_live_config, smoke_result_json


def main() -> int:
    try:
        print(smoke_result_json(load_live_config()))
        return 0
    except (ImportError, RuntimeError, ValueError) as error:
        print(f"CARLA smoke run failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
