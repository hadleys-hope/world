"""Shared pedestrian surfaces, building entrances and obstacle-checked A* graph."""
import heapq
import math

VERSION = 1
HOUSE_DIMENSIONS = ((20, 18), (16, 18), (17, 18), (20, 20))
WORKPLACES = {
    'workshop': dict(name='Maintenance workshop', angle=16., radius=244., width=21., depth=16.),
    'laboratory': dict(name='Research laboratory', angle=48., radius=244., width=21., depth=16.),
}


def polar(angle, radius, height=1.32):
    a = math.radians(angle)
    return (radius * math.cos(a), radius * math.sin(a), height)


def segment_hits_rectangle(a, b, rectangle, margin=.35):
    """Exact slab test in a rotated footprint's local tangent/radial axes."""
    x, y, angle, width, depth = rectangle
    angle = math.radians(angle)
    ca, sa = math.cos(angle), math.sin(angle)
    def local(p):
        dx, dy = p[0] - x, p[1] - y
        return -sa * dx + ca * dy, ca * dx + sa * dy
    p, q = local(a), local(b)
    low, high = 0., 1.
    for start, end, half in zip(p, q, (width / 2 + margin, depth / 2 + margin)):
        delta = end - start
        if abs(delta) < 1e-12:
            if abs(start) > half:
                return False
        else:
            u, v = (-half - start) / delta, (half - start) / delta
            low, high = max(low, min(u, v)), min(high, max(u, v))
            if low > high:
                return False
    return True


