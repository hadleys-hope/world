"""Measure routing alone, not graphics/FPS: py tests/benchmark-pedestrians.py."""
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from hadleys.world import World

started=time.perf_counter()
w=World()
g=w.navigation
result={'nodes':len(g.nodes),'edges':len(g.edges),'crossings':len(g.crossings),
        'world_initialization_ms':round((time.perf_counter()-started)*1000,2)}
for count in (50,300):
    routes=[(f'home:{i}','work:laboratory' if i%3==2 else 'work:workshop') for i in range(count)]
    g.path_cache.clear();g.length_cache.clear()
    started=time.perf_counter()
    lengths=[g.distance(a,b) for a,b in routes]
    cold=(time.perf_counter()-started)*1000
    started=time.perf_counter()
    for _ in range(100):
        for a,b in routes:
            g.distance(a,b)
    cached=(time.perf_counter()-started)*1000/100
    result[str(count)]={'cold_all_routes_ms':round(cold,3),'cold_per_resident_ms':round(cold/count,3),
                        'cached_all_routes_ms':round(cached,3),'reachable':sum(n is not None for n in lengths)}
print(json.dumps(result,indent=2))
