import gzip
import tempfile
import unittest
from pathlib import Path
from hadleys.world import World
from hadleys.persistence import Store
from hadleys.simulation import world_tick
from hadleys.api.snapshots import snapshot
from hadleys.enums import TransportKind, TransportState


class PersistenceTests(unittest.TestCase):
    def test_both_legacy_module_paths_resume(self):
        for name in ("__main__", "hadleys_hope"):
            with self.subTest(module=name), tempfile.TemporaryDirectory() as directory:
                store = Store(directory)
                fixture = Path(__file__).parent / "fixtures" / f"legacy-{name}.pkl.gz"
                Path(store.pkl).write_bytes(gzip.decompress(fixture.read_bytes()))
                w = store.load_world()
                self.assertIsInstance(w, World)
                self.assertEqual(w.t, 123)
                self.assertEqual(len(w.issues), 1)
                world_tick(w)
                self.assertEqual(w.t, 124)
                store.save_world(w)
                resumed = store.load_world()
                self.assertEqual(snapshot(resumed), snapshot(w))
                self.assertFalse(Path(directory, "world.old.pkl").exists())

    def test_history_schema_and_enum_wire_compatibility(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            w = World()
            world_tick(w)
            store.record_hour(w)
            self.assertEqual(store.history(1)["hourly"][0]["t"], 1)
        self.assertEqual(TransportKind.FREIGHT, "freight")
        self.assertEqual(str(TransportState.TO_DEPOT), "TO_DEPOT")
