"""simulation: colony simulation components."""

from __future__ import annotations
from typing import Optional

import time
from hadleys.config import CFG
from hadleys.domains.attractors import attractor_sample
from hadleys.domains.energy import power_step, reactor_scram, reactor_step
from hadleys.domains.environment import env_step
from hadleys.domains.finance import finance_day_close, finance_month_close
from hadleys.domains.houses import house_events, houses_step
from hadleys.domains.incidents import damage_target, incidents_step, pipes_audit
from hadleys.domains.internet import internet_step
from hadleys.domains.people import people_step
from hadleys.domains.security import spawn_xeno
from hadleys.domains.transport import roads_step
from hadleys.domains.water import water_step
from hadleys.numerics import polar
from hadleys.world import World


def world_tick(w: World):
    if w.finished:
        return
    w.t += 1
    bridge = getattr(w, "bridge", None)
    if bridge:
        bridge.apply()
    env_step(w)
    reactor_step(w)
    power_step(w)
    houses_step(w)
    water_step(w)
    internet_step(w)
    incidents_step(w)
    roads_step(w)
    people_step(w)
    house_events(w)
    if w.t % 60 == 0:
        pipes_audit(w)
    if w.t % w.cfg["ticks_per_day"] == 0:
        finance_day_close(w)
    if w.t % (w.cfg["ticks_per_day"] * w.cfg["days_per_month"]) == 0:
        finance_month_close(w)
    if w.t % 10 == 0:
        attractor_sample(w)
    if bridge:
        bridge.publish()


def inject(w: World, cmd: str):
    rng = w.rng
    c = w.cfg
    if cmd == "span":
        i = int(rng.integers(0, w.P))
        damage_target(w, f"span:{i}", "vandal", 1.0)
        w.log("WARN", f"[manual] span {i} broken")
        return {
            "x": float(w.p_x[i]),
            "y": float(w.p_y[i]),
            "text": f"Span {i} broken in sector {int(w.p_sector[i]) + 1}",
        }
    elif cmd == "pole":
        i = int(rng.integers(0, w.P))
        damage_target(w, f"pole:{i}", "impact", 1.0)
        w.log("WARN", f"[manual] pole {i} fallen")
        return {
            "x": float(w.p_x[i]),
            "y": float(w.p_y[i]),
            "text": f"Pole {i} fell in sector {int(w.p_sector[i]) + 1}",
        }
    elif cmd == "xeno":
        s = int(rng.integers(0, w.S))
        spawn_xeno(w, s, 4)
        w.lockdown_ticks[s] = 240
        w.log("ALARM", f"[manual] xenomorph pack outside sector {s + 1}: LOCKDOWN")
        return {
            "sector": s,
            "x": polar(s * 60 + 30, w.cfg["wall_radius"] + 60)[0],
            "y": polar(s * 60 + 30, w.cfg["wall_radius"] + 60)[1],
            "text": f"Xenomorphs outside sector {s + 1}",
        }
    elif cmd == "storm":
        w.storm_ticks = 400
        w.storm_lighting = True
        w.log("WARN", "[manual] snowstorm")
        return {"text": "Snowstorm for the next 6 hours"}
    elif cmd == "trunk":
        damage_target(w, "trunk", "xenomorph", 1.0)
        return {"x": -c["wall_radius"] - 200, "y": 0, "text": "Trunk line cut"}
    elif cmd == "pump":
        damage_target(w, "reactor:pump_b", "wear", 1.0)
        return {
            "x": c["reactor_pos"][0],
            "y": c["reactor_pos"][1],
            "text": "Reactor pump B tripped",
        }
    elif cmd == "marines":
        w.nest_alert = 300
        w.marines_active = 300
        damage_target(w, "reactor:heat_exchanger", "marines", 0.8)
        w.log("ALARM", "[manual] marines hit the heat exchanger")
        return {
            "x": c["reactor_pos"][0],
            "y": c["reactor_pos"][1],
            "text": "Stray fire hit the heat exchanger",
        }
    elif cmd == "scram":
        reactor_scram(w, "operator")
        return {
            "x": c["reactor_pos"][0],
            "y": c["reactor_pos"][1],
            "text": "Reactor SCRAM",
        }
    elif cmd == "money":
        w.colony_budget += 50000
        w.log("INFO", "[manual] corporation transferred 50 000 cr to the colony")
        return {"text": "50 000 cr received"}
    elif cmd == "road":
        s = int(rng.integers(0, w.S))
        damage_target(w, f"road:{s}", "impact", 1.0)
        w.log("WARN", f"[manual] road segment {s + 1} collapsed")
        return {
            "x": polar(s * 60 + 30, c["ring_road_radius"])[0],
            "y": polar(s * 60 + 30, c["ring_road_radius"])[1],
            "text": f"Ring road collapsed in sector {s + 1}",
        }
    elif cmd == "storm":
        pass
    return {"text": cmd}


def new_colony(w_holder: dict, reason: str):
    """Replace the finished world with a fresh one; the old world's events stay in history.db."""
    old = w_holder["w"]
    w = World(CFG)
    w.speed = old.speed
    w.bridge = getattr(old, "bridge", None)
    if w.bridge:
        w.bridge.w = w
        w.bridge.last_pub_t[:] = -999
    w.log(
        "INFO",
        f"New colony founded ({reason}); the previous one ended with: {old.finish_reason or 'operator reset'}",
    )
    w_holder["w"] = w
    return w


def sim_loop(w_holder: dict, store: Optional[Store]):
    last = time.time()
    acc = 0.0
    last_save = time.time()
    finished_at = None
    while True:
        w = w_holder["w"]
        now = time.time()
        acc += (now - last) * w.speed
        last = now
        n = int(acc)
        acc -= n
        if w.finished:
            finished_at = finished_at or now
            if now - finished_at > 120:
                with w.lock:
                    if store:
                        try:
                            store.record_hour(w)
                        except Exception:
                            pass
                    w = new_colony(
                        w_holder, "automatic restart two minutes after the end"
                    )
                finished_at = None
            time.sleep(0.05)
            acc = 0.0
        elif w.paused:
            time.sleep(0.05)
            acc = 0.0
        else:
            with w.lock:
                for _ in range(min(n, 200)):
                    world_tick(w)
                    if store and w.t % 60 == 0:
                        try:
                            store.record_hour(w)
                        except Exception as e:
                            print("history write failed:", e)
            time.sleep(0.01)
        if store and time.time() - last_save > 300:
            with w.lock:
                try:
                    store.save_world(w)
                except Exception as e:
                    print("autosave failed:", e)
            last_save = time.time()
