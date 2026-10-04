"""Persistent resident profiles and a simulation-clock workday.

Routes use the same obstacle-checked sidewalk graph and entrances as the viewer.
"""
from dataclasses import dataclass, field
import math
from hadleys.geometry.pedestrians import PedestrianGraph, WORKPLACES

PROFESSIONS = ("engineer", "electrician", "scientist")
STATES = ("HOME", "WALK_TO_WORK", "AT_WORK", "WALK_HOME")
NAVIGATION_VERSION = 2


@dataclass
class Citizen:
    id: int
    home: int
    profession: str
    workplace: str
    shift_start: int
    shift_end: int
    route: list
    route_length: float
    state: str = "HOME"
    progress: float = 0.0
    x: float = 0.0
    y: float = 0.0
    wait_reason: str = ""
    last_transition: int = 0
    height: float = 1.25
    route_nodes: list = field(default_factory=list)
    route_edges: list = field(default_factory=list)
    navigation_revision: int = -1
    shelter_target: str = ""
    duty_day: int = -1


def route_segment(c):
    remaining = c.progress * c.route_length
    for i, (a, b) in enumerate(zip(c.route, c.route[1:])):
        length = math.dist(a[:2], b[:2])
        if remaining <= length and length > 0:
            return i, remaining / length
        remaining -= length
    return max(0, len(c.route) - 2), 1.


def route_position(c):
    if len(c.route) < 2:
        return c.route[0][:2] if c.route else (c.x, c.y)
    i, p = route_segment(c)
    a, b = c.route[i:i+2]
    return a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p


def update_position(c):
    c.x, c.y = route_position(c)
    if len(c.route) > 1:
        i, p = route_segment(c)
        c.height = c.route[i][2] + (c.route[i+1][2] - c.route[i][2]) * p


def assign_route(w, c, points, nodes, edges, returning=False):
    c.route = list(reversed(points)) if returning else points
    c.route_nodes = list(reversed(nodes)) if returning else nodes
    c.route_edges = list(reversed(edges)) if returning else edges
    c.route_length = sum(math.dist(a[:2], b[:2]) for a, b in zip(c.route, c.route[1:]))
    c.progress = 1. if returning else 0.
    c.navigation_revision = w.navigation.revision
    update_position(c)


def motion_plan(w, c, goal):
    graph = w.navigation
    position = (c.x, c.y, c.height)
    if c.state == 'HOME':
        candidates = [f'home:{c.home}']
    elif c.state == 'AT_WORK':
        candidates = [f'work:{c.workplace}']
    elif len(c.route_nodes) > 1:
        segment, _ = route_segment(c)
        edge = c.route_edges[segment]
        if edge in graph.closed:
            return None  # No walking across a connection closed under our feet.
        candidates = [node for node in c.route_nodes[segment:segment+2] if node is not None]
    else:
        # A one-time recovery connector for older saves, preserving the saved position.
        nearest = sorted(graph.nodes, key=lambda n: math.dist(position[:2], graph.nodes[n][:2]))
        candidates = [n for n in nearest[:8] if math.dist(position[:2], graph.nodes[n][:2]) < 80 and graph.segment_clear(position, graph.nodes[n])]
    options = []
    for start in candidates:
        distance = graph.distance(start, goal)
        if distance is not None and graph.segment_clear(position, graph.nodes[start]):
            options.append((distance + math.dist(position[:2], graph.nodes[start][:2]), start))
    if not options:
        return None
    _, start = min(options)
    path = graph.find_path(start, goal)
    points = [graph.nodes[n] for n in path]
    edges = graph.path_edges(path)
    if math.dist(position[:2], points[0][:2]) > 1e-7:
        # This connector is a portion of the current checked graph edge, or migration recovery.
        if not graph.segment_clear(position, points[0]):
            return None
        points.insert(0, position)
        path = [None] + path
        edges = [None] + edges
    return points, path, edges


def plan_motion(w, c, goal, returning=False):
    result = motion_plan(w, c, goal)
    if result is None:
        c.wait_reason = 'no_path'
        c.navigation_revision = w.navigation.revision
        return False
    assign_route(w, c, *result, returning=returning)
    return True


def initialize_citizens(w, migrate=False):
    """Stable profiles and routes; no global RNG draws."""
    if not hasattr(w, 'navigation'):
        w.navigation = PedestrianGraph(w)
    citizens = []
    for i in range(int(w.cfg.get('citizen_count', 300))):
        legacy = migrate and i < len(getattr(w, 'w_home', []))
        home = int(w.w_home[i]) if legacy else i % w.N
        profession = PROFESSIONS[i % 3]
        workplace = 'laboratory' if profession == 'scientist' else 'workshop'
        start = 8 * 60 + (i % 6) * 5
        entry = w.navigation.nodes[f'home:{home}']
        c = Citizen(i, home, profession, workplace, start, start + 480, [], 0., x=entry[0], y=entry[1], height=entry[2])
        path = w.navigation.find_path(f'home:{home}', f'work:{workplace}')
        if path:
            assign_route(w, c, [w.navigation.nodes[n] for n in path], path, w.navigation.path_edges(path))
        else:
            c.route = [entry]
            c.wait_reason = 'no_path'
        if legacy:
            c.state = STATES[int(w.w_state[i])]
            if c.state in ('WALK_TO_WORK', 'WALK_HOME'):
                c.x, c.y = float(w.w_x[i]), float(w.w_y[i])
                c.route_nodes = []
                goal = f'home:{home}' if c.state == 'WALK_HOME' else f'work:{workplace}'
                if not plan_motion(w, c, goal, c.state == 'WALK_HOME'):
                    c.route = [(c.x, c.y, c.height)]
                    c.route_length, c.progress = 0., 0.
            elif c.state == 'AT_WORK':
                c.progress = 1.
                update_position(c)
        citizens.append(c)
    w.citizens = citizens
    w.citizens_version = NAVIGATION_VERSION


