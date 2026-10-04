# Pedestrian routing

The graph uses `colony_layout`, the same road plan used to draw streets and junction markings. Both sidewalk banks of every road with `walk=true`, the six neighbourhood promenades, all 300 painted zebra crossings, sidewalk corners, and home/workplace entrances are included. Carriageways are crossed at zebras; buildings are excluded. Existing road paint and sidewalks are reused, without a second bright NPC pavement layer.

A* minimizes route length. With a common walking speed, this also minimizes travel time. Routes and distances are cached; closures invalidate the cache and trigger replanning. An independent Dijkstra check compares A* distances for every Sector 1 home to both workplaces, with the demonstration crossing open and closed.

Only the 50 Sector 1 residents commute. The remaining 250 profiles stay at home without assignments. Old graph saves are upgraded with IDs, schedules, current outdoor positions and supported closures retained.

## Routing benchmark

Run `py tests/benchmark-pedestrians.py` from `world`. Example on the development computer, 2026-10-04:

| Residents | All routes, cold cache | Per resident | All distances, cached |
| --- | ---: | ---: | ---: |
| 50 | 20.811 ms | 0.416 ms | 0.008 ms |
| 300 | 415.406 ms | 1.385 ms | 0.047 ms |

Graph: 24,124 nodes, 24,973 edges, 300 crossings. Full world initialization took about 1.42 seconds. The 300-resident row is a routing capacity check; it does not enable other sectors. These figures measure server routing, not browser frame time or FPS, and vary by hardware and load.