class PedestrianGraph:
    version = VERSION

    def __init__(self, w):
        self.nodes, self.edges, self.adjacency = {}, {}, {}
        self.obstacles, self.obstacle_index = [], {}
        self.closed = set()
        self.revision = 0
        self.path_cache = {}
        self.length_cache = {}
        for i in range(w.N):
            width, depth = HOUSE_DIMENSIONS[int(w.h_type[i])]
            self.add_obstacle((float(w.h_x[i]), float(w.h_y[i]), float(w.h_angle[i]), width + .5, depth + .5))
        for spec in WORKPLACES.values():
            x, y, _ = polar(spec['angle'], spec['radius'])
            self.add_obstacle((x, y, spec['angle'], spec['width'], spec['depth']))
        # Existing civic frontages and service buildings border the inner promenade.
        for s in range(w.S):
            x, y, _ = polar(s * 60 + 38, 251)
            self.add_obstacle((x, y, s * 60 + 38, 28, 10))
        for key, width, depth in [('garage', 56, 24), ('medlab', 36, 24), ('school', 40, 24)]:
            angle, radius = w.cfg[key]
            x, y, _ = polar(angle, radius)
            self.add_obstacle((x, y, angle, width + 2, depth + 2))
        self._build(w)

    def add_obstacle(self, rectangle):
        index = len(self.obstacles)
        self.obstacles.append(rectangle)
        x, y, _, width, depth = rectangle
        pad = math.hypot(width, depth) / 2 + 1
        for ix in range(math.floor((x - pad) / 64), math.floor((x + pad) / 64) + 1):
            for iy in range(math.floor((y - pad) / 64), math.floor((y + pad) / 64) + 1):
                self.obstacle_index.setdefault((ix, iy), set()).add(index)

    def segment_clear(self, a, b):
        candidates = set()
        for ix in range(math.floor(min(a[0], b[0]) / 64), math.floor(max(a[0], b[0]) / 64) + 1):
            for iy in range(math.floor(min(a[1], b[1]) / 64), math.floor(max(a[1], b[1]) / 64) + 1):
                candidates.update(self.obstacle_index.get((ix, iy), ()))
        return not any(segment_hits_rectangle(a, b, self.obstacles[i]) for i in candidates)

    def node(self, name, point):
        self.nodes[name] = point
        self.adjacency.setdefault(name, [])
        return name

    def edge(self, a, b, kind='sidewalk', name=None):
        if not self.segment_clear(self.nodes[a], self.nodes[b]):
            return None
        name = name or f'{a}|{b}'
        length = math.dist(self.nodes[a][:2], self.nodes[b][:2])
        self.edges[name] = dict(a=a, b=b, kind=kind, length=length)
        self.adjacency[a].append((b, name, length))
        self.adjacency[b].append((a, name, length))
        return name

    def _build(self, w):
        # Outer side of each row street, matching the rendered 10 m road + sidewalk.
        radii = [264.] + [w.cfg['house_radius_min'] - 30 + k * w.cfg['house_ring_step'] + 6.55 for k in range(w.cfg['house_rows'])]
        circles = {}
        def angle_key(angle):
            return round(angle % 360, 8)
        for layer, radius in enumerate(radii):
            angles = {float(a) for a in range(0, 360, 2)}
            angles.update(angle_key(float(a)) for a in w.h_angle)
            if layer == 0:
                angles.update(s['angle'] for s in WORKPLACES.values())
            offset = math.degrees(math.asin(6.55 / radius))
            for sector in range(w.S):
                angles.update((angle_key(sector * 60 - offset), angle_key(sector * 60 + offset)))
            ordered = sorted(angles)
            for index, angle in enumerate(ordered):
                circles[layer, angle_key(angle)] = self.node(f'walk:{layer}:{index}', polar(angle, radius))
            for index, angle in enumerate(ordered):
                end = ordered[(index + 1) % len(ordered)]
                span = (end - angle) % 360
                midpoint = (angle + span / 2) % 360
                crossing = next((s for s in range(w.S) if abs((midpoint - s * 60 + 180) % 360 - 180) < offset), None)
                self.edge(circles[layer, angle_key(angle)], circles[layer, angle_key(end)],
                          'crossing' if crossing is not None else 'sidewalk')
        for sector in range(w.S):
            angle = sector * 60
            previous = circles[0, angle_key(angle + math.degrees(math.asin(6.55 / radii[0])))]
            for layer, radius in enumerate(radii[1:], 1):
                inner = radius - 13.1
                p = polar(angle, math.sqrt(inner * inner - 6.55 ** 2))
                ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))
                point = (p[0] - sa * 6.55, p[1] + ca * 6.55, 1.32)
                start = self.node(f'spine:{sector}:{layer}', point)
                self.edge(previous, start)
                end = circles[layer, angle_key(angle + math.degrees(math.asin(6.55 / radius)))]
                self.edge(start, end, 'crossing', f'crossing:row:{layer - 1}:sector:{sector}')
                previous = end
        for home in range(w.N):
            angle = float(w.h_angle[home])
            depth = HOUSE_DIMENSIONS[int(w.h_type[home])][1]
            # First exterior stair, directly in front of the rendered door.
            entrance = self.node(f'home:{home}', polar(angle, float(w.h_radius[home]) - depth / 2 - .7, 1.55))
            layer = int(w.h_ring[home]) + 1
            self.edge(entrance, circles[layer, angle_key(angle)], 'entrance')
        for key, spec in WORKPLACES.items():
            entrance = self.node(f'work:{key}', polar(spec['angle'], spec['radius'] + spec['depth'] / 2 + .65, .65))
            self.edge(entrance, circles[0, angle_key(spec['angle'])], 'entrance', f'entrance:{key}')

    def set_closed(self, edge, closed):
        if edge not in self.edges:
            raise ValueError('Unknown pedestrian connection')
        if closed == (edge in self.closed):
            return
        self.closed.add(edge) if closed else self.closed.discard(edge)
        self.revision += 1
        self.path_cache.clear()
        self.length_cache.clear()

    def find_path(self, start, goal):
        key = (start, goal, self.revision)
        if key in self.path_cache:
            return self.path_cache[key]
        if start not in self.nodes or goal not in self.nodes:
            return None
        queue = [(0., 0., start)]
        costs, parents = {start: 0.}, {}
        while queue:
            _, cost, node = heapq.heappop(queue)
            if cost != costs.get(node):
                continue
            if node == goal:
                path = [goal]
                while path[-1] != start:
                    path.append(parents[path[-1]])
                path.reverse()
                self.path_cache[key] = path
                return path
            for other, edge, length in self.adjacency[node]:
                if edge in self.closed:
                    continue
                new_cost = cost + length
                if new_cost < costs.get(other, math.inf):
                    costs[other], parents[other] = new_cost, node
                    estimate = math.dist(self.nodes[other][:2], self.nodes[goal][:2])
                    heapq.heappush(queue, (new_cost + estimate, new_cost, other))
        self.path_cache[key] = None
        return None

    def path_edges(self, path):
        return [next(edge for node, edge, _ in self.adjacency[a] if node == b) for a, b in zip(path, path[1:])]

    def distance(self, start, goal):
        key = start, goal, self.revision
        if key not in self.length_cache:
            path = self.find_path(start, goal)
            self.length_cache[key] = sum(self.edges[e]['length'] for e in self.path_edges(path)) if path else None
        return self.length_cache[key]

    def geometry(self):
        return dict(version=VERSION, nodes=self.nodes, edges=self.edges, workplaces=WORKPLACES)