def migrate_navigation(w):
    """Upgrade preliminary routes once; later saves retain exact routes and closures."""
    if not hasattr(w, 'navigation') or getattr(w.navigation, 'version', 0) != PedestrianGraph.version:
        w.navigation = PedestrianGraph(w)
    if getattr(w, 'citizens_version', 0) >= NAVIGATION_VERSION:
        return
    for c in w.citizens:
        c.workplace = 'laboratory' if c.profession == 'scientist' else 'workshop'
        c.height, c.route_nodes, c.route_edges = 1.25, [], []
        c.navigation_revision, c.shelter_target = -1, ''
        c.duty_day = w.t // w.cfg['ticks_per_day'] if c.state != 'HOME' else -1
        if c.state in ('HOME', 'AT_WORK'):
            node = f'home:{c.home}' if c.state == 'HOME' else f'work:{c.workplace}'
            c.x, c.y, c.height = w.navigation.nodes[node]
        goal = f'home:{c.home}' if c.state in ('WALK_HOME', 'AT_WORK') else f'work:{c.workplace}'
        if not plan_motion(w, c, goal, c.state in ('WALK_HOME', 'AT_WORK')):
            c.route, c.route_nodes, c.route_edges = [(c.x, c.y, c.height)], [], []
            c.route_length, c.progress = 0., 0.
    w.citizens_version = NAVIGATION_VERSION


def citizens_step(w):
    if w.paused or w.finished:
        return
    minute = w.t % w.cfg['ticks_per_day']
    speed = w.cfg.get('citizen_walk_mps', 1.3) * w.cfg['tick_seconds']
    graph = w.navigation
    for c in w.citizens:
        previous = c.state
        previous_reason = c.wait_reason
        c.wait_reason = ''
        storm = w.storm_ticks > 0
        locked = bool(w.lockdown_ticks[int(w.h_sector[c.home])])
        commute_length = graph.distance(f'home:{c.home}', f'work:{c.workplace}')
        if commute_length is None:
            commute_length = c.route_length
        commute = math.ceil(commute_length / max(speed, 1e-9))
        shift_due = max(0, c.shift_start - commute) <= minute < c.shift_end
        same_shift_day = c.duty_day < 0 or c.duty_day == w.t // w.cfg['ticks_per_day']
        if locked:
            c.wait_reason = 'sector_lockdown'
            continue
        if storm:
            if c.state in ('HOME', 'AT_WORK'):
                c.wait_reason = 'storm'
                continue
            if not c.shelter_target or c.navigation_revision != graph.revision:
                options = []
                for goal, returning in ((f'home:{c.home}', True), (f'work:{c.workplace}', False)):
                    result = motion_plan(w, c, goal)
                    if result:
                        length = sum(math.dist(a[:2], b[:2]) for a,b in zip(result[0],result[0][1:]))
                        options.append((length, goal, returning, result))
                if not options:
                    c.wait_reason = 'no_path'
                    continue
                _, c.shelter_target, returning, result = min(options, key=lambda option: option[0])
                assign_route(w, c, *result, returning=returning)
                c.state = 'WALK_HOME' if returning else 'WALK_TO_WORK'
            c.wait_reason = 'seeking_shelter'
        else:
            c.shelter_target = ''
            if c.state == 'HOME':
                if not shift_due:
                    c.wait_reason = 'outside_shift'
                    continue
                if not plan_motion(w, c, f'work:{c.workplace}'):
                    continue
                c.state = 'WALK_TO_WORK'
                c.duty_day = w.t // w.cfg['ticks_per_day']
            elif c.state == 'AT_WORK':
                if same_shift_day and minute < c.shift_end:
                    if minute < c.shift_start:
                        c.wait_reason = 'before_shift'
                    continue
                if not plan_motion(w, c, f'home:{c.home}', returning=True):
                    continue
                c.state = 'WALK_HOME'
            elif c.state == 'WALK_TO_WORK' and (not same_shift_day or minute >= c.shift_end):
                if not plan_motion(w, c, f'home:{c.home}', returning=True):
                    continue
                c.state = 'WALK_HOME'
            elif c.navigation_revision != graph.revision or previous_reason == 'no_path':
                returning = c.state == 'WALK_HOME'
                goal = f'home:{c.home}' if returning else f'work:{c.workplace}'
                if not plan_motion(w, c, goal, returning):
                    continue
        if c.state in ('WALK_TO_WORK', 'WALK_HOME'):
            direction = 1 if c.state == 'WALK_TO_WORK' else -1
            c.progress = min(1., max(0., c.progress + direction * speed / max(c.route_length, 1e-9)))
            update_position(c)
            if c.progress in (0., 1.):
                c.state = 'HOME' if c.progress == 0 else 'AT_WORK'
                c.wait_reason = 'storm' if storm else ''
        if previous != c.state:
            c.last_transition = w.t


def citizen_snapshot(w):
    result = []
    for c in w.citizens:
        profile = {key: value for key, value in vars(c).items() if key not in ('route', 'route_nodes', 'route_edges')}
        profile['workplace_name'] = WORKPLACES[c.workplace]['name']
        profile['destination'] = c.home if c.state in ('HOME', 'WALK_HOME') else c.workplace
        profile['indoors'] = c.state in ('HOME', 'AT_WORK')
        result.append(profile)
    return result
