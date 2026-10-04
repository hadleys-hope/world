"""Shared pedestrian surfaces, building entrances and obstacle-checked A* graph."""
import heapq
import math
from hadleys.geometry.roads import colony_layout

VERSION = 2
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
        self.version = VERSION  # Store the schema version in the pickle itself.
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
        """Both sidewalk banks and every painted zebra from the shared road plan."""
        layout = colony_layout(w.cfg)
        segments, road_index = [], {}
        for road in layout['roads']:
            for a, b in zip(road['points'], road['points'][1:]):
                index = len(segments)
                segments.append((a, b, road['width'] / 2))
                pad = road['width'] / 2 + 5
                for ix in range(math.floor((min(a[0], b[0]) - pad) / 32), math.floor((max(a[0], b[0]) + pad) / 32) + 1):
                    for iy in range(math.floor((min(a[1], b[1]) - pad) / 32), math.floor((max(a[1], b[1]) + pad) / 32) + 1):
                        road_index.setdefault((ix, iy), set()).add(index)

        def project(point, a, b):
            dx, dy = b[0] - a[0], b[1] - a[1]
            t = max(0., min(1., ((point[0]-a[0])*dx + (point[1]-a[1])*dy) / (dx*dx + dy*dy or 1)))
            return (a[0] + t*dx, a[1] + t*dy)

        def on_road(point, margin=0):
            for q in layout['roundabouts']:
                distance = math.dist(point[:2], (q['x'], q['y']))
                if distance < q['outer'] + margin:
                    return distance > 8.6 - margin
            indices = road_index.get((math.floor(point[0]/32), math.floor(point[1]/32)), ())
            return any(math.dist(point[:2], project(point, segments[i][0], segments[i][1])) < segments[i][2] + margin for i in indices)

        def walk_clear(a, b, margin=.1):
            count = max(1, math.ceil(math.dist(a[:2], b[:2]) / 1.5))
            return self.segment_clear(a, b) and all(not on_road((a[0]+(b[0]-a[0])*i/count, a[1]+(b[1]-a[1])*i/count), margin) for i in range(count+1))

        locations, walk_index = {}, {}
        def walk_node(point):
            key = round(point[0], 5), round(point[1], 5)
            if key not in locations:
                name = self.node(f'walk:{len(locations)}', (point[0], point[1], 1.25))
                locations[key] = name
                walk_index.setdefault((math.floor(point[0]/8), math.floor(point[1]/8)), []).append(name)
            return locations[key]

        def nearby(point, radius=6):
            nodes = []
            for ix in range(math.floor((point[0]-radius)/8), math.floor((point[0]+radius)/8)+1):
                for iy in range(math.floor((point[1]-radius)/8), math.floor((point[1]+radius)/8)+1):
                    nodes.extend(walk_index.get((ix, iy), ()))
            return sorted((n for n in nodes if math.dist(point[:2], self.nodes[n][:2]) <= radius), key=lambda n: math.dist(point[:2], self.nodes[n][:2]))

        # Match buildRoadWalks: subdivide at 3 m, offset using the local tangent.
        for road in layout['roads']:
            if not road['walk']:
                continue
            points = [road['points'][0]]
            for a, b in zip(road['points'], road['points'][1:]):
                count = max(1, math.ceil(math.dist(a, b)/3))
                points.extend((a[0]+(b[0]-a[0])*i/count, a[1]+(b[1]-a[1])*i/count) for i in range(1, count+1))
            for side in (-1, 1):
                path = []
                for i, p in enumerate(points):
                    a, b = points[max(0,i-1)], points[min(len(points)-1,i+1)]
                    dx, dy = b[0]-a[0], b[1]-a[1]
                    length = math.hypot(dx,dy) or 1
                    offset = side*(road['width']/2+1.55)
                    path.append((p[0]-dy/length*offset, p[1]+dx/length*offset))
                for a, b in zip(path,path[1:]):
                    midpoint = ((a[0]+b[0])/2, (a[1]+b[1])/2)
                    if on_road(midpoint, 2.7*.52+.1) or any(math.dist(midpoint,(q['x'],q['y'])) < q['outer']+2.7 for q in layout['roundabouts']):
                        continue
                    edge = self.edge(walk_node(a), walk_node(b))
                    if edge:
                        self.edges[edge].update(road=road['id'], bank=side)

        # The six neighbourhood promenades are drawn by buildStreetLife.
        for sector in range(w.S):
            a0, a1 = sector*60+3, sector*60+38
            count = math.ceil(math.radians(a1-a0)*226/3)
            points = [polar(a0+(a1-a0)*i/count,226,1.25) for i in range(count+1)]
            for a,b in zip(points,points[1:]):
                if walk_clear(a,b,2.8*.52+.1):
                    self.edge(walk_node(a),walk_node(b))

        self.crossings = []
        for junction in layout['junctions']:
            ends = []
            for arm, angle in enumerate(junction['arms']):
                dx,dy = math.cos(angle),math.sin(angle)
                nx,ny = -dy,dx
                d = 19.2 if junction['mode']=='roundabout' else 11.2
                half = junction['width']/2
                centre = (junction['x']+dx*d,junction['y']+dy*d)
                endpoints = []
                for side in (-1,1):
                    offset = half + 1.55
                    p = (centre[0]+nx*side*offset,centre[1]+ny*side*offset,1.25)
                    # Acute T-junctions can overlap the nominal sidewalk endpoint.
                    while on_road(p, .1) and offset < half + 16:
                        offset += .5
                        p = (centre[0]+nx*side*offset,centre[1]+ny*side*offset,1.25)
                    node = self.node(f'zebra:{junction["row"]}:{arm}:{side}',p)
                    endpoints.append(node)
                    for other in nearby(p,12):
                        if walk_clear(p,self.nodes[other]):
                            self.edge(node,other)
                            break
                # The main segment lies on existing asphalt, with short curb ramps.
                ramps = []
                for side, end in zip((-1,1),endpoints):
                    p = (centre[0]+nx*side*(half-.2),centre[1]+ny*side*(half-.2),1.05)
                    node = self.node(f'{end}:ramp',p)
                    self.edge(end,node,'ramp')
                    ramps.append(node)
                name = f'crossing:junction:{junction["row"]}:arm:{arm}'
                # Keep the demonstration closure stable across existing saves.
                if junction['sector']==0 and abs(math.hypot(junction['x'],junction['y'])-270)<1 and abs(angle-math.pi/2)<.12:
                    name = 'crossing:row:0:sector:0'
                edge = self.edge(*ramps,'crossing',name)
                if edge:
                    self.crossings.append(dict(edge=edge, junction=junction['row'], arm=arm, endpoints=endpoints))
                ends.extend(endpoints)
            # Join sidewalk corners around the intersection, never through its roadway.
            for i,a in enumerate(ends):
                for b in ends[i+1:]:
                    if walk_clear(self.nodes[a],self.nodes[b]):
                        self.edge(a,b)

        # Weld consecutive road parcels and sidewalk mouths on the same bank.
        for name, point in list(self.nodes.items()):
            if not name.startswith('walk:'):
                continue
            for other in nearby(point,3.2):
                if other > name and walk_clear(point,self.nodes[other]) and not any(n==other for n,_,_ in self.adjacency[name]):
                    self.edge(name,other)

        # Entrance connectors are the only additional pavement drawn by the NPC layer.
        for home in range(w.N):
            depth = HOUSE_DIMENSIONS[int(w.h_type[home])][1]
            point = polar(float(w.h_angle[home]),float(w.h_radius[home])-depth/2-.7,1.55)
            node = self.node(f'home:{home}',point)
            for other in nearby(point,25):
                if walk_clear(point,self.nodes[other]):
                    edge = self.edge(node,other,'entrance')
                    if edge:
                        break
        for key,spec in WORKPLACES.items():
            point = polar(spec['angle'],spec['radius']+spec['depth']/2+.65,.65)
            node = self.node(f'work:{key}',point)
            for target in nearby(point,15):
                if walk_clear(point,self.nodes[target]):
                    self.edge(node,target,'entrance',f'entrance:{key}')
                    break

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
        return dict(version=VERSION, nodes=self.nodes, edges=self.edges, workplaces=WORKPLACES, crossings=self.crossings)
