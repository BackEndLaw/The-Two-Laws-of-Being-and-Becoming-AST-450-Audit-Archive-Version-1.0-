"""CARLA environment integration for the RescueOS vehicle contract."""

from integrations.vehicle.carla.adapter import CarlaVehicleAdapter
from integrations.vehicle.carla.blocked_route import run_denied_case

__all__ = ["CarlaVehicleAdapter", "run_denied_case"]