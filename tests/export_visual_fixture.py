"""Small reproducible input for the renderer checks; no MQTT or saved production data."""
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hadleys.klyaksa import Colony
from hadleys.world import World
from hadleys.api.snapshots import house_geometry
colony = Colony()
colony.tick(1)
target = ROOT / 'test-results' / 'visual-fixture.json'
target.parent.mkdir(exist_ok=True)
target.write_text(json.dumps({'acheron':house_geometry(World()), 'geometry': json.loads(colony.geometry()), 'state': json.loads(colony.state())}))
print(target)
