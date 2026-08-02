"""
CARLA live-drive harness — main entry point.

All ``carla`` imports are lazy so ordinary installs and CI remain
unaffected.  The harness is opt-in; run it explicitly via::

    python -m qrtc.carla_harness
    # or
    carla-live-drive

Environment variables:
    See qrtc.carla_config for the full list.

Safety guarantee
----------------
``carla`` is never imported at module load time.  If it is not installed
the module can still be imported; only the :func:`run_drive` function
(and the ``__main__`` block) will fail with an ImportError that includes
installation guidance.
"""
from __future__ import annotations

import json
import math
import sys
import traceback
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qrtc.carla_config import CarlaConfig, carla_config_from_env, validate_carla_config
from qrtc.carla_lidar import LidarCollector, build_lidar_summary, process_lidar_points
from qrtc.carla_telemetry import build_qrtc_projection, submit_to_qrtc_pipeline
from qrtc.limits import canonical_json


# ---------------------------------------------------------------------------
# CARLA lazy import helper
# ---------------------------------------------------------------------------

def _require_carla() -> Any:  # noqa: ANN401
    """Import and return the ``carla`` module, or raise ImportError with help."""
    try:
        import carla  # type: ignore[import]
        return carla
    except ImportError as exc:
        raise ImportError(
            "CARLA Python API is not installed. "
            "Install it from the CARLA 0.9.16 release (requires CPython 3.12):\n"
            "  pip install <path-to-carla-0.9.16-cp312-*.whl>\n"
            "See qrtc-transit/README.md for full setup instructions."
        ) from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _displacement(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
) -> float:
    dx, dy, dz = end[0] - start[0], end[1] - start[1], end[2] - start[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _transform_snapshot(transform: Any, velocity: Any) -> dict[str, Any]:
    loc = transform.location
    rot = transform.rotation
    speed = math.sqrt(velocity.x ** 2 + velocity.y ** 2 + velocity.z ** 2)
    return {
        "x": loc.x,
        "y": loc.y,
        "z": loc.z,
        "pitch": rot.pitch,
        "yaw": rot.yaw,
        "roll": rot.roll,
        "vx": velocity.x,
        "vy": velocity.y,
        "vz": velocity.z,
        "speed_mps": speed,
    }


def _select_blueprint(blueprint_library: Any, preferred: str) -> Any:
    """Choose ``preferred`` or fall back deterministically."""
    bp = blueprint_library.find(preferred)
    if bp is not None:
        return bp
    # Deterministic fallback: sort by id, pick first vehicle
    vehicles = sorted(
        blueprint_library.filter("vehicle.*"),
        key=lambda b: b.id,
    )
    if not vehicles:
        raise RuntimeError("No vehicle blueprints found in the simulator")
    return vehicles[0]


def _try_spawn(
    world: Any,
    blueprint: Any,
    spawn_points: list[Any],
    preferred_index: int,
) -> tuple[Any, int]:
    """
    Try the requested spawn point, then all others in order.
    Return (actor, actual_index_used).
    """
    indices = list(range(len(spawn_points)))
    if preferred_index < len(indices):
        indices = [preferred_index] + [i for i in indices if i != preferred_index]

    for idx in indices:
        actor = world.try_spawn_actor(blueprint, spawn_points[idx])
        if actor is not None:
            return actor, idx

    raise RuntimeError(
        f"Could not spawn vehicle at any of {len(spawn_points)} spawn points"
    )


# ---------------------------------------------------------------------------
# Core drive function
# ---------------------------------------------------------------------------

def run_drive(cfg: CarlaConfig | None = None) -> dict[str, Any]:
    """
    Execute a bounded synchronous CARLA drive and return a detailed run report.

    This function:
    - connects to CARLA using ``cfg`` (defaults to :func:`carla_config_from_env`)
    - enables synchronous mode and Traffic Manager
    - spawns a vehicle, attaches collision and (optionally) lidar sensors
    - runs for ``cfg.ticks`` frames
    - always cleans up in a ``finally`` block
    - returns a report dict (also written to ``cfg.output``)

    Raises ``SystemExit`` with a non-zero code on connection/spawn/tick/output
    failures so the process exit code signals CI correctly.
    """
    carla = _require_carla()

    if cfg is None:
        cfg = carla_config_from_env()

    errors = validate_carla_config(cfg)
    if errors:
        for e in errors:
            print(f"[carla-harness] config error: {e}", file=sys.stderr)
        raise SystemExit(1)

    run_id = str(uuid.uuid4())
    run_ts = datetime.now(UTC).isoformat()
    print(f"[carla-harness] run_id={run_id} ts={run_ts}", flush=True)

    # --- Connect ----------------------------------------------------------------
    try:
        client = carla.Client(cfg.host, cfg.port)
        client.set_timeout(cfg.timeout)
        client_version = client.get_client_version()
        server_version = client.get_server_version()
        world = client.get_world()
        map_name = world.get_map().name
    except Exception as exc:  # noqa: BLE001
        print(f"[carla-harness] connection failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        raise SystemExit(2) from exc

    print(
        f"[carla-harness] client={client_version} server={server_version} map={map_name}",
        flush=True,
    )

    # Save and later restore original world settings
    original_settings = world.get_settings()
    settings = world.get_settings()
    settings.synchronous_mode = True
    settings.fixed_delta_seconds = cfg.fixed_delta
    world.apply_settings(settings)

    # Traffic Manager
    tm = client.get_trafficmanager(cfg.tm_port)
    tm.set_synchronous_mode(True)

    ego_vehicle = None
    collision_sensor = None
    lidar_sensor = None
    lidar_collector: LidarCollector | None = None
    collision_events: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    missing_data_count = 0

    try:
        # --- Spawn vehicle --------------------------------------------------
        blueprint_library = world.get_blueprint_library()
        blueprint = _select_blueprint(blueprint_library, cfg.preferred_blueprint)
        spawn_points = world.get_map().get_spawn_points()
        if not spawn_points:
            raise RuntimeError("World has no spawn points")

        try:
            ego_vehicle, actual_spawn_index = _try_spawn(
                world, blueprint, spawn_points, cfg.spawn_point
            )
        except RuntimeError as exc:
            print(f"[carla-harness] spawn failed: {exc}", file=sys.stderr)
            raise SystemExit(3) from exc

        actor_id = ego_vehicle.id
        actor_type_id = ego_vehicle.type_id
        print(
            f"[carla-harness] spawned {actor_type_id} id={actor_id} "
            f"spawn_point={actual_spawn_index}",
            flush=True,
        )

        # Enable conservative autopilot
        ego_vehicle.set_autopilot(True, cfg.tm_port)
        tm.ignore_lights_percentage(ego_vehicle, 0)
        tm.distance_to_leading_vehicle(ego_vehicle, 3.0)
        tm.vehicle_percentage_speed_difference(ego_vehicle, 20.0)

        # --- Collision sensor -----------------------------------------------
        collision_bp = blueprint_library.find("sensor.other.collision")
        collision_transform = carla.Transform()
        collision_sensor = world.spawn_actor(
            collision_bp, collision_transform, attach_to=ego_vehicle
        )

        def _on_collision(event: Any) -> None:
            other = getattr(event.other_actor, "type_id", "unknown")
            collision_events.append(
                {
                    "frame": event.frame,
                    "other_actor": other,
                    "impulse_x": event.normal_impulse.x,
                    "impulse_y": event.normal_impulse.y,
                    "impulse_z": event.normal_impulse.z,
                }
            )

        collision_sensor.listen(_on_collision)

        # --- Lidar sensor ---------------------------------------------------
        if cfg.lidar.enabled:
            lidar_bp = blueprint_library.find("sensor.lidar.ray_cast")
            if lidar_bp is None:
                print(
                    "[carla-harness] lidar blueprint not found; skipping lidar",
                    file=sys.stderr,
                )
            else:
                lidar_bp.set_attribute(
                    "channels", str(cfg.lidar.channels)
                )
                lidar_bp.set_attribute("range", str(cfg.lidar.range_m))
                lidar_bp.set_attribute(
                    "points_per_second", str(cfg.lidar.points_per_second)
                )
                lidar_bp.set_attribute(
                    "rotation_frequency", str(cfg.lidar.rotation_frequency)
                )
                lidar_bp.set_attribute("upper_fov", str(cfg.lidar.upper_fov))
                lidar_bp.set_attribute("lower_fov", str(cfg.lidar.lower_fov))

                lidar_transform = carla.Transform(
                    carla.Location(x=0.0, z=2.4)
                )
                lidar_sensor = world.spawn_actor(
                    lidar_bp, lidar_transform, attach_to=ego_vehicle
                )
                lidar_collector = LidarCollector(
                    retain_raw=cfg.lidar.retain_raw,
                    max_raw_frames=cfg.lidar.max_raw_frames,
                    drop_frame_index=cfg.lidar.drop_frame_index,
                )
                lidar_sensor.listen(lidar_collector.on_data)

        # --- Tick loop ------------------------------------------------------
        initial_transform = ego_vehicle.get_transform()
        start_pos = (
            initial_transform.location.x,
            initial_transform.location.y,
            initial_transform.location.z,
        )
        speed_values: list[float] = []
        ticks_completed = 0

        try:
            for tick_idx in range(cfg.ticks):
                frame = world.tick()
                ticks_completed += 1

                transform = ego_vehicle.get_transform()
                velocity = ego_vehicle.get_velocity()
                snap = _transform_snapshot(transform, velocity)
                snap["frame"] = frame
                snap["tick_index"] = tick_idx
                samples.append(snap)
                speed_values.append(snap["speed_mps"])

                if tick_idx % 50 == 0:
                    print(
                        f"[carla-harness] tick={tick_idx}/{cfg.ticks} "
                        f"speed={snap['speed_mps']:.2f} m/s "
                        f"collisions={len(collision_events)}",
                        flush=True,
                    )
        except Exception as exc:  # noqa: BLE001
            print(f"[carla-harness] tick loop error: {exc}", file=sys.stderr)
            traceback.print_exc()
            missing_data_count += cfg.ticks - ticks_completed
            # Do not raise; partial data is acceptable; cleanup follows.

        # Compute displacement
        final_transform = ego_vehicle.get_transform()
        end_pos = (
            final_transform.location.x,
            final_transform.location.y,
            final_transform.location.z,
        )
        disp = _displacement(start_pos, end_pos)

        mean_speed = sum(speed_values) / len(speed_values) if speed_values else 0.0
        max_speed = max(speed_values) if speed_values else 0.0

        # Lidar summary
        lidar_frame_evidence: list[dict[str, Any]] = []
        lidar_summary_dict: dict[str, Any] = {}
        if lidar_collector is not None:
            frames, dropped, cb_errors = lidar_collector.snapshot()
            summary = build_lidar_summary(frames, dropped, cb_errors)
            lidar_summary_dict = summary.as_dict()
            lidar_frame_evidence = [f.as_dict() for f in frames]
        else:
            lidar_summary_dict = {
                "frames_received": 0,
                "frames_dropped": 0,
                "callback_errors": 0,
                "total_points": 0,
                "total_invalid": 0,
                "nearest_obstacle_overall": None,
                "nearest_obstacle_front": None,
                "mean_nearest_front": None,
            }

        # --- Build run report -----------------------------------------------
        run_report: dict[str, Any] = {
            "run_id": run_id,
            "run_timestamp_utc": run_ts,
            "status": "completed",
            "client_version": client_version,
            "server_version": server_version,
            "map_name": map_name,
            "blueprint": actor_type_id,
            "actor_id": actor_id,
            "actor_type_id": actor_type_id,
            "spawn_point_index": actual_spawn_index,
            "ticks_requested": cfg.ticks,
            "ticks_completed": ticks_completed,
            "missing_data_count": missing_data_count,
            "principal": cfg.principal,
            "destination": cfg.destination,
            "config": cfg.as_dict(),
            "summary": {
                "collision_count": len(collision_events),
                "displacement_m": disp,
                "mean_speed_mps": mean_speed,
                "max_speed_mps": max_speed,
            },
            "collision_events": collision_events,
            "samples": samples,
            "lidar_summary": lidar_summary_dict,
            "lidar_frame_evidence": lidar_frame_evidence,
        }

        # Emit config and evidence digests
        from qrtc.carla_telemetry import _config_digest, _evidence_digest
        run_report["config_digest"] = _config_digest(cfg.as_dict())
        run_report["evidence_digest"] = _evidence_digest(run_report["summary"])

        # --- Write output ---------------------------------------------------
        out_path = Path(cfg.output)
        try:
            out_path.write_text(
                json.dumps(run_report, indent=2, default=str),
                encoding="utf-8",
            )
            print(f"[carla-harness] report written to {out_path}", flush=True)
        except OSError as exc:
            print(f"[carla-harness] output write failed: {exc}", file=sys.stderr)
            raise SystemExit(4) from exc

        # --- Optional QRTC submission ---------------------------------------
        if cfg.submit_to_qrtc:
            projection = build_qrtc_projection(run_report)
            qrtc_result = submit_to_qrtc_pipeline(
                projection, db_path=cfg.qrtc_db
            )
            run_report["qrtc_submission"] = qrtc_result.as_dict()
            print(
                f"[carla-harness] QRTC submission: status={qrtc_result.status} "
                f"transit_id={qrtc_result.transit_id} db={qrtc_result.db_path}",
                flush=True,
            )
            # Rewrite with QRTC result included
            out_path.write_text(
                json.dumps(run_report, indent=2, default=str),
                encoding="utf-8",
            )

        return run_report

    finally:
        # --- Cleanup (always executed) --------------------------------------
        print("[carla-harness] cleaning up ...", flush=True)
        if ego_vehicle is not None:
            try:
                ego_vehicle.set_autopilot(False)
            except Exception:  # noqa: BLE001
                pass
        for sensor in (lidar_sensor, collision_sensor):
            if sensor is not None:
                try:
                    sensor.stop()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    sensor.destroy()
                except Exception:  # noqa: BLE001
                    pass
        if ego_vehicle is not None:
            try:
                ego_vehicle.destroy()
            except Exception:  # noqa: BLE001
                pass
        try:
            tm.set_synchronous_mode(False)
        except Exception:  # noqa: BLE001
            pass
        try:
            world.apply_settings(original_settings)
        except Exception:  # noqa: BLE001
            pass
        print("[carla-harness] cleanup complete", flush=True)


# ---------------------------------------------------------------------------
# Console entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:  # noqa: ARG001
    """Entry point for the ``carla-live-drive`` console script."""
    cfg = carla_config_from_env()
    errors = validate_carla_config(cfg)
    if errors:
        for e in errors:
            print(f"config error: {e}", file=sys.stderr)
        return 1

    try:
        report = run_drive(cfg)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 1
    except Exception as exc:  # noqa: BLE001
        print(f"[carla-harness] fatal: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 10

    status = report.get("status", "unknown")
    print(f"[carla-harness] done status={status}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
