"""persistence: colony simulation components."""

from __future__ import annotations

import json
import os
import pickle
import sqlite3
from hadleys.config import CFG
from hadleys.domains.hydraulics import UtilityNetwork
from hadleys.world import World


class LegacyWorldUnpickler(pickle.Unpickler):
    """Resolve class paths written by the former script and importable monolith.

    Only load operator-owned world.pkl files, as before: pickle is not an
    interchange format for untrusted uploads.
    """

    def find_class(self, module, name):
        if module in {"__main__", "hadleys_hope"}:
            from hadleys.models import Issue, Rover

            classes = {
                "World": World,
                "Issue": Issue,
                "Rover": Rover,
                "UtilityNetwork": UtilityNetwork,
            }
            if name in classes:
                return classes[name]
        return super().find_class(module, name)


class Store:
    def __init__(self, data_dir: str):
        self.dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.pkl = os.path.join(data_dir, "world.pkl")
        self.db = os.path.join(data_dir, "history.db")
        con = sqlite3.connect(self.db)
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS hourly (t INTEGER PRIMARY KEY, time TEXT, t_out REAL, wind REAL, storm INTEGER,
                available_kw REAL, demand_kw REAL, shedding INTEGER, reactor_mode TEXT, core_temp REAL,
                water_tank REAL, houses_power INTEGER, houses_water INTEGER, houses_net INTEGER, burst INTEGER,
                issues INTEGER, colony REAL, sectors TEXT, avg_t REAL, min_t REAL);
            CREATE TABLE IF NOT EXISTS events (t INTEGER, level TEXT, text TEXT);
            CREATE TABLE IF NOT EXISTS reports (month INTEGER PRIMARY KEY, saved_t INTEGER, json TEXT);
        """
        )
        con.commit()
        con.close()
        self.last_event_t = -1
        self.last_report_month = 0

    def load_world(self) -> Optional[World]:
        if not os.path.exists(self.pkl):
            return None
        try:
            with open(self.pkl, "rb") as f:
                w = LegacyWorldUnpickler(f).load()
            if getattr(w, "schema", 1) != World.SCHEMA:
                old = self.pkl.replace(".pkl", ".old.pkl")
                os.replace(self.pkl, old)
                print(
                    f"saved world has schema {getattr(w, 'schema', 1)}, current is {World.SCHEMA}; moved it to {old}, starting a new world"
                )
                return None
            added = self.migrate(w)
            print(
                f"resumed world from {self.pkl} at {w.time_str()} (tick {w.t}){', added fields: ' + ', '.join(added) if added else ''}"
            )
            return w
        except Exception as e:
            print(f"could not load {self.pkl}: {e}; starting a new world")
            return None

    @staticmethod
    def migrate(w: World):
        """Fill in attributes a newer version added since the world was saved, using a fresh world's defaults."""
        previous_layout = getattr(w, "layout_version", 3)
        old_defaults = {"garage": (75, 210), "medlab": (195, 210), "school": (315, 210)}
        for key, old in old_defaults.items():
            if tuple(w.cfg.get(key, old)) == old:
                w.cfg[key] = CFG[key]
        w.cfg = {**CFG, **w.cfg}
        fresh = World(w.cfg)
        added = []
        for k, v in fresh.__dict__.items():
            if k not in w.__dict__:
                setattr(w, k, UtilityNetwork(w) if k == "utilities" else v)
                added.append(k)
        if previous_layout < 4 and w.P == fresh.P:
            w.p_x = fresh.p_x.copy()
            w.p_y = fresh.p_y.copy()
            w.p_angle = fresh.p_angle.copy()
            w.layout_version = 4
            added.append("road verges v4")
        for k, v in fresh.cfg.items():
            w.cfg.setdefault(k, v)
        if w.utilities.version != UtilityNetwork.VERSION:
            old = w.utilities
            w.utilities = UtilityNetwork(w)
            for key in (
                "sewer_storage",
                "storm_storage",
                "snow_m3",
                "pump_speed",
                "overflow_m3",
            ):
                setattr(w.utilities, key, getattr(old, key, getattr(w.utilities, key)))
            added.append("utilities v4")
        for r in w.rovers:
            for key, value in [
                ("velocity", 0.0),
                ("fuel_l", 120.0),
                ("odometer_m", 0.0),
            ]:
                if key not in r.__dict__:
                    setattr(r, key, value)
        return added

    def save_world(self, w: World):
        tmp = self.pkl + ".tmp"
        with open(tmp, "wb") as f:
            pickle.dump(w, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, self.pkl)

    def record_hour(self, w: World):
        con = sqlite3.connect(self.db)
        con.execute(
            "INSERT OR REPLACE INTO hourly VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                w.t,
                w.time_str(),
                round(w.t_out, 1),
                round(w.wind, 1),
                int(w.storm_ticks > 0),
                round(w.available_kw),
                round(w.demand_kw),
                w.shedding,
                w.r_mode,
                round(w.r_core_temp),
                round(w.water_tank_m3, 1),
                int(w.h_power_ok.sum()),
                int(w.h_water_ok.sum()),
                int(w.h_net_online.sum()),
                int(w.h_burst.sum()),
                len(w.open_issues()),
                round(w.colony_budget),
                json.dumps([round(float(x)) for x in w.sector_budget]),
                round(float(w.h_t_in.mean()), 1),
                round(float(w.h_t_in.min()), 1),
            ),
        )
        new_events = [e for e in list(w.events) if e["t"] > self.last_event_t]
        if new_events:
            con.executemany(
                "INSERT INTO events VALUES (?,?,?)",
                [(e["t"], e["level"], e["text"]) for e in reversed(new_events)],
            )
            self.last_event_t = max(e["t"] for e in new_events)
        if w.last_report and w.last_report["month"] > self.last_report_month:
            con.execute(
                "INSERT OR REPLACE INTO reports VALUES (?,?,?)",
                (w.last_report["month"], w.t, json.dumps(w.last_report)),
            )
            self.last_report_month = w.last_report["month"]
        con.commit()
        con.close()

    def history(self, hours: int):
        con = sqlite3.connect(self.db)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM hourly ORDER BY t DESC LIMIT ?", (hours,)
        ).fetchall()
        reports = con.execute("SELECT json FROM reports ORDER BY month").fetchall()
        con.close()
        return {
            "hourly": [dict(r) for r in reversed(rows)],
            "reports": [json.loads(r[0]) for r in reports],
        }
