"""Pure sensor-to-actuator house controller programs."""


def thermostat(mem, t_in, target, band=0.5):
    on = mem.get("heater_on", True)
    if t_in < target - band:
        on = True
    elif t_in > target + band:
        on = False
    mem["heater_on"] = on
    return on


def prog_comfort(st):
    s, env, pw, mem = st["sensors"], st["weather"], st["power"], st["mem"]
    target, why = 21.0, "comfort 21"
    if s["limit_w"] and s["limit_w"] <= 1800:
        target, why = 6.0, "grid limit, antifreeze"
    elif s["limit_w"] or s["on_ups"]:
        target, why = 16.0, "limited power, eco"
    return {
        "target_c": target,
        "heater_on": thermostat(mem, s["t_in"], target),
        "reason": why,
        "appliances_on": not (s["on_ups"] or (s["limit_w"] and s["limit_w"] <= 1800)),
        "valve_open": s["pipes_ok"],
    }


def prog_eco(st):
    s, env, pw, mem = st["sensors"], st["weather"], st["power"], st["mem"]
    night = env.get("night", False)
    target, why = (15.0, "eco night 15") if night else (18.0, "eco day 18")
    if pw.get("shedding", 0) >= 3:
        target, why = target - 2, f"shedding L{pw['shedding']}, minus 2"
    if s["limit_w"] and s["limit_w"] <= 1800:
        target, why = 6.0, "grid limit, antifreeze"
    return {
        "target_c": target,
        "heater_on": thermostat(mem, s["t_in"], target, 0.7),
        "reason": why,
        "appliances_on": not s["on_ups"],
        "valve_open": s["pipes_ok"],
    }


def prog_night_setback(st):
    s, env, pw, mem = st["sensors"], st["weather"], st["power"], st["mem"]
    hour = env.get("hour", 12.0)
    if 5.0 <= hour < 6.0:
        target, why = 21.0, "warm-up before morning"
    elif hour >= 22.0 or hour < 6.0:
        target, why = 16.0, "night setback 16"
    else:
        target, why = 21.0, "day 21"
    if s["on_ups"]:
        target, why = 14.0, "on ups, stretch the battery"
    if s["limit_w"] and s["limit_w"] <= 1800:
        target, why = 6.0, "grid limit, antifreeze"
    return {
        "target_c": target,
        "heater_on": thermostat(mem, s["t_in"], target),
        "reason": why,
        "appliances_on": not s["on_ups"],
        "valve_open": s["pipes_ok"],
    }


def prog_storm_ready(st):
    s, env, pw, mem = st["sensors"], st["weather"], st["power"], st["mem"]
    target, why = 21.0, "comfort 21"
    if env.get("storm") or env.get("wind", 0) > 20:
        target, why = 23.5, "storm, banking heat"
    if not s["net_online"]:
        why = why + " (offline, last forecast)"
    if s["on_ups"]:
        target, why = 12.0, "on ups, minimum"
    if s["limit_w"] and s["limit_w"] <= 1800:
        target, why = 6.0, "grid limit, antifreeze"
    return {
        "target_c": target,
        "heater_on": thermostat(mem, s["t_in"], target),
        "reason": why,
        "appliances_on": not (s["on_ups"] or bool(s["limit_w"])),
        "valve_open": s["pipes_ok"],
    }


def prog_dumb(st):
    s, mem = st["sensors"], st["mem"]
    return {
        "target_c": 26.0,
        "heater_on": thermostat(mem, s["t_in"], 26.0, 1.0),
        "reason": "always warm, never saves",
        "appliances_on": True,
        "valve_open": True,
    }


PROGRAMS = {
    "comfort": prog_comfort,
    "eco": prog_eco,
    "night-setback": prog_night_setback,
    "storm-ready": prog_storm_ready,
    "dumb": prog_dumb,
}
