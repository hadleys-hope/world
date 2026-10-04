import math
import heapq
import pickle
import unittest

from hadleys.world import World
from hadleys.persistence import Store
from hadleys.domains.citizens import citizens_step, route_position, update_position
from hadleys.geometry.pedestrians import segment_hits_rectangle
from hadleys.geometry.roads import colony_layout


class PedestrianTests(unittest.TestCase):
    def setUp(self):
        self.w = World()
        self.graph = self.w.navigation

    def test_rotated_obstacle_intersections(self):
        rectangle = (0, 0, 45, 10, 4)
        self.assertTrue(segment_hits_rectangle((-10, -10), (10, 10), rectangle))
        self.assertFalse(segment_hits_rectangle((20, -10), (20, 10), rectangle))
        self.assertTrue(segment_hits_rectangle((0, 0), (1, 1), rectangle))

    def test_both_banks_of_every_walkable_road_are_included(self):
        for road in colony_layout(self.w.cfg)['roads']:
            if road['walk']:
                banks = {e.get('bank') for e in self.graph.edges.values() if e.get('road') == road['id']}
                self.assertEqual(banks, {-1, 1}, road['id'])

    def test_every_crossing_comes_from_existing_junction_markings(self):
        junctions = colony_layout(self.w.cfg)['junctions']
        self.assertEqual(len(self.graph.crossings), sum(len(j['arms']) for j in junctions))
        for crossing in self.graph.crossings:
            j = junctions[crossing['junction']]
            angle = j['arms'][crossing['arm']]
            d = 19.2 if j['mode'] == 'roundabout' else 11.2
            e = self.graph.edges[crossing['edge']]
            a,b = self.graph.nodes[e['a']],self.graph.nodes[e['b']]
            self.assertAlmostEqual((a[0]+b[0])/2,j['x']+math.cos(angle)*d)
            self.assertAlmostEqual((a[1]+b[1])/2,j['y']+math.sin(angle)*d)
            self.assertEqual(a[2],1.05)

    def test_astar_matches_independent_shortest_distances(self):
        for closed in (False, True):
            self.graph.set_closed('crossing:row:0:sector:0',closed)
            for goal in ('work:workshop','work:laboratory'):
                costs = {goal: 0.}
                queue = [(0.,goal)]
                while queue:
                    cost,node = heapq.heappop(queue)
                    if cost != costs[node]:
                        continue
                    for other,edge,length in self.graph.adjacency[node]:
                        if edge in self.graph.closed:
                            continue
                        candidate = cost+length
                        if candidate < costs.get(other,math.inf):
                            costs[other]=candidate
                            heapq.heappush(queue,(candidate,other))
                for home in range(50):
                    self.assertAlmostEqual(self.graph.distance(f'home:{home}',goal),costs[f'home:{home}'],places=7)

    def test_graph_upgrade_keeps_active_position_and_saved_closure(self):
        c = self.w.citizens[0]
        c.state,c.progress = 'WALK_TO_WORK',.1
        update_position(c)
        position = c.x,c.y
        self.graph.set_closed('entrance:laboratory',True)
        del self.graph.version  # Old pickles stored only the class-level version.
        Store.migrate(self.w)
        self.assertEqual((c.x,c.y),position)
        self.assertIn('entrance:laboratory',self.w.navigation.closed)
        self.assertTrue(all(e is None or e in self.w.navigation.edges for e in c.route_edges))

    def test_every_home_reaches_both_real_entrances(self):
        for home in range(self.w.N):
            for workplace in ('workshop', 'laboratory'):
                with self.subTest(home=home, workplace=workplace):
                    path = self.graph.find_path(f'home:{home}', f'work:{workplace}')
                    self.assertIsNotNone(path)
                    self.assertEqual(path[0], f'home:{home}')
                    self.assertEqual(path[-1], f'work:{workplace}')
                    self.assertTrue(any(self.graph.edges[e]['kind'] == 'crossing' for e in self.graph.path_edges(path)))

    def test_graph_never_enters_building_footprints(self):
        # Check sampled edge points independently of the graph's segment slab test.
        for edge in self.graph.edges.values():
            a, b = self.graph.nodes[edge['a']], self.graph.nodes[edge['b']]
            for fraction in (0., .25, .5, .75, 1.):
                px, py = a[0] + (b[0]-a[0])*fraction, a[1] + (b[1]-a[1])*fraction
                for x, y, angle, width, depth in self.graph.obstacles:
                    angle = math.radians(angle)
                    u = -math.sin(angle)*(px-x) + math.cos(angle)*(py-y)
                    v = math.cos(angle)*(px-x) + math.sin(angle)*(py-y)
                    self.assertFalse(abs(u) < width/2 and abs(v) < depth/2)

    def test_closed_crossing_uses_a_longer_available_path(self):
        a, b = 'home:0', 'work:workshop'
        crossing = 'crossing:row:0:sector:0'
        original = self.graph.find_path(a, b)
        self.assertIn(crossing, self.graph.path_edges(original))
        distance = self.graph.distance(a, b)
        self.graph.set_closed(crossing, True)
        rerouted = self.graph.find_path(a, b)
        self.assertIsNotNone(rerouted)
        self.assertNotIn(crossing, self.graph.path_edges(rerouted))
        self.assertGreater(self.graph.distance(a, b), distance)
        self.graph.set_closed(crossing, False)
        self.assertEqual(self.graph.find_path(a, b), original)

    def test_closed_entrance_waits_at_home_then_resumes(self):
        c = self.w.citizens[0]
        self.graph.set_closed('entrance:workshop', True)
        position = c.x, c.y
        self.w.t = 480
        citizens_step(self.w)
        self.assertEqual(c.state, 'HOME')
        self.assertEqual(c.wait_reason, 'no_path')
        self.assertEqual((c.x, c.y), position)
        self.graph.set_closed('entrance:workshop', False)
        self.w.t += 1
        citizens_step(self.w)
        self.assertEqual(c.state, 'WALK_TO_WORK')
        self.assertGreater(c.progress, 0)

    def test_dynamic_detour_preserves_current_point(self):
        c = self.w.citizens[0]
        self.w.t = 470
        c.state, c.progress = 'WALK_TO_WORK', .02
        update_position(c)
        position = c.x, c.y
        self.graph.set_closed('crossing:row:0:sector:0', True)
        citizens_step(self.w)
        self.assertNotIn('crossing:row:0:sector:0', c.route_edges)
        self.assertEqual(c.route[0][:2], position)
        self.assertLessEqual(math.dist(position, (c.x, c.y)), 78.000001)

    def test_blocked_current_edge_waits_without_teleporting(self):
        c = self.w.citizens[0]
        c.state, c.progress = 'WALK_TO_WORK', .001
        update_position(c)
        position = c.x, c.y
        self.graph.set_closed(c.route_edges[0], True)
        self.w.t = 470
        citizens_step(self.w)
        self.assertEqual(c.wait_reason, 'no_path')
        self.assertEqual((c.x, c.y), position)
        self.graph.set_closed(c.route_edges[0], False)
        citizens_step(self.w)
        self.assertNotEqual((c.x, c.y), position)

    def test_shorter_route_does_not_reverse_an_existing_commute(self):
        c = self.w.citizens[0]
        self.graph.set_closed('crossing:row:0:sector:0', True)
        departure = c.shift_start - math.ceil(self.graph.distance('home:0', 'work:workshop') / 78)
        self.w.t = departure
        citizens_step(self.w)
        self.assertEqual(c.state, 'WALK_TO_WORK')
        self.graph.set_closed('crossing:row:0:sector:0', False)
        self.w.t += 1
        citizens_step(self.w)
        self.assertIn(c.state, ('WALK_TO_WORK', 'AT_WORK'))

    def test_save_load_preserves_closures_routes_and_waiting(self):
        self.graph.set_closed('entrance:workshop', True)
        self.w.t = 480
        citizens_step(self.w)
        resumed = pickle.loads(pickle.dumps(self.w))
        Store.migrate(resumed)
        self.assertEqual(resumed.navigation.closed, self.graph.closed)
        self.assertEqual(vars(resumed.citizens[0]), vars(self.w.citizens[0]))
        self.assertEqual(resumed.citizens[0].wait_reason, 'no_path')
        resumed.navigation.set_closed('entrance:workshop', False)
        citizens_step(resumed)
        self.assertEqual(resumed.citizens[0].state, 'WALK_TO_WORK')

    def test_previous_profile_version_preserves_outdoor_position(self):
        c = self.w.citizens[0]
        c.state, c.progress = 'WALK_TO_WORK', .1
        update_position(c)
        position = c.x, c.y
        self.w.citizens_version = 1
        c.workplace = 'garage'
        c.route = [p[:2] for p in c.route]
        del self.w.navigation
        Store.migrate(self.w)
        self.assertEqual(c.workplace, 'workshop')
        self.assertEqual((c.x, c.y), position)
        self.assertEqual(route_position(c), position)
        self.assertEqual(self.w.citizens_version, 2)


if __name__ == '__main__':
    unittest.main()
