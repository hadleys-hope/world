"""Compatibility entry point. Implementation lives in hadleys/."""

from hadleys.config import CFG, COSTS, TYPE_NAMES  # noqa: F401
from hadleys.numerics import clamp, polar  # noqa: F401
from hadleys.geometry.terrain import (
    RIVER_PROFILE,
    coast_height,
    site_elevation,
)  # noqa: F401
from hadleys.domains.hydraulics import UtilityNetwork, hydraulic_step  # noqa: F401
from hadleys.models import Issue, Rover  # noqa: F401
from hadleys.world import World  # noqa: F401
from hadleys.domains.environment import env_step  # noqa: F401
from hadleys.domains.energy import (
    reactor_step,
    reactor_scram,
    grid_rebuild,
    power_step,
)  # noqa: F401
from hadleys.domains.houses import (
    houses_decide,
    houses_demand,
    houses_step,
    house_events,
)  # noqa: F401
from hadleys.domains.water import water_step  # noqa: F401
from hadleys.domains.internet import internet_step  # noqa: F401
from hadleys.domains.people import walker_path_point, people_step  # noqa: F401
from hadleys.domains.security import (
    move_toward,
    street_path,
    xeno_step,
    squad_step,
    spawn_xeno,
)  # noqa: F401
from hadleys.geometry.roads import (
    _LAYOUT_CACHE,
    angle_diff,
    arc_waypoints,
    ring_blocked,
    ring_route,
    rover_polar,
    colony_layout,
    traffic_junctions,
    signal_phase,
    exterior_route,
    roundabout_route,
    plan_route,
)  # noqa: F401
from hadleys.domains.transport import (
    make_traffic,
    traffic_step,
    rover_move,
    roads_step,
    _go_home,
    _garbage_rover,
    _sludge_rover,
)  # noqa: F401
from hadleys.domains.incidents import (
    HOUSE_TARGETS,
    REPAIR_PRIORITY,
    OUTSIDE_TARGETS,
    issue_target_spec,
    _crew_fits,
    _pipes_blocked,
    _repair_rover,
    damage_target,
    resolve_issue,
    incidents_step,
    pipes_audit,
)  # noqa: F401
from hadleys.domains.finance import (
    finance_reserve,
    finance_record,
    finance_pay,
    finance_day_close,
    finance_month_close,
    _expense_by_cause,
)  # noqa: F401
from hadleys.domains.attractors import (
    attractor_sample,
    FAST_KEYS,
    _houses_attractors,
    attractor_snapshot,
)  # noqa: F401
from hadleys.simulation import world_tick, inject, new_colony, sim_loop  # noqa: F401
from hadleys.api.snapshots import (
    snapshot,
    bus_snapshot,
    house_snapshot,
    house_geometry,
)  # noqa: F401
from hadleys.integrations.mqtt import MqttBridge  # noqa: F401
from hadleys.persistence import Store  # noqa: F401
from hadleys.api.server import make_handler  # noqa: F401
from hadleys.cli import main  # noqa: F401
from hadleys.web import (
    HTML,
    HTML3D,
    HTMLBUS,
    NAV_CSS,
    NAV_HTML,
    HTMLHOUSE,
    HTMLGRAPH,
    HTMLATTR,
)  # noqa: F401

if __name__ == "__main__":
    main()
