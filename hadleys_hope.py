"""Hadley's Hope colony simulation, LV-426.

One process, one file: environment, reactor and grid, 300 houses, water,
internet, roads and rovers, incidents, finance, a browser UI and persistence.
Run `python3 hadleys_hope.py` and open http://localhost:8000.

Modelling revision: shared SI utility graph, pressure-dependent domestic water,
separate gravity drains and zoom-loaded prefab interiors. Viewer: "inspect a
home", "roof transparency", and "underground utilities". Select pipes
for live engineering data. Procedural assets need no downloaded texture packs.
The Attractors navigation tab preserves the thermal phase portrait and water,
power/UPS, repair and money history panels. Its optional 3D water-coupling view
plots measured temperature, thermal rate and gauge pressure, with selectable
basin/district/pressure colour. Preview flow assumes fixed weather and loads.
Main HUD: Colony / Water / Power / Network presets; Overview / Layers / Places /
Operations panels. Operator scenario controls are in Operations.

Scope: expanded 300-house interpretation of Hadley's Hope, retaining the original
six-sector layout and simulation interfaces. Hydraulic model is quasi-steady
Darcy-Weisbach on an explicitly branched network, not EPANET or water hammer.
Drainage uses Manning capacity plus aggregate sump storage, not a backwater PDE.
Elevated mains assume maintained insulation/heat tracing; domestic freeze/burst
uses the existing indoor thermal model. Glass reflections use a procedural
prefiltered environment, not ray tracing. Detailed interiors load within 480 m for up to 32 homes plus an inspected home.
Batched two/three-storey facades, windows and rooftop equipment remain visible
at colony scale. Pipe cutaway jackets are slightly enlarged for legibility.
Local controls: drag to pan, right-drag to orbit, wheel/trackpad to zoom at
cursor, WASD/arrows to move, Q/E for altitude, Shift to accelerate, F to focus.
Roofs remain visible at all distances (opacity 0.84; C toggles 0.62).
The civic core has two towers; a separate 64 m paraboloid serves the space
uplink, independently of the 5G site. Ocean intake conserves water/brine mass
and caps ice-melting heat at the reactor's available heat recovery.
Cargo cranes consume a finite stock of 24 containers; deliveries use the inner
road and the same signal schedule as the visible traffic heads.
Road vehicles use lane offsets, grade/ice speed reduction, acceleration,
following gaps, timed signals and fuel bookkeeping; this is a kinematic model. Pressure is gauge kPa,
flow is L/s, geometry metres. Surface-water precipitation is water-equivalent.

References: https://usepa.github.io/EPANET2.2/12_analysis_algorithms.html
Design context: https://alienseries.wordpress.com/2012/10/18/hadleys-hope/

"""
from __future__ import annotations

import json
import math
import os
import pickle
import random
import signal
import sqlite3
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

# ------------------------------------------------------------------------------------
# Configuration. Every number the simulation uses lives here.
# ------------------------------------------------------------------------------------

CFG = {
    "seed": 12345,
    "sectors": 6,
    "houses_per_sector": 50,
    "tick_seconds": 60,
    "ticks_per_day": 1440,
    "days_per_month": 30,
    # geometry (map units, roughly metres). The city is a ring of six sectors inside a wall.
    "hub_radius": 140,
    "house_radius_min": 300,        # first row of houses
    "house_ring_step": 60,          # distance between rows; streets run between rows
    "house_rows": 5,
    "ring_road_radius": 640,
    "wall_radius": 690,
    "spine_radii": [200, 270, 330, 390, 450, 510, 570, 640],   # poles along each boundary street
    "arc_pole_angles": [10.0, 20.5, 31.0, 41.5, 52.0],         # poles along each row street, degrees inside the sector
    "reactor_pos": (-1280, 0),
    "solar_pos": (-1480, -300),
    "water_plant_pos": (-1280, 220),
    "radwaste_pos": (-1280, 420),
    "mine_pos": (-1280, 620),
    "waste_station_pos": (-1000, 140),
    "tower_junction": (-1000, 0),
    "tower_pos": (-1000, -540),
    "dish_pos": (-1680, -930),
    "ocean_intake_pos": (-1710, 220),
    "ocean_level_m": -8.0,
    "ocean_center": (-2350, 550),
    "ocean_radii": (900, 1150),
    "water_heat_kw": 1900.0,
    "water_recovery": 0.85,
    "traffic_vehicles": 18,
    "cargo_depot": (136.0, 210.0),
    "landing_pad_pos": (960, 0),
    "garage": (75.0, 210.0),          # polar: angle, radius; vehicle bay in sector 1
    "medlab": (195.0, 210.0),
    "school": (315.0, 210.0),
    "walkers": 60,
    # environment (LV-426: minus 40..60, permanent dusk, storms)
    "t_mean": -45.0,
    "t_daily_amp": 8.0,
    "storm_prob_per_tick": 0.0004,
    "storm_len_ticks": (180, 600),
    "storm_wind": (22.0, 34.0),
    "calm_wind": (4.0, 14.0),
    "daylight_max": 0.3,
    # houses
    "heater_kw": [3.5, 3.0, 3.0, 4.5],          # by type: barracks, standard, insulated, manager
    "ua_w_per_k": [38.0, 32.0, 22.0, 45.0],
    "heat_cap_j_per_k": [0.8e7, 1.0e7, 1.3e7, 1.8e7],
    "base_load_w": [200, 300, 300, 600],
    "type_counts": [120, 120, 45, 15],
    "comfort_c": 21.0, "eco_c": 16.0, "antifreeze_c": 5.0,
    "freeze_ticks_to_frozen": 60, "frozen_ticks_to_burst": 30,
    "water_per_house_m3_day": 0.2,
    # reactor
    "reactor_gross_mw": 6.0, "reactor_self_mw": 0.6, "heat_export_mw": 3.0,
    "ramp_frac_per_min": 0.05, "core_temp_nominal": 780.0, "core_temp_limit": 1200.0,
    "pump_battery_h": 8.0, "reserve_mw": 0.5,
    # grid
    "solar_peak_kw": 200.0,
    "mine_kw": 2000.0, "water_plant_kw": 300.0, "waste_storage_kw": 20.0,
    "ops_center_kw": 40.0, "comms_kw": 20.0, "cabinet_kw": 1.0, "gate_kw": 2.0,
    "lamp_kw": 0.25, "road_heating_kw": 300.0,
    "aeration_w": 150.0, "pump_station_kw": 50.0,
    "ups_center_kw": 150.0, "ups_center_kwh": 800.0,
    "ups_sector_kw": 100.0, "ups_sector_kwh": 400.0,
    "ups_charge_kw": 100.0,
    "limit_level3_w": 2500.0, "limit_level5_w": 1800.0,
    # water
    "water_tank_m3": 500.0, "water_plant_m3_h": 12.0,
    # finance
    "sector_budget": 10000.0, "colony_budget": 100000.0,
    "tariff_kwh": 0.25, "tariff_water_m3": 3.0, "sewage_fee": 20.0, "internet_fee": 15.0,
    "mine_income_per_tick": 3.0,
    # economy feedback: without these the colony budget only grows and has no attractor
    "colony_payroll_day": 2500.0,        # staff wages and supply shipments, paid every day even with the mine down
    "company_reserve_target": 100000.0,  # reserve the company leaves in the colony
    "company_levy_frac": 0.5,            # share of the surplus above the target the company takes at month close
    "sector_budget_cap": 30000.0,        # sector money above this goes to the colony at month close
    "reactor_upkeep_month": 3000.0,
    # incidents: probability per tick
    "p_xeno": 0.00004, "p_vandal": 0.00025, "p_animal": 0.0002, "p_rover_hit": 0.0003,
    "p_nest_fire": 0.02,           # per tick while a xeno attack near the processor is open
    "p_pump_wear": 0.00002,
    # sewage and waste
    "sludge_per_resident_per_tick": 1.0 / (1440 * 60),
    "waste_per_resident_per_tick": 1.0 / (1440 * 6 * 50),
    "rover_speed": 14.0,           # map units per tick on a good road
    # ui
    "http_port": 8000,
    "default_speed": 20,
}

COSTS = {
    "span": (200, "sector", 120), "pole": (600, "sector", 180), "feeder": (800, "sector", 240),
    "rp": (1500, "sector", 240), "ups": (1000, "sector", 120), "tower_line": (500, "colony", 240),
    "trunk": (3000, "colony", 480), "substation": (5000, "colony", 480),
    "pump": (4000, "colony", 360), "heat_exchanger": (15000, "colony", 720),
    "solar": (800, "colony", 120), "wiring": (600, "house", 120), "pipes": (1200, "house", 180),
    "aeration": (900, "house", 120), "cabinet": (400, "sector", 240), "net_span": (150, "sector", 120),
    "terminal": (80, "house", 60), "lamp": (300, "sector", 60), "road": (500, "sector", 3),
    "gate": (1200, "sector", 120), "waste_trip": (100, "sector", 0), "sludge_trip": (120, "sector", 0),
    "wall": (800, "sector", 200),
}

TYPE_NAMES = ["barracks", "standard", "insulated", "manager"]


def clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def polar(angle_deg, radius):
    a = math.radians(angle_deg)
    return radius * math.cos(a), radius * math.sin(a)


# ------------------------------------------------------------------------------------
# Utility engineering. SI units; one rooted pressure network, no decorative fake links.
# Steady state per tick (not a water-hammer or drinking-water quality model).
# Darcy-Weisbach / pressure-dependent demand: USEPA EPANET 2.2, chapter 12.
# ------------------------------------------------------------------------------------

RIVER_PROFILE = [(500,1550,46), (50,1490,34), (-410,1250,23), (-900,1060,12), (-1450,840,1), (-2050,740,-8)]


def coast_height(x,y,height):
    """Shared coastal basin and graded frozen river profile; keep colony terraces intact."""
    if math.hypot(x,y)<900:return height
    q=math.hypot((x+2350)/900,(y-550)/1150)
    az=math.atan2((y-550)/1150,(x+2350)/900)
    q/=1+.08*math.sin(3*az)+.05*math.sin(7*az)+.025*math.sin(11*az)
    t=clamp((1.10-q)/.16,0,1);t=t*t*(3-2*t)
    height=height*(1-t)+(-26-22*max(0,1-q*q))*t
    for a,b in zip(RIVER_PROFILE,RIVER_PROFILE[1:]):
        dx,dy=b[0]-a[0],b[1]-a[1]
        u=clamp(((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy),0,1)
        distance=math.hypot(x-a[0]-u*dx,y-a[1]-u*dy)
        t=clamp((95-distance)/70,0,1);t=t*t*(3-2*t)
        target=a[2]+(b[2]-a[2])*u-2
        height=height*(1-t)+target*t
    return height


def site_elevation(x, y, c):
    """Same finished grades as terrainH in the viewer (metres above local datum)."""
    r = math.hypot(x, y)
    def smooth(a, b, v):
        t = clamp((v-a)/(b-a), 0.0, 1.0)
        return t*t*(3-2*t)
    if r < c['hub_radius']:
        h = 8.0
    elif r < c['house_radius_min']-30:
        h = 8-3*smooth(c['hub_radius'], c['house_radius_min']-30, r)
    elif r < c['ring_road_radius']:
        u = (r-(c['house_radius_min']-30))/c['house_ring_step']
        k = math.floor(u)
        h = 5+k*3.4+3.4*smooth(.62, 1, u-k)
    elif r < c['wall_radius']+20:
        h = 5+c['house_rows']*3.4
    else:
        h = (5+c['house_rows']*3.4)*(1-smooth(c['wall_radius']+20, c['wall_radius']+260, r))
    # Engineered terraces meet a continuous, rolling basalt landscape.
    natural = 22+24*math.sin(x*.0018)*math.cos(y*.0024)+14*math.sin(x*.004+y*.001)
    for px,py,height,width in [(1250,850,180,280),(-450,-1350,145,360),(-1640,980,220,310),(450,1650,190,330)]:
        natural += height*math.exp(-((x-px)**2+(y-py)**2)/(width*width))
    blend = smooth(c['wall_radius']+20, c['wall_radius']+320, r)
    return coast_height(x,y,h+blend*natural+.5*math.sin(x*.031)*math.cos(y*.027))



class UtilityNetwork:
    """Rooted, isolatable district mains. Every service has one traced supply path.

    A tree is intentional: sector isolation cannot secretly backfeed through a
    decorative ring. Nodes/links are also the authoritative drawing coordinates.
    Sanitary and storm gravity networks run in separate corridors and outfalls.
    """
    VERSION = 3

    def __init__(self, w):
        self.version = self.VERSION
        c = w.cfg
        self.nodes, self.links = [], []
        self.house_nodes = np.zeros(w.N, dtype=int)
        def node(xy, kind, sector=-1, house=-1, height=3.6):
            x, y = map(float, xy)
            n = len(self.nodes)
            self.nodes.append(dict(id=n, x=x, y=y, z=site_elevation(x,y,c)+height,
                                   kind=kind, sector=int(sector), house=int(house)))
            return n
        def link(a, b, diameter, kind, points=None):
            na, nb = self.nodes[a], self.nodes[b]
            pts = points or [[na['x'],na['y']], [nb['x'],nb['y']]]
            xyz = [[float(x),float(y),site_elevation(x,y,c)+3.6] for x,y in pts]
            xyz[0] = [na['x'],na['y'],na['z']]
            xyz[-1] = [nb['x'],nb['y'],nb['z']]
            if kind in ('main','district','header'):
                # Keep this route above vehicle clearance; node endpoints are shared.
                for v in xyz[1:-1]:v[2]=site_elevation(v[0],v[1],c)+7.2
            length = sum(math.dist(p,q) for p,q in zip(xyz,xyz[1:]))
            self.links.append(dict(id=len(self.links), a=a, b=b, diameter_m=diameter,
                                   length_m=length, roughness_m=.000007 if diameter<.1 else .000045,
                                   material='PE100 SDR11' if diameter<.1 else 'lined ductile iron',
                                   insulation_mm=60, minor_k=2.5 if kind=='service' else 1.2,
                                   kind=kind, sector=nb['sector'], points=xyz))
        root = node((-70,-45), 'tank', height=24)
        pump = node((-40,-40), 'pump')
        link(root,pump,.25,'pump')
        # A common header goes round the outside of the civic campus. Branch
        # spines sit 12 m to the side of the road centre, beyond its sidewalk.
        headers=[];rr=c['hub_radius']+24
        start_angle=math.degrees(math.atan2(12,rr))
        for sector in range(w.S):
            angle=sector*60+start_angle
            header=node(polar(angle,rr),'header',height=7.2)
            if sector==0:
                na=self.nodes[pump];nb=self.nodes[header]
                link(pump,header,.22,'header',[(na['x'],na['y']),(-40,-130),(rr,-130),(nb['x'],nb['y'])])
            else:
                pts=[polar(v,rr) for v in np.linspace((sector-1)*60+start_angle,angle,33)]
                link(headers[-1],header,.20,'header',pts)
            headers.append(header)
        for sector in range(w.S):
            angle=sector*60.0;rad=math.radians(angle)
            def shoulder(r):return (r*math.cos(rad)-12*math.sin(rad),r*math.sin(rad)+12*math.cos(rad))
            prev=node(shoulder(c['hub_radius']+28),'isolation',sector,height=7.2)
            link(headers[sector],prev,.15,'district')
            for row in range(c['house_rows']):
                r=c['house_radius_min']-18+row*c['house_ring_step']
                junction=node(shoulder(r),'tee',sector,height=7.2)
                link(prev,junction,.125,'main');prev=junction
                last=junction;previous_angle=angle+math.degrees(math.atan2(12,r))
                for i in np.flatnonzero((w.h_sector==sector)&(w.h_ring==row)):
                    end_angle=float(w.h_angle[i]);tap=node(polar(end_angle,r),'tee',sector)
                    pts=[polar(v,r) for v in np.linspace(previous_angle,end_angle,max(3,int((end_angle-previous_angle)/.8)+1))]
                    link(last,tap,.08,'row',pts)
                    # The last point is the exact common service inlet, under the wet core.
                    service=node(polar(end_angle,float(w.h_radius[i])-6),'meter',sector,int(i),.9)
                    link(tap,service,.025,'service');self.house_nodes[i]=service
                    last,previous_angle=tap,end_angle
        self.a = np.array([e['a'] for e in self.links])
        self.b = np.array([e['b'] for e in self.links])
        self.length = np.array([e['length_m'] for e in self.links])
        self.diameter = np.array([e['diameter_m'] for e in self.links])
        self.roughness = np.array([e['roughness_m'] for e in self.links])
        self.minor = np.array([e['minor_k'] for e in self.links])
        self.z = np.array([n['z'] for n in self.nodes])
        self.parent_edge = np.full(len(self.nodes),-1,dtype=int)
        self.parent_edge[self.b] = np.arange(len(self.links))
        depth = np.zeros(len(self.nodes),dtype=int)
        for a,b in zip(self.a,self.b): depth[b]=depth[a]+1
        self.levels = [np.flatnonzero(depth[self.b]==d) for d in range(1,int(depth.max())+1)]
        self.head = self.z.copy()
        self.flow = np.zeros(len(self.links))
        self.velocity = self.flow.copy()
        self.loss = self.flow.copy()
        self.pressure = np.zeros(w.N)
        self.delivered = np.zeros(w.N)
        self.leaks = np.zeros(w.N)
        self.converged = True
        self.residual = 0.0
        self.iterations = 0
        self.pump_speed = 1.0
        self.sewer_storage = 0.0
        self.storm_storage = 0.0
        self.snow_m3 = 0.0
        self.sewer_out_m3 = self.storm_out_m3 = self.overflow_m3 = 0.0
        self.drainage = self._drainage(w)
        self.drain_rates = [np.zeros(len(self.links)), np.zeros(len(self.links))]

    def _drainage(self,w):
        """Separate foul/surface-water trees; inverts descend all the way to outfall.

        Deep collectors are required by the artificial terrace grades. Lift at the
        western treatment sump is explicit; no uphill gravity sewer is implied.
        """
        systems = []
        for name, offset, rough in [('sanitary',2.3,.013),('storm',-2.3,.015)]:
            nodes = []
            for n in self.nodes:
                a=math.atan2(n['y'],n['x'])
                nodes.append(dict(x=n['x']-math.sin(a)*offset,y=n['y']+math.cos(a)*offset,z=0.0,
                                  kind=n['kind'],house=n['house']))
            # Accumulate rises first, then lower the whole network to maintain cover.
            distances=[]
            for e in self.links:
                a,b=e['a'],e['b']; pa,pb=nodes[a],nodes[b]
                L=e['length_m']; slope=.02 if e['kind']=='service' else .005
                nodes[b]['z']=nodes[a]['z']+L*slope
                distances.append((L,slope))
            datum=min(site_elevation(n['x'],n['y'],w.cfg)-3.2-n['z'] for n in nodes)
            for n in nodes:n['z']+=datum
            edges=[]
            for e,(L,slope) in zip(self.links,distances):
                # A service is 110 mm; rows 250 mm; collectors 450/600 mm.
                d=.11 if e['kind']=='service' else (.25 if e['kind']=='row' else (.6 if name=='storm' else .45))
                area=math.pi*d*d/4
                capacity=area*(d/4)**(2/3)*math.sqrt(slope)/rough
                pts=[]
                for k,p in enumerate(e['points']):
                    f=k/(len(e['points'])-1); a,b=nodes[e['a']],nodes[e['b']]
                    ang=math.atan2(p[1],p[0])
                    pts.append([p[0]-math.sin(ang)*offset,p[1]+math.cos(ang)*offset,a['z']+(b['z']-a['z'])*f])
                pts[0]=[nodes[e['a']][k] for k in ('x','y','z')]
                pts[-1]=[nodes[e['b']][k] for k in ('x','y','z')]
                edges.append(dict(a=e['b'],b=e['a'],diameter_m=d,slope=slope,length_m=L,
                                  material='vitrified clay' if name=='sanitary' else 'reinforced concrete',
                                  capacity_m3_s=capacity,points=pts))
            outlet=nodes[0]
            plant=w.cfg['water_plant_pos']
            # These are pumped rising mains, shown separately from gravity links.
            rising=[[outlet[k] for k in ('x','y','z')],
                    [plant[0]+20,plant[1]-12,site_elevation(*plant,w.cfg)-2.5]]
            systems.append(dict(name=name,nodes=nodes,links=edges,rising_main=rising,
                                outfall='western treatment / retention works',manning_n=rough))
        return systems

    def aggregate(self, demand):
        out=demand.copy()
        for ids in reversed(self.levels): np.add.at(out,self.a[ids],out[self.b[ids]])
        return out[self.b]

    def headloss(self,q):
        """Darcy-Weisbach; laminar f=64/Re; Swamee-Jain turbulent estimate."""
        v=4*np.abs(q)/(math.pi*self.diameter**2)
        re=v*self.diameter/1.31e-6  # 10 C water
        safe=np.maximum(re,1.0)
        turbulent=.25/np.log10(self.roughness/(3.7*self.diameter)+5.74/np.maximum(safe,2300)**.9)**2
        blend=np.clip((re-2300)/1700,0,1)
        f=(1-blend)*64/safe+blend*turbulent
        return (f*self.length/self.diameter+self.minor)*v*v/(2*9.81)

    def solve(self,w,requested):
        dt=float(w.cfg['tick_seconds'])
        active=w.water_main_ok[w.h_sector]&w.h_valve_open
        intact=w.h_pipes_ok&~w.h_burst
        active &= bool(w.pump_station_ok and w.water_tank_m3>0)
        requested=np.where(active&intact,requested,0.0)
        leak_area=np.where(active&w.h_burst,math.pi*.0015**2,0.0) # 3 mm equivalent break
        node_load=np.zeros(len(self.nodes))
        p=np.maximum(self.pressure/9.81,20.0)
        use=np.zeros(w.N); leak=use.copy()
        for iteration in range(200):
            use=requested*np.sqrt(np.clip(p/15.0,0,1))
            leak=.62*leak_area*np.sqrt(2*9.81*np.maximum(p,0))
            total=float((use+leak).sum())
            # Average partial-tick delivery when the tank runs dry, exact mass balance.
            factor=min(1.0,w.water_tank_m3/max(total*dt,1e-30))
            use*=factor; leak*=factor
            node_load.fill(0); node_load[self.house_nodes]=use+leak
            q=self.aggregate(node_load)
            loss=self.headloss(q)
            source=self.z[0]+6.12*w.water_tank_m3/w.cfg['water_tank_m3']
            head=np.full(len(self.nodes),source)
            pump_gain=max(0,28*self.pump_speed**2-20000*q[0]**2) if w.pump_station_ok else 0.0
            for ids in self.levels:
                head[self.b[ids]]=head[self.a[ids]]-loss[ids]
                if 0 in ids:head[1]+=pump_gain
            target=np.where(active,np.maximum(0,head[self.house_nodes]-self.z[self.house_nodes]),0)
            error=float(np.max(np.abs(target-p)))
            if error<1e-6:break
            p=.65*p+.35*target
        self.iterations=iteration+1; self.converged=error<1e-5; self.residual=error
        self.head=head; self.flow=q; self.loss=loss
        self.velocity=4*q/(math.pi*self.diameter**2)
        self.pressure=target*9.81  # kPa, gauge
        self.delivered=use*dt; self.leaks=leak*dt
        w.h_water_ok=active&intact&(target>=3.0)&(use>=requested*.95)&(factor>.95)
        return self.delivered

    def geometry(self,w):
        c=w.cfg; plant=c['water_plant_pos']
        feed_xy=[[plant[0]+30,plant[1]], [plant[0]+86,plant[1]], [plant[0]+86,18], [-164,18], [-164,-130], [-70,-130], [-70,-45]]
        feed=[]
        for a,b in zip(feed_xy,feed_xy[1:]):
            count=max(1,math.ceil(math.dist(a,b)/12))
            for j in range(count):
                t=j/count;x=a[0]+(b[0]-a[0])*t;y=a[1]+(b[1]-a[1])*t
                feed.append([x,y,site_elevation(x,y,c)+7.2])
        feed.append([-70,-45,site_elevation(-70,-45,c)+7.2])
        feed.append([-70,-45,self.z[0]+6.5])
        return dict(nodes=self.nodes,links=self.links,house_nodes=self.house_nodes.tolist(),
                    drainage=self.drainage,plant_feed=feed,version=self.VERSION)

    def state(self):
        return dict(pressure_kpa=np.round(self.pressure,2).tolist(),flow_l_s=np.round(self.flow*1000,5).tolist(),
                    velocity_m_s=np.round(self.velocity,5).tolist(),headloss_m=np.round(self.loss,6).tolist(),
                    head_m=np.round(self.head,4).tolist(),delivered_l=np.round(self.delivered*1000,4).tolist(),
                    leak_l=np.round(self.leaks*1000,4).tolist(),converged=self.converged,
                    residual_m=self.residual,iterations=self.iterations,
                    sewer_storage_m3=round(self.sewer_storage,5),storm_storage_m3=round(self.storm_storage,5),
                    snow_m3=round(self.snow_m3,5),sewer_out_m3=round(self.sewer_out_m3,5),
                    storm_out_m3=round(self.storm_out_m3,5),overflow_m3=round(self.overflow_m3,5),
                    drainage_l_s=[np.round(q*1000,5).tolist() for q in self.drain_rates])


def hydraulic_step(w):
    if not hasattr(w,'utilities') or w.utilities.version != UtilityNetwork.VERSION:w.utilities=UtilityNetwork(w)
    u=w.utilities; c=w.cfg; dt=float(c['tick_seconds'])
    hour=(w.t%1440)/60
    diurnal=.5+.9*max(0,math.sin(math.pi*(hour-5)/16))
    request=c['water_per_house_m3_day']/86400*(1+.5*w.h_residents)*diurnal
    use=u.solve(w,request)
    w.h_water_m3+=use; w.h_water_day+=use; w.h_water_month+=use
    w.sector_water_m3=np.bincount(w.h_sector,weights=use,minlength=w.S)
    w.water_flow_m3_h=float((use+u.leaks).sum())/dt*3600
    w.water_tank_m3=max(0,w.water_tank_m3-float((use+u.leaks).sum()))
    # Ninety percent return to the separate foul sewer after household use.
    # Manning full-bore capacities bound each subtree. This is a lumped storage
    # approximation, not an unsteady free-surface/backwater solver.
    for system,attr,inflow in [(u.drainage[0],'sewer_storage',use*.9),
                               (u.drainage[1],'storm_storage',u.leaks.copy())]:
        if attr=='storm_storage':
            # Water-equivalent precipitation accumulates as snow below freezing.
            rain=(.003 if w.storm_ticks>0 else .0002) if w.precip!='none' else 0.0
            volume=rain*(w.N*350)*dt/3600
            if w.t_out<=0:u.snow_m3+=volume; volume=0.0
            melt=min(u.snow_m3,max(0,w.t_out)*.0001*w.N*350*dt/3600)
            u.snow_m3-=melt
            inflow+=(volume+melt)/w.N
        loads=np.zeros(len(u.nodes)); loads[u.house_nodes]=inflow/dt
        rates=u.aggregate(loads)
        u.drain_rates[0 if attr=='sewer_storage' else 1]=rates
        ratios=[e['capacity_m3_s']/q for e,q in zip(system['links'],rates) if q>0]
        ratio=min(1.0,min(ratios,default=1.0))
        amount=float(inflow.sum()); queued=getattr(u,attr)+amount
        # Lift pumps run on the same protected supply as the potable station.
        capacity=(.012 if attr=='sewer_storage' else .08)*dt if w.pump_station_ok else 0.0
        out=min(queued,capacity,max(0,amount*ratio)+max(0,capacity-amount))
        storage=queued-out; overflow=max(0,storage-200)
        setattr(u,attr,min(storage,200)); u.overflow_m3+=overflow
        if attr=='sewer_storage':u.sewer_out_m3=out
        else:u.storm_out_m3=out
    w.h_sludge+=np.where(w.h_water_ok,c['sludge_per_resident_per_tick']*(1+w.h_residents),0)
    w.h_sludge=np.minimum(w.h_sludge,1.0)


# ------------------------------------------------------------------------------------
# World state
# ------------------------------------------------------------------------------------

@dataclass
class Issue:
    id: int
    kind: str
    target: str          # "span:12", "pole:3", "house:17", "reactor:pump_b", "road:2", "gate:4" ...
    sector: int          # -1 for colony objects
    cause: str
    cost: float
    payer: str           # sector | colony | house
    duration: int        # repair ticks
    pos: tuple
    opened_t: int
    status: str = "open" # open | funded | in_progress | resolved | unfunded
    severity: str = "warning"
    started_t: int = -1
    resolved_t: int = -1


@dataclass
class Rover:
    name: str
    kind: str                       # garbage | sludge | repair | plumber
    x: float = 0.0
    y: float = 0.0
    state: str = "IDLE"
    route: list = field(default_factory=list)   # list of (x, y) waypoints
    job: Optional[object] = None    # sector index, house index or Issue
    timer: int = 0
    load: float = 0.0
    speed: float = 14.0
    wait: int = 0
    heading: float = 0.0
    velocity: float = 0.0       # map metres per simulation tick
    odometer_m: float = 0.0
    fuel_l: float = 120.0


class World:
    SCHEMA = 4      # bump when array layouts change; new plain attributes are filled in by Store.migrate on load

    def __init__(self, cfg=CFG):
        self.schema = self.SCHEMA
        self.cfg = cfg
        self.rng = np.random.default_rng(cfg["seed"])
        self.pyrng = random.Random(cfg["seed"])
        self.t = 0
        self.speed = cfg["default_speed"]
        self.paused = False
        self.finished = False
        self.finish_reason = ""
        self.events = deque(maxlen=400)
        self.issues: list[Issue] = []
        self.next_issue_id = 1
        self.packets = []
        self.lock = threading.Lock()
        S = cfg["sectors"]
        H = cfg["houses_per_sector"]
        self.S = S
        self.N = N = S * H

        # ---- houses (numpy) ----
        idx = np.arange(N)
        self.h_sector = idx // H
        self.h_ring = (idx % H) // 10
        self.h_slot = idx % 10
        self.h_angle = self.h_sector * 60.0 + 7.5 + self.h_slot * 5.2
        self.h_radius = cfg["house_radius_min"] + self.h_ring * cfg["house_ring_step"]
        self.h_x = self.h_radius * np.cos(np.radians(self.h_angle))
        self.h_y = self.h_radius * np.sin(np.radians(self.h_angle))
        types = np.concatenate([np.full(c, i) for i, c in enumerate(cfg["type_counts"])])
        self.rng.shuffle(types)
        self.h_type = types
        self.h_ua = np.array(cfg["ua_w_per_k"])[types]
        self.h_cap = np.array(cfg["heat_cap_j_per_k"])[types]
        self.h_heater_w = np.array(cfg["heater_kw"])[types] * 1000.0
        self.h_base_w = np.array(cfg["base_load_w"])[types].astype(float)
        self.h_residents = self.rng.integers(0, 3, N)
        self.h_residents[self.h_type == 3] = 2
        self.h_t_in = np.full(N, 20.0)
        self.h_heater_on = np.ones(N, dtype=bool)
        self.h_target = np.full(N, cfg["comfort_c"])
        self.h_draw_w = np.zeros(N)
        self.h_heat_w = np.zeros(N)
        self.h_limit_w = np.zeros(N)
        self.h_power_ok = np.ones(N, dtype=bool)
        self.h_on_ups = np.zeros(N, dtype=bool)
        self.h_meter_kwh = np.zeros(N)
        self.h_meter_month = np.zeros(N)
        self.h_meter_day = np.zeros(N)
        self.h_water_day = np.zeros(N)
        self.h_water_month = np.zeros(N)
        self.h_water_m3 = np.zeros(N)
        self.h_pipes_ok = np.ones(N, dtype=bool)
        self.h_frozen = np.zeros(N, dtype=int)
        self.h_burst = np.zeros(N, dtype=bool)
        self.h_water_ok = np.ones(N, dtype=bool)
        self.h_wiring_ok = np.ones(N, dtype=bool)
        self.h_terminal_ok = np.ones(N, dtype=bool)
        self.h_aeration_ok = np.ones(N, dtype=bool)
        self.h_sludge = self.rng.uniform(0.0, 0.6, N)
        self.h_net_online = np.ones(N, dtype=bool)
        self.h_valve_open = np.ones(N, dtype=bool)
        self.h_appliances_on = np.ones(N, dtype=bool)
        self.h_repairs_month = np.zeros(N)
        # external house controllers (runtime over MQTT); fallback thermostat when stale
        self.h_ctrl_t = np.full(N, -10_000)
        self.h_ctrl_heater = np.zeros(N, dtype=bool)
        self.h_ctrl_target = np.full(N, cfg["comfort_c"])
        self.h_ctrl_valve = np.ones(N, dtype=bool)
        self.h_ctrl_appl = np.ones(N, dtype=bool)
        self.h_program = [""] * N
        self.h_reason = [""] * N
        self.prog_stats = {}        # program name -> {"kwh", "house_ticks", "cold_ticks", "t_sum"} accumulated this month
        self.h_log = [deque(maxlen=40) for _ in range(N)]      # per-house event log: transitions and decisions
        self.h_hist = np.full((N, 144), 20.0)                  # indoor temperature every 10 minutes, last 24 h
        self.h_hist_draw = np.zeros((N, 144))
        self.h_hist_i = 0
        self.h_prev = None

        # ---- poles: a tree per sector. Spine along the boundary street (angle s*60),
        #      branches along each row street; every pole carries a lamp, a power span
        #      and an internet cable back to its parent ----
        spine_r = cfg["spine_radii"]
        arc_a = cfg["arc_pole_angles"]
        px, py, ps, pk, parent, kind, prad, pang = [], [], [], [], [], [], [], []
        self.spine_index = {}       # (sector, radius) -> pole index
        for s in range(S):
            first = len(px)
            for j, r in enumerate(spine_r):
                base_angle = s * 60.0 + math.degrees(9.0 / r)      # 9 units beside the boundary road
                x, y = polar(base_angle, r)
                px.append(x); py.append(y); ps.append(s); pk.append(j); parent.append(first + j - 1 if j > 0 else -1)
                kind.append(0); prad.append(r); pang.append(base_angle)
                self.spine_index[(s, r)] = first + j
            for k in range(cfg["house_rows"] + 1):
                r = cfg["house_radius_min"] - 30 + k * cfg["house_ring_step"]   # row street below row k
                prev = self.spine_index[(s, r)]
                for m, a in enumerate(arc_a):
                    ang = s * 60.0 + a
                    x, y = polar(ang, r - 6)
                    px.append(x); py.append(y); ps.append(s); pk.append(k); parent.append(prev)
                    kind.append(1); prad.append(r); pang.append(ang)
                    prev = len(px) - 1
        self.P = P = len(px)
        self.p_x = np.array(px); self.p_y = np.array(py)
        self.p_sector = np.array(ps); self.p_k = np.array(pk); self.p_parent = np.array(parent)
        self.p_kind = np.array(kind); self.p_radius = np.array(prad); self.p_angle = np.array(pang)
        self.p_state = np.zeros(P, dtype=int)   # 0 standing, 1 tilted, 2 fallen
        self.p_lamp_ok = np.ones(P, dtype=bool)
        self.p_lamp_on = np.ones(P, dtype=bool)
        self.s_health = np.ones(P)              # span from parent to pole i
        self.s_ice = np.zeros(P)
        self.s_online = np.ones(P, dtype=bool)
        self.n_span_ok = np.ones(P, dtype=bool)
        self.net_chain = np.ones(P, dtype=bool)
        # house -> nearest arc pole of its row street
        hp = np.zeros(N, dtype=int)
        for i in range(N):
            s, k = int(self.h_sector[i]), int(self.h_ring[i])
            cands = np.flatnonzero((self.p_sector == s) & (self.p_kind == 1) & (self.p_k == k))
            hp[i] = int(cands[np.argmin(np.abs(self.p_angle[cands] - self.h_angle[i]))])
        self.h_pole = hp

        # ---- grid nodes ----
        self.trunk_ok = True
        self.substation_ok = True
        self.tower_line_ok = True
        self.feeder_ok = np.ones(S, dtype=bool)
        self.rp_ok = np.ones(S, dtype=bool)
        self.feeder_online = np.ones(S, dtype=bool)
        self.solar_health = 1.0
        self.solar_kw = 0.0

        # ---- ups ----
        self.ups_center_kwh = cfg["ups_center_kwh"]
        self.ups_center_state = "STANDBY"
        self.ups_kwh = np.full(S, cfg["ups_sector_kwh"])
        self.ups_state = ["STANDBY"] * S
        self.ups_health = np.ones(S)

        # ---- reactor ----
        self.r_mode = "ONLINE"
        self.r_power_mw = 4.5
        self.r_setpoint_mw = 4.5
        self.r_core_temp = cfg["core_temp_nominal"]
        self.r_decay_mw = 0.0
        self.r_available_mw = 0.0
        self.r_pump_a = 1.0
        self.r_pump_b = 1.0
        self.r_hx = 1.0
        self.r_battery_h = cfg["pump_battery_h"]
        self.r_mode_ticks = 0
        self.r_emergency_ticks = 0
        self.r_shutdown_t = 0
        self.r_faults: list[str] = []
        self.r_link_ok = True
        self.r_flow = 1.0
        self.r_coolant_temp = 300.0

        # ---- balance ----
        self.available_kw = 0.0
        self.demand_kw = 0.0
        self.deficit_kw = 0.0
        self.shedding = 0
        self.surplus_ticks = 0
        self.max_shed_logged = 0
        self.shed_log_t = -1000
        self.comms_powered = True
        self.sector_demand_kw = np.zeros(S)
        self.sector_online = np.ones(S, dtype=bool)
        self.mine_powered = True
        self.mine_frac = 1.0
        self.road_heating_on = False
        self.storm_lighting = False
        self.infra_loads_kw = {}

        # ---- water ----
        self.water_tank_m3 = cfg["water_tank_m3"]
        self.water_plant_ok = True
        self.water_plant_heat = True
        self.water_plant_m3_h = 0.0
        self.intake_ok=True
        self.raw_intake_m3_h=self.brine_m3_h=0.0
        self.water_heat_available_kw=self.water_heat_used_kw=0.0
        self.ocean_withdrawn_m3=self.brine_returned_m3=0.0
        self.pump_station_ok = True
        self.water_main_ok = np.ones(S, dtype=bool)
        self.sector_water_m3 = np.zeros(S)
        self.water_flow_m3_h = 0.0
        self.utilities = UtilityNetwork(self)

        # ---- internet ----
        self.comms_ok = True
        self.tower_ok = True
        self.cabinet_ok = np.ones(S, dtype=bool)
        self.cabinet_ups_h = np.full(S, 2.0)
        self.cabinet_online = np.ones(S, dtype=bool)
        self.net_sector_online = np.ones(S, dtype=bool)
        self.uplink_ok = True
        self.packets_per_min = 0

        # ---- roads, walls, gates, waste, sewage ----
        self.road_integrity = np.full(S, 100.0)     # ring road segment per sector
        self.road_icy = False
        self.gate_state = ["OPEN"] * S              # gate g sits in the wall at boundary angle g*60
        self.gate_ok = np.ones(S, dtype=bool)
        self.gate_open_frac = np.ones(S)            # 1 open, 0 closed, animated
        self.lockdown_ticks = np.zeros(S, dtype=int)
        self.waste_level = self.rng.uniform(0.2, 0.6, S)
        self.sludge_store = self.rng.uniform(0.1, 0.4, S)
        self.sanitary = np.full(S, 100.0)
        self.sector_dark = np.zeros(S, dtype=bool)
        R = cfg["ring_road_radius"]
        self.rovers = [
            Rover("garbage", "garbage", *polar(15.0, R), speed=cfg["rover_speed"]),
            Rover("sludge", "sludge", *polar(195.0, R), speed=cfg["rover_speed"]),
            Rover("engineer", "repair", *polar(105.0, R), speed=cfg["rover_speed"] * 1.3),
            Rover("engineer-2", "repair", *polar(345.0, R), speed=cfg["rover_speed"] * 1.3),
            Rover("plumber", "plumber", *polar(285.0, R), speed=cfg["rover_speed"] * 1.3),
        ]
        self.traffic = make_traffic(self.cfg)
        self.cargo = {'phase':'WAIT','progress':0.0,'loaded':0,'completed':0,'truck':0}
        self.dish_ok=True
        self.mobile_online=True
        self.waste_station_level = 0.0

        # ---- people / threats ----
        self.xeno_markers: list[dict] = []          # agents: approach -> breach -> hunt -> attack -> retreat
        self.marines_active = 0
        self.nest_alert = 0
        self.wall_breach = [None] * S               # angle of the broken wall panel per sector, or None
        self.squad = {"state": "BASE", "x": 0.0, "y": 60.0, "route": [], "sector": -1, "timer": 0}
        W = cfg["walkers"]
        self.w_home = self.rng.integers(0, N, W)
        self.w_state = np.zeros(W, dtype=int)       # 0 home, 1 to hub, 2 at hub, 3 to home
        self.w_prog = np.zeros(W)
        self.w_timer = self.rng.integers(30, 600, W)
        self.w_x = self.h_x[self.w_home].copy()
        self.w_y = self.h_y[self.w_home].copy()

        # ---- finance ----
        self.sector_budget = np.full(S, cfg["sector_budget"])
        self.colony_budget = cfg["colony_budget"]
        self.cost_records: list[dict] = []
        self.month = 1
        self.month_income = np.zeros(S)
        self.month_expense = np.zeros(S)
        self.colony_month_expense = 0.0
        self.colony_month_income = 0.0
        self.last_report: Optional[dict] = None
        self.unfunded_total = 0.0

        # ---- environment ----
        self.t_out = cfg["t_mean"]
        self.wind = 8.0
        self.precip = "none"
        self.daylight = 0.0
        self.dust = 0.2
        self.storm_ticks = 0
        self.synoptic = 0.0
        self.visibility = 100.0

        # ---- attractor page: colony trajectory samples ----
        self.attr_fast = []     # every 10 ticks, last 5 days
        self.attr_slow = []     # every 6 hours, last 60 days
        self.last_levy = 0.0
        self.levy_total = 0.0
        self.last_sector_transfer = 0.0

    # ---- pickling: drop the lock, recreate it on load ----
    def __getstate__(self):
        d = self.__dict__.copy()
        d.pop("lock", None)
        d.pop("bridge", None)
        return d

    def __setstate__(self, d):
        self.__dict__.update(d)
        self.lock = threading.Lock()

    # ---- helpers ----
    def log(self, level, text):
        self.events.appendleft({"t": self.t, "level": level, "text": text})

    def time_str(self):
        c = self.cfg
        day = self.t // c["ticks_per_day"] % c["days_per_month"] + 1
        hour = self.t // 60 % 24
        minute = self.t % 60
        return f"M{self.month} D{day:02d} {hour:02d}:{minute:02d}"

    def is_night(self):
        h = self.t // 60 % 24
        return h >= 22 or h < 6

    def open_issue(self, kind, target, sector, cause, cost_key, pos, severity="warning"):
        for i in self.issues:
            if i.target == target and i.kind == kind and i.status != "resolved":
                return i
        cost, payer, dur = COSTS[cost_key]
        iss = Issue(self.next_issue_id, kind, target, sector, cause, float(cost), payer, dur, pos, self.t,
                    severity=severity)
        self.next_issue_id += 1
        self.issues.append(iss)
        self.log("ALARM" if severity == "critical" else "WARN", f"{kind} at {target} ({cause})")
        return iss

    def open_issues(self):
        return [i for i in self.issues if i.status != "resolved"]


# ------------------------------------------------------------------------------------
# Environment
# ------------------------------------------------------------------------------------

def env_step(w: World):
    c = w.cfg
    hour = (w.t % c["ticks_per_day"]) / 60.0
    w.synoptic += w.rng.normal(0, 0.15) - 0.01 * w.synoptic
    w.synoptic = clamp(w.synoptic, -12, 12)
    base = c["t_mean"] - c["t_daily_amp"] * math.cos(2 * math.pi * (hour - 4) / 24)
    if w.storm_ticks > 0:
        w.storm_ticks -= 1
        w.wind += (w.rng.uniform(*c["storm_wind"]) - w.wind) * 0.1
        w.precip = "snow"
        w.visibility = 4.0
        if w.storm_ticks == 0:
            w.log("INFO", "Storm is over")
            w.storm_lighting = False
    else:
        if w.rng.random() < c["storm_prob_per_tick"]:
            w.storm_ticks = int(w.rng.integers(*c["storm_len_ticks"]))
            w.log("WARN", f"Snowstorm begins, {w.storm_ticks // 60} h")
            w.storm_lighting = True
        w.wind += (w.rng.uniform(*c["calm_wind"]) - w.wind) * 0.05
        w.precip = "snow" if w.rng.random() < 0.002 else ("none" if w.precip == "none" or w.rng.random() < 0.01 else w.precip)
        w.visibility = 60.0 if w.precip == "snow" else 100.0
    storm_drop = 10.0 if w.storm_ticks > 0 else 0.0
    w.t_out = base + w.synoptic - storm_drop + w.rng.normal(0, 0.05)
    w.daylight = c["daylight_max"] * max(0.0, math.sin(math.pi * (hour - 6) / 12)) * (0.2 if w.storm_ticks > 0 else 1.0)
    w.dust = clamp(w.dust + (0.02 * w.wind / 10 - 0.02) * 0.05 + w.rng.normal(0, 0.01), 0.05, 0.95)
    w.road_icy = w.precip == "snow" or w.storm_ticks > 0
    if w.precip == "snow":
        w.s_ice = np.minimum(1.0, w.s_ice + 0.002)
    elif w.t_out > 0:
        w.s_ice = np.maximum(0.0, w.s_ice - 0.005)


# ------------------------------------------------------------------------------------
# Reactor
# ------------------------------------------------------------------------------------

def reactor_step(w: World):
    c = w.cfg
    nom = c["reactor_gross_mw"]
    ramp = c["ramp_frac_per_min"] * nom
    flow = (0.5 * (w.r_pump_a > 0.2) + 0.5 * (w.r_pump_b > 0.2)) * w.r_hx
    w.r_mode_ticks += 1

    if w.r_mode in ("ONLINE", "RUNBACK"):
        if w.rng.random() < c["p_pump_wear"]:
            which = "pump_b" if w.r_pump_b > 0.2 else "pump_a"
            setattr(w, "r_" + which, 0.1)
            w.open_issue("pump_trip", f"reactor:{which}", -1, "wear", "pump", c["reactor_pos"], "critical")
            w.log("ALARM", f"Reactor {which.upper()} tripped")

    if w.r_mode == "ONLINE" and flow < 0.75:
        w.r_mode = "RUNBACK"
        w.r_mode_ticks = 0
        w.log("ALARM", "Reactor RUNBACK: coolant flow reduced")
    if w.r_mode == "RUNBACK" and flow >= 0.99:
        w.r_mode = "ONLINE"
        w.log("INFO", "Reactor back ONLINE")

    if w.r_mode in ("ONLINE", "RUNBACK"):
        # the operator follows the load: generation tracks demand plus a spinning reserve
        # during load shedding the operator asks for everything the plant can give
        wanted = nom if w.shedding > 0 else w.demand_kw / 1000.0 + c["reactor_self_mw"] + 0.15 * c["heat_export_mw"] + c["reserve_mw"]
        w.r_setpoint_mw = clamp(wanted, 0.2 * nom, nom)
        cap = nom * (1.0 if w.r_mode == "ONLINE" else min(1.0, flow / 0.5) * 0.5)
        target = min(w.r_setpoint_mw, cap)
        w.r_power_mw += clamp(target - w.r_power_mw, -ramp, ramp) + w.rng.normal(0, 0.004)
        w.r_power_mw = clamp(w.r_power_mw, 0.0, nom)
        w.r_decay_mw = 0.0
        thermal = w.r_power_mw / 0.3
        t_eq = 300.0 + 480.0 * (thermal / 20.0) / max(flow, 0.05)
        w.r_core_temp += (t_eq - w.r_core_temp) * 0.05 + w.rng.normal(0, 0.6)
        w.r_core_temp = clamp(w.r_core_temp, 300, 1400)
        w.r_available_mw = max(0.0, min(cap, w.r_power_mw + ramp) - c["reactor_self_mw"] - 0.15 * c["heat_export_mw"])
        w.water_plant_heat = True
        if flow < 0.3 or w.r_core_temp > c["core_temp_limit"]:
            reactor_scram(w, "protection: temperature/flow")
    elif w.r_mode in ("SCRAM", "COOLING", "EMERGENCY"):
        w.r_power_mw = 0.0
        w.r_available_mw = 0.0
        w.water_plant_heat = False
        t_since = max(1, (w.t - w.r_shutdown_t) * 60)
        w.r_decay_mw = 0.066 * 20.0 * (t_since ** -0.2 - (t_since + 3.0e7) ** -0.2)
        pumps_powered = w.trunk_ok and w.substation_ok
        if not pumps_powered:
            w.r_battery_h = max(0.0, w.r_battery_h - 1 / 60)
        else:
            w.r_battery_h = min(c["pump_battery_h"], w.r_battery_h + 1 / 240)
        flow_now = flow if (pumps_powered or w.r_battery_h > 0) else 0.02 * w.r_hx
        t_eq = 300.0 + 480.0 * (w.r_decay_mw / 20.0) / max(flow_now, 0.002)
        w.r_core_temp += (t_eq - w.r_core_temp) * 0.02
        w.r_core_temp = clamp(w.r_core_temp, 300, 1400)
        if w.r_mode == "SCRAM" and w.r_mode_ticks > 30:
            w.r_mode = "COOLING"
            w.r_mode_ticks = 0
        if w.r_mode == "COOLING":
            if flow_now < 0.05 or w.r_core_temp > c["core_temp_limit"]:
                w.r_mode = "EMERGENCY"
                w.r_mode_ticks = 0
                w.log("ALARM", "Reactor EMERGENCY: heat removal lost")
            elif w.r_core_temp < 400 and w.r_hx > 0.7 and flow >= 0.5 and pumps_powered and w.r_mode_ticks > 360:
                w.r_mode = "STARTING"
                w.r_mode_ticks = 0
                w.log("INFO", "Reactor STARTING")
        if w.r_mode == "EMERGENCY":
            if w.r_core_temp > c["core_temp_limit"]:
                w.r_emergency_ticks += 1
                if w.r_emergency_ticks > 240:
                    w.r_mode = "CORE_DAMAGE"
                    w.log("ALARM", "CORE DAMAGE. Simulation over.")
                    w.finished = True
                    w.finish_reason = "Reactor core damage"
            else:
                w.r_emergency_ticks = 0
            if flow_now >= 0.4 and w.r_core_temp < 900:
                w.r_mode = "COOLING"
                w.r_mode_ticks = 0
                w.log("INFO", "Reactor heat removal restored, COOLING")
    elif w.r_mode == "STARTING":
        w.r_power_mw += ramp * 0.5
        w.r_available_mw = max(0.0, w.r_power_mw - c["reactor_self_mw"])
        w.water_plant_heat = w.r_power_mw > 2.0
        w.r_core_temp += (c["core_temp_nominal"] - w.r_core_temp) * 0.02
        if w.r_power_mw >= nom * 0.5:
            w.r_mode = "ONLINE"
            w.r_mode_ticks = 0
            w.log("INFO", "Reactor ONLINE")
    elif w.r_mode == "CORE_DAMAGE":
        w.r_available_mw = 0.0
    w.r_flow = flow
    w.r_coolant_temp = 300.0 + (w.r_core_temp - 300.0) * 0.35
    w.r_faults = [f for f, ok in (("PUMP_A_TRIP", w.r_pump_a > 0.2), ("PUMP_B_TRIP", w.r_pump_b > 0.2),
                                  ("HEAT_EXCHANGER_DAMAGE", w.r_hx > 0.7)) if not ok]


def reactor_scram(w: World, reason):
    if w.r_mode in ("ONLINE", "RUNBACK", "STARTING"):
        w.r_mode = "SCRAM"
        w.r_mode_ticks = 0
        w.r_shutdown_t = w.t
        w.r_power_mw = 0.0
        w.log("ALARM", f"Reactor SCRAM ({reason})")


# ------------------------------------------------------------------------------------
# Grid, balance, ups
# ------------------------------------------------------------------------------------

def grid_rebuild(w: World):
    """Walk the pole tree: a pole is online when its parent is online and the span to it is intact."""
    fallen = w.p_state == 2
    parent = w.p_parent
    parent_fallen = np.where(parent >= 0, fallen[np.maximum(parent, 0)], False)
    span_ok = (w.s_health >= 0.2) & ~fallen & ~parent_fallen
    net_ok = w.n_span_ok & ~fallen & ~parent_fallen
    sector_feed = w.trunk_ok & w.substation_ok & w.feeder_ok & w.rp_ok
    w.feeder_online = sector_feed
    online = np.zeros(w.P, dtype=bool)
    net = np.zeros(w.P, dtype=bool)
    for i in range(w.P):           # parents always precede children in the arrays
        p = parent[i]
        up = sector_feed[w.p_sector[i]] if p < 0 else online[p]
        upn = True if p < 0 else net[p]
        online[i] = up and span_ok[i]
        net[i] = upn and net_ok[i]
    w.s_online = online
    w.net_chain = net


def houses_decide(w: World):
    """House brains. Houses with a fresh external controller (runtime over MQTT) use its decisions;
    the rest run the built-in thermostat. This is where libhopevm plugs in."""
    c = w.cfg
    ext = (w.t - w.h_ctrl_t) < 15
    target = np.full(w.N, c["comfort_c"])
    target[w.h_on_ups | (w.h_limit_w > 0)] = c["eco_c"]
    target[(w.h_limit_w > 0) & (w.h_limit_w <= c["limit_level5_w"])] = c["antifreeze_c"]
    on = w.h_heater_on.copy()
    on[w.h_t_in < target - 0.5] = True
    on[w.h_t_in > target + 0.5] = False
    valve = ~w.h_burst
    appl = np.ones(w.N, dtype=bool)
    # external decisions override
    target = np.where(ext, w.h_ctrl_target, target)
    on = np.where(ext, w.h_ctrl_heater, on)
    valve = np.where(ext, w.h_ctrl_valve & ~w.h_burst, valve)
    appl = np.where(ext, w.h_ctrl_appl, appl)
    # hard limits the grid enforces regardless of the program: heater cannot exceed the limit budget
    w.h_target = target
    w.h_heater_on = on
    w.h_valve_open = valve
    w.h_appliances_on = appl
    w.h_ext = ext


def houses_demand(w: World):
    c = w.cfg
    night = w.is_night()
    base = w.h_base_w * (0.6 if night else 1.0) + w.rng.uniform(-50, 50, w.N)
    base = np.maximum(base, 80.0)
    base = np.where(w.h_appliances_on, base, 100.0)          # program switched appliances off: fridge only
    heater = np.where(w.h_heater_on, w.h_heater_w, 0.0)
    aeration = np.where(w.h_aeration_ok, c["aeration_w"], 0.0)
    want = base + heater + aeration
    limit = w.h_limit_w
    lim = np.where(limit > 0, limit, 1e9)
    essential = aeration + 100.0
    heat_alloc = np.minimum(heater, np.maximum(0.0, lim - essential))
    rest = np.minimum(base - 100.0, np.maximum(0.0, lim - essential - heat_alloc))
    draw = np.minimum(essential + heat_alloc + rest, want)
    return draw, heat_alloc


def power_step(w: World):
    c = w.cfg
    S = w.S
    grid_rebuild(w)
    w.solar_kw = c["solar_peak_kw"] * w.daylight * (1 - w.dust) * w.solar_health * (1 + w.rng.normal(0, 0.03))
    w.solar_kw = max(0.0, w.solar_kw)
    reactor_kw = w.r_available_mw * 1000.0 if (w.trunk_ok and w.substation_ok) else 0.0
    available = reactor_kw + (w.solar_kw if w.substation_ok else 0.0)

    houses_decide(w)
    house_pole_online = w.s_online[w.h_pole] & w.h_wiring_ok
    draw, heat_alloc = houses_demand(w)
    infra = {
        "mine": c["mine_kw"] * w.mine_frac,
        "water_plant": c["water_plant_kw"] if w.water_plant_ok else 0.0,
        "waste_storage": c["waste_storage_kw"],
        "ops_center": c["ops_center_kw"],
        "comms": c["comms_kw"] + (c["comms_kw"] * 0.5 if w.tower_line_ok else 0.0),
        "cabinets": c["cabinet_kw"] * S,
        "gates": c["gate_kw"] * S,
        "lamps": 0.0,
        "road_heating": c["road_heating_kw"] if (w.road_icy and w.shedding < 2) else 0.0,
        "pump_station": c["pump_station_kw"],
        "ups_charge": 0.0,
    }
    lamps_on = w.p_lamp_ok & w.s_online & (w.shedding < 4) & (w.is_night() or w.storm_ticks > 0 or w.precip == "snow")
    lamp_kw = c["lamp_kw"] * (1.2 if w.storm_lighting else 1.0)
    infra["lamps"] = float(lamps_on.sum()) * lamp_kw
    w.p_lamp_on = lamps_on
    w.road_heating_on = infra["road_heating"] > 0
    need = np.maximum(0.0, c["ups_sector_kwh"] - w.ups_kwh)
    charge_kw = np.where((need > 0) & w.feeder_online & (w.shedding < 2), c["ups_charge_kw"], 0.0)
    center_need = c["ups_center_kwh"] - w.ups_center_kwh
    center_charge = c["ups_charge_kw"] if (center_need > 0 and w.substation_ok and w.trunk_ok and w.shedding < 2) else 0.0
    infra["ups_charge"] = float(charge_kw.sum()) + center_charge

    grid_house_draw = np.where(house_pole_online, draw, 0.0)
    sector_draw = np.bincount(w.h_sector, weights=grid_house_draw, minlength=S) / 1000.0
    demand = float(sector_draw.sum()) + sum(infra.values())
    w.sector_demand_kw = sector_draw

    deficit = max(0.0, demand - available)
    if deficit > 0 and available > 0:
        if w.shedding < 8:
            w.shedding += 1
            if w.shedding > w.max_shed_logged or w.t - w.shed_log_t > 240:
                w.log("WARN", f"Load shedding level {w.shedding}, deficit {deficit:.0f} kW")
                w.max_shed_logged = w.shedding
                w.shed_log_t = w.t
        w.surplus_ticks = 0
    elif available > 0 and demand < available * 0.9:
        w.surplus_ticks += 1
        if w.surplus_ticks > 30 and w.shedding > 0:
            w.shedding -= 1
            w.surplus_ticks = 0
            if w.shedding == 0:
                w.log("INFO", "Load shedding ended")
                w.max_shed_logged = 0
    if available <= 0.0:
        w.shedding = 8
    reactor_up = w.r_mode not in ("SCRAM", "COOLING", "EMERGENCY", "CORE_DAMAGE")
    w.mine_frac = (1.0 if w.shedding < 6 else 0.5 if w.shedding < 7 else 0.0) if (available > 0 and reactor_up) else 0.0
    w.mine_powered = w.mine_frac > 0

    limit = np.zeros(w.N)
    if w.shedding >= 3:
        limit[:] = c["limit_level3_w"]
    if w.shedding >= 5:
        limit[:] = c["limit_level5_w"]
    shed_sectors = np.zeros(S, dtype=bool)
    if w.shedding >= 8 and available > 0:
        excess = deficit
        for s in range(S - 1, -1, -1):
            if excess <= 0:
                break
            shed_sectors[s] = True
            excess -= float(sector_draw[s])
    sector_feed = w.feeder_online & ~shed_sectors
    w.sector_online = sector_feed

    house_feed_ok = house_pole_online & sector_feed[w.h_sector]
    on_ups = np.zeros(w.N, dtype=bool)
    powered = house_feed_ok.copy()
    for s in range(S):
        mask = w.h_sector == s
        if sector_feed[s]:
            w.ups_kwh[s] = min(c["ups_sector_kwh"], w.ups_kwh[s] + charge_kw[s] / 60.0)
            w.ups_state[s] = "CHARGING" if charge_kw[s] > 0 else "STANDBY"
        else:
            if w.ups_kwh[s] > 0 and w.ups_health[s] > 0.2:
                m = mask & house_pole_online & ~house_feed_ok
                limit[m] = np.minimum(np.where(limit[m] > 0, limit[m], 1e9), c["limit_level3_w"])
                sup = min(c["ups_sector_kw"], float(np.minimum(draw[m], c["limit_level3_w"]).sum()) / 1000.0)
                w.ups_kwh[s] = max(0.0, w.ups_kwh[s] - sup / 60.0)
                powered[m] = True
                on_ups[m] = True
                w.ups_state[s] = "DISCHARGING"
                if w.ups_kwh[s] <= 0:
                    w.ups_state[s] = "DEPLETED"
                    w.log("ALARM", f"Sector {s + 1} UPS depleted")
            else:
                w.ups_state[s] = "DEPLETED" if w.ups_kwh[s] <= 0 else "FAULT"
    if w.substation_ok and w.trunk_ok and available > 0:
        w.ups_center_kwh = min(c["ups_center_kwh"], w.ups_center_kwh + center_charge / 60.0)
        w.ups_center_state = "CHARGING" if center_charge > 0 else "STANDBY"
        w.comms_powered = True
        w.pump_station_ok = True
    else:
        if w.ups_center_kwh > 0:
            w.ups_center_kwh = max(0.0, w.ups_center_kwh - (c["ops_center_kw"] + c["comms_kw"] + c["pump_station_kw"]) / 60.0)
            w.ups_center_state = "DISCHARGING"
            w.comms_powered = True
            w.pump_station_ok = True
        else:
            w.ups_center_state = "DEPLETED"
            w.comms_powered = False
            w.pump_station_ok = False

    real_draw = np.where(powered, draw, 0.0)
    heat = np.where(powered, heat_alloc, 0.0)
    w.h_power_ok = powered
    w.h_on_ups = on_ups
    w.h_limit_w = limit
    w.h_draw_w = real_draw
    w.h_heat_w = heat
    kwh = real_draw / 1000.0 / 60.0
    w.h_meter_kwh += kwh
    w.h_meter_month += kwh
    w.h_meter_day += kwh
    w.available_kw = available
    w.demand_kw = demand
    w.deficit_kw = deficit
    # statistics by house program (external programs by name, the rest as "thermostat")
    names = [p if (p and ext_i) else "thermostat" for p, ext_i in zip(w.h_program, getattr(w, "h_ext", np.zeros(w.N, dtype=bool)))]
    for name in set(names):
        idx = np.fromiter((k for k, n in enumerate(names) if n == name), dtype=int)
        st = w.prog_stats.setdefault(name, {"kwh": 0.0, "house_ticks": 0, "cold_ticks": 0, "t_sum": 0.0, "cost": 0.0})
        st["kwh"] += float(kwh[idx].sum())
        st["house_ticks"] += int(len(idx))
        st["cold_ticks"] += int((w.h_t_in[idx] < 16.0).sum())
        st["t_sum"] += float(w.h_t_in[idx].sum())
        st["cost"] += float(kwh[idx].sum()) * c["tariff_kwh"]
    w.infra_loads_kw = {k: round(v, 1) for k, v in infra.items()}
    lamps_by_sector = np.bincount(w.p_sector, weights=w.p_lamp_on.astype(float), minlength=S)
    w.sector_dark = (lamps_by_sector < 6) & np.array([w.is_night()] * S)
    if w.mine_frac > 0:
        w.colony_budget += c["mine_income_per_tick"] * w.mine_frac
        w.colony_month_income += c["mine_income_per_tick"] * w.mine_frac


# ------------------------------------------------------------------------------------
# Houses: thermal, pipes, water
# ------------------------------------------------------------------------------------

def houses_step(w: World):
    c = w.cfg
    dt = c["tick_seconds"]
    ua_eff = w.h_ua * (1.0 + 0.006 * w.wind)
    q_loss = ua_eff * (w.h_t_in - w.t_out)
    q_int = (w.h_draw_w - w.h_heat_w) * 0.8 + w.h_residents * 80.0
    w.h_t_in += (w.h_heat_w + q_int - q_loss) * dt / w.h_cap
    cold = w.h_t_in < 0.0
    w.h_frozen = np.where(cold, w.h_frozen + 1, 0)
    w.h_pipes_ok[(w.h_t_in > 3.0) & ~w.h_burst] = True
    newly_frozen = (w.h_frozen == c["freeze_ticks_to_frozen"]) & w.h_pipes_ok
    for i in np.flatnonzero(newly_frozen):
        w.h_pipes_ok[i] = False
        w.log("WARN", f"House {i + 1}: pipes frozen")
    burst_now = (w.h_frozen == c["freeze_ticks_to_frozen"] + c["frozen_ticks_to_burst"]) & ~w.h_burst
    for i in np.flatnonzero(burst_now):
        w.h_burst[i] = True
        cost_mul = 0.5 if not w.h_valve_open[i] else 1.0
        iss = w.open_issue("pipes_burst", f"house:{i}", int(w.h_sector[i]), "freeze", "pipes",
                           (float(w.h_x[i]), float(w.h_y[i])), "critical")
        iss.cost *= cost_mul
    hydraulic_step(w)


def water_step(w: World):
    c=w.cfg;dt=float(c['tick_seconds'])
    electric=bool(w.trunk_ok and w.substation_ok and w.r_available_mw>0 and w.shedding<7)
    w.water_plant_ok=bool(w.water_plant_heat and electric and w.intake_ok)
    need=max(0,c['water_tank_m3']-w.water_tank_m3)
    desired=c['water_plant_m3_h']*clamp(need/60,.15,1.0) if need>0 else 0.0
    # kWh per m3: warm ice to 0 C, latent heat, then temper water to 5 C.
    # Saline source is conservatively treated as frozen whenever ambient < -2 C.
    ice=max(0,-w.t_out) if w.t_out<-2 else 0
    melt_kwh_m3=(2.1*ice+(334 if ice else 0)+4.18*5)/3.6
    w.water_heat_available_kw=min(c['water_heat_kw'],max(0,w.r_power_mw*(1/.3-1)*1000*.18)) if w.water_plant_ok else 0.0
    raw_limit=w.water_heat_available_kw/max(melt_kwh_m3,1e-9)
    clean_rate=min(desired,raw_limit*c['water_recovery']) if w.water_plant_ok else 0.0
    produced=min(need,clean_rate*dt/3600)
    raw=produced/c['water_recovery'];reject=raw-produced
    w.water_plant_m3_h=produced*3600/dt
    w.raw_intake_m3_h=raw*3600/dt;w.brine_m3_h=reject*3600/dt
    w.water_heat_used_kw=w.raw_intake_m3_h*melt_kwh_m3
    w.water_tank_m3+=produced;w.ocean_withdrawn_m3+=raw;w.brine_returned_m3+=reject
    if w.water_tank_m3<=0 and w.t%60==0:w.log('ALARM','Water tank empty')


# ------------------------------------------------------------------------------------
# Browser UI (served at /). Plain canvas, polls /state four times per second.
# ------------------------------------------------------------------------------------

HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Hadley's Hope</title>
<style>
  :root { --bg:#0f1115; --panel:#171a21; --line:#2a2f3a; --text:#d9dde6; --dim:#8a93a6; --ok:#5ec07a; --warn:#e0b04a; --bad:#e2574d; --blue:#5aa9ff; --cyan:#4fd1c5; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font:13px/1.35 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; display:flex; height:100vh; overflow:hidden; }
  #map { flex:1 1 auto; position:relative; }
  canvas { display:block; width:100%; height:100%; }
  #side { width:490px; flex:0 0 490px; background:var(--panel); border-left:1px solid var(--line); overflow-y:auto; padding:10px 12px; }
  h1 { font-size:15px; margin:0 0 6px; } h2 { font-size:12px; color:var(--dim); text-transform:uppercase; letter-spacing:.06em; margin:14px 0 6px; }
  .row { display:flex; gap:6px; flex-wrap:wrap; align-items:center; }
  button { background:#232835; color:var(--text); border:1px solid var(--line); border-radius:6px; padding:4px 8px; cursor:pointer; font-size:12px; }
  button:hover { background:#2d3444; } button.on { border-color:var(--blue); color:var(--blue); }
  a.tab { color:var(--text); text-decoration:none; padding:4px 10px; border:1px solid var(--line); border-radius:6px; background:#1c212c; font-size:12px; } a.tab.on { border-color:var(--blue); color:var(--blue); } a.tab:hover { background:#2d3444; }
  .kpi { display:grid; grid-template-columns:1fr 1fr; gap:6px; }
  .card { background:#1f2430; border:1px solid var(--line); border-radius:8px; padding:6px 8px; }
  .card .v { font-size:17px; font-weight:600; } .card .l { color:var(--dim); font-size:11px; }
  table { width:100%; border-collapse:collapse; font-size:11.5px; } th,td { padding:2px 3px; text-align:right; border-bottom:1px solid var(--line); white-space:nowrap; } th { color:var(--dim); font-weight:500; } td:first-child, th:first-child { text-align:left; }
  .ok { color:var(--ok); } .warn { color:var(--warn); } .bad { color:var(--bad); } .dim { color:var(--dim); }
  #log { font-family: ui-monospace, Menlo, Consolas, monospace; font-size:11px; max-height:230px; overflow-y:auto; background:#0f1115; border:1px solid var(--line); border-radius:6px; padding:6px; }
  #log div { padding:1px 0; } .ALARM { color:var(--bad); } .WARN { color:var(--warn); } .INFO { color:var(--dim); }
  #legend { position:absolute; left:10px; bottom:10px; background:rgba(23,26,33,.9); border:1px solid var(--line); border-radius:8px; padding:8px 10px; font-size:11px; color:var(--dim); line-height:1.5; }
  #legend b { color:var(--text); }
  #banner { position:absolute; left:10px; top:10px; background:rgba(23,26,33,.9); border:1px solid var(--line); border-radius:8px; padding:6px 10px; font-size:13px; }
  #finished { position:absolute; inset:0; display:none; align-items:center; justify-content:center; background:rgba(0,0,0,.6); font-size:28px; color:var(--bad); }
  pre { white-space:pre-wrap; font-size:11px; background:#0f1115; padding:6px; border-radius:6px; border:1px solid var(--line); }
  @media (max-width: 900px) {
    body { flex-direction:column; overflow:auto; height:auto; }
    #map { flex:none; height:62vh; min-height:360px; }
    #side { width:100%; flex:none; border-left:none; border-top:1px solid var(--line); }
    #legend { display:none; }
    #banner { font-size:11px; }
  }
</style></head>
<body>
<div id="map"><canvas id="c"></canvas>
  <div id="banner">connecting...</div>
  <div id="legend"><b>Map</b>: house colour = indoor temperature (blue cold, orange warm), red frame = no power, blue frame = on sector UPS, x = burst pipes.<br>
  Yellow lines = power (moving dashes = energised), blue = water, cyan = internet cable, cyan dots = packets, red dot = packet with no uplink.<br>
  Poles: dot; orange = tilted, red x = fallen; glow = street lamp on. Gates on the ring road: green open, grey closed, red lockdown.<br>
  Rovers: G garbage, S sludge hauler, E engineers, P plumber. Red diamonds = xenomorphs. ! = open issue.</div>
  <div id="finished"></div>
  <div id="tip" style="position:absolute;display:none;background:rgba(23,26,33,.95);border:1px solid var(--line);border-radius:6px;padding:6px 8px;font-size:11px;pointer-events:none"></div>
</div>
<div id="side">
  <div class="row" style="margin-bottom:8px"><a href="/" class="tab">3D planet</a><a href="/flat" class="tab on">flat map</a><a href="/bus" class="tab">bus and programs</a><a href="/house" class="tab">house</a><a href="/graph" class="tab">systems</a><a href="/attractors" class="tab">Attractors</a></div>
  <h1>Hadley's Hope, LV-426</h1>
  <div class="row"><span id="time" style="font-weight:600;min-width:120px"></span>
    <button id="pause">Pause</button>
    <span class="dim">speed</span><button data-s="1">1x</button><button data-s="20">20x</button><button data-s="120">120x</button><button data-s="600">600x</button></div>
  <h2>Inject</h2>
  <div class="row">
    <button data-i="span">break span</button><button data-i="pole">fell pole</button><button data-i="xeno">xenomorphs</button>
    <button data-i="storm">storm</button><button data-i="trunk">cut trunk</button><button data-i="pump">pump trip</button>
    <button data-i="marines">marines fire</button><button data-i="scram">SCRAM</button><button data-i="road">break road</button><button data-i="money">+50k cr</button>
  </div>
  <h2>Colony</h2>
  <div class="kpi" id="kpi"></div>
  <h2>Reactor and power</h2>
  <div id="reactor" class="card"></div>
  <h2>Sectors</h2>
  <table id="sectors"><thead><tr><th>#</th><th>cr</th><th>kW</th><th>avg C</th><th>min C</th><th>pwr</th><th>water</th><th>net</th><th>UPS</th><th>waste</th><th>san</th><th>gate</th><th>road</th></tr></thead><tbody></tbody></table>
  <h2>Open issues <span id="nissues" class="dim"></span></h2>
  <div id="issues" class="dim" style="font-size:11px;max-height:120px;overflow-y:auto"></div>
  <h2>Events</h2>
  <div id="log"></div>
  <h2>Last monthly report</h2>
  <pre id="report">no month closed yet</pre>
</div>
<script>
const cv = document.getElementById('c'), ctx = cv.getContext('2d');
let G = null, S = null, packetsSeen = new Map(), lastFetch = 0, animT = 0;
const ADMIN = new URLSearchParams(location.search).get('admin') || localStorage.getItem('hh_admin') || ''; if(ADMIN) localStorage.setItem('hh_admin', ADMIN);
const post = async (o) => { const r = await fetch('/cmd', {method:'POST', body: JSON.stringify({...o, token: ADMIN})}); if(r.status===403 && !window.__ro){ window.__ro=true; alert('View only. Open the page as /?admin=TOKEN to control the colony.'); } };
document.getElementById('pause').onclick = () => post({cmd:'pause'});
document.querySelectorAll('button[data-s]').forEach(b => b.onclick = () => post({cmd:'speed', value:+b.dataset.s}));
document.querySelectorAll('button[data-i]').forEach(b => b.onclick = () => post({cmd:'inject', value:b.dataset.i}));

async function loadGeom(){ G = await (await fetch('/geometry')).json(); }
async function poll(){
  try { const s = await (await fetch('/state')).json(); S = s; lastFetch = performance.now(); renderSide(s); }
  catch(e) { document.getElementById('banner').textContent = 'no connection'; }
  setTimeout(poll, 250);
}

// ---------- coordinate transform ----------
let sc = 1, ox = 0, oy = 0;
function fit(){
  const W = cv.clientWidth, H = cv.clientHeight; cv.width = W * devicePixelRatio; cv.height = H * devicePixelRatio;
  const x0=-1620, x1=800, y0=-800, y1=800;
  sc = Math.min(W/(x1-x0), H/(y1-y0)); ox = W/2 - sc*(x0+x1)/2; oy = H/2 - sc*(y0+y1)/2;
}
const X = x => ox + sc*x, Y = y => oy + sc*y;
function polar(a, r){ const t = a*Math.PI/180; return [r*Math.cos(t), r*Math.sin(t)]; }

// ---------- colours ----------
function tempColor(t){ // -60..25 -> blue..white..orange
  const u = Math.max(0, Math.min(1, (t + 40) / 65));
  if (u < 0.6) { const k = u/0.6; return `rgb(${Math.round(60+150*k)},${Math.round(110+120*k)},${Math.round(230-20*k)})`; }
  const k = (u-0.6)/0.4; return `rgb(${Math.round(210+45*k)},${Math.round(230-90*k)},${Math.round(210-150*k)})`;
}
const modeColor = {ONLINE:'#5ec07a', RUNBACK:'#e0b04a', SCRAM:'#e2574d', COOLING:'#e2574d', EMERGENCY:'#ff2a2a', CORE_DAMAGE:'#ff0000', STARTING:'#5aa9ff'};

// ---------- drawing helpers ----------
function line(x0,y0,x1,y1,color,w,dash,off){ ctx.beginPath(); ctx.strokeStyle=color; ctx.lineWidth=w; ctx.setLineDash(dash||[]); ctx.lineDashOffset=off||0; ctx.moveTo(X(x0),Y(y0)); ctx.lineTo(X(x1),Y(y1)); ctx.stroke(); ctx.setLineDash([]); }
function flow(x0,y0,x1,y1,color,w,on,speed){ line(x0,y0,x1,y1,on?color:'#3a3f4a',w); if(on) line(x0,y0,x1,y1,'#ffffff',Math.max(1,w-1),[3,9],-animT*speed); }
function dot(x,y,r,color){ ctx.beginPath(); ctx.fillStyle=color; ctx.arc(X(x),Y(y),r,0,Math.PI*2); ctx.fill(); }
function text(x,y,s,color,size,align){ ctx.fillStyle=color||'#d9dde6'; ctx.font=`${size||11}px sans-serif`; ctx.textAlign=align||'center'; ctx.fillText(s,X(x),Y(y)); }
function box(x,y,w,h,fill,stroke,label,sub){ ctx.fillStyle=fill; ctx.strokeStyle=stroke; ctx.lineWidth=1.2; ctx.beginPath(); if(ctx.roundRect) ctx.roundRect(X(x)-w/2,Y(y)-h/2,w,h,6); else ctx.rect(X(x)-w/2,Y(y)-h/2,w,h); ctx.fill(); ctx.stroke(); if(label) text(x,y-3,label,'#e8ecf3',11); if(sub) text(x,y+10,sub,'#9aa3b5',10); }

function draw(){
  fit(); ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);
  ctx.clearRect(0,0,cv.clientWidth,cv.clientHeight);
  animT = performance.now()/40;
  if(!G || !S) { requestAnimationFrame(draw); return; }
  const c = G.cfg, R = c.ring_road_radius, WR = c.wall_radius, HR = c.hub_radius, ns = c.sectors;
  // sectors
  for(let s=0;s<ns;s++){
    const a0=(s*60)*Math.PI/180, a1=((s+1)*60)*Math.PI/180;
    ctx.beginPath(); ctx.arc(X(0),Y(0),sc*(WR),a0,a1); ctx.arc(X(0),Y(0),sc*(HR+10),a1,a0,true); ctx.closePath();
    const sec=S.sectors[s];
    ctx.fillStyle = sec.lockdown ? 'rgba(226,87,77,.10)' : (!sec.online ? 'rgba(226,87,77,.05)' : (sec.dark ? 'rgba(0,0,0,.35)' : 'rgba(255,255,255,.025)'));
    ctx.fill();
    const [lx,ly]=polar(s*60+30, WR+40); text(lx,ly,`S${s+1}`,'#6d7689',12);
  }
  // wall
  ctx.beginPath(); ctx.strokeStyle='#7c766e'; ctx.lineWidth=4; ctx.arc(X(0),Y(0),sc*WR,0,Math.PI*2); ctx.stroke();
  // roads: ring, boundary streets through the gates, row streets, trunk road, tower road, service road
  for(let s=0;s<ns;s++){
    const integ=S.sectors[s].road; const col = integ<20?'#e2574d':(integ<50?'#8a6a2a':'#3d4350');
    ctx.beginPath(); ctx.strokeStyle=col; ctx.lineWidth=S.power.road_heating?5:4; ctx.arc(X(0),Y(0),sc*R,(s*60)*Math.PI/180,((s+1)*60)*Math.PI/180); ctx.stroke();
    const [sx,sy]=polar(s*60,HR), [ex,ey]=polar(s*60,WR+70); line(sx,sy,ex,ey,'#2e3440',2);
    for(let k=0;k<=c.house_rows;k++){ const r=c.house_radius_min-30+k*c.house_ring_step; ctx.beginPath(); ctx.strokeStyle='#262b36'; ctx.lineWidth=1.5; ctx.arc(X(0),Y(0),sc*r,(s*60+2.5)*Math.PI/180,(s*60+57.5)*Math.PI/180); ctx.stroke(); }
  }
  line(-WR-70,0,c.reactor_pos[0]+70,0,'#3d4350',4); line(c.tower_junction[0],c.tower_junction[1],c.tower_pos[0],c.tower_pos[1]+40,'#2e3440',2); line(c.reactor_pos[0]+70,-40,c.reactor_pos[0]+70,c.mine_pos[1]+40,'#2e3440',2);
  // gates in the wall at the sector boundaries
  for(let s=0;s<ns;s++){ const [gx,gy]=polar(s*60,WR); const st=S.sectors[s].gate; const col = st==='LOCKDOWN'?'#e2574d':(st==='OPEN'?'#5ec07a':'#8a93a6');
    ctx.save(); ctx.translate(X(gx),Y(gy)); ctx.rotate(s*60*Math.PI/180); ctx.fillStyle=col; ctx.fillRect(-3,-9,6,18); ctx.restore(); if(!S.sectors[s].gate_ok) text(gx,gy-12,'!','#e2574d',12); }
  // Both views consume the same utility graph.
  const waterOn = S.water.tank_m3>0 && S.water.pump;
  for(const e of G.utilities.links){const pts=e.points;const on=(S.hydraulics.flow_l_s[e.id]||0)>0;for(let j=0;j<pts.length-1;j++)flow(pts[j][0],pts[j][1],pts[j+1][0],pts[j+1][1],on?'#65bbd1':'#344c54',e.kind==='service'?.55:1.15,on,.5);}

  // power: trunk, tower line, solar line, feeders, spans along the pole tree
  const reactorUp = S.reactor.available_mw>0;
  flow(c.reactor_pos[0]+70, 8, -HR+10, 8, '#f2c14e', 3, S.power.trunk && reactorUp, 2.5);
  flow(c.tower_junction[0]+7, 8, c.tower_pos[0]+7, c.tower_pos[1]+40, '#f2c14e', 1.2, S.power.tower_line && S.power.trunk && reactorUp, 2);
  flow(c.solar_pos[0]+70, c.solar_pos[1]+30, c.reactor_pos[0]+40, -60, '#f2c14e', 1.2, S.power.solar_kw>0, 2);
  for(let s=0;s<ns;s++){ const [x1,y1]=polar(s*60+1.6,HR+20); flow(0,-40,x1,y1,'#f2c14e',2,S.power.feeder[s]&&S.sectors[s].online,2); }
  for(let i=0;i<G.poles.x.length;i++){
    const p=G.poles.parent[i], s=G.poles.sector[i];
    let px0,py0; if(p<0){ [px0,py0]=polar(s*60+1.6,HR+20); } else { px0=G.poles.x[p]; py0=G.poles.y[p]; }
    const px1=G.poles.x[i], py1=G.poles.y[i];
    flow(px0,py0,px1,py1,'#f2c14e',1.6,S.poles.span[i]===1,2);
    const dx=px1-px0, dy=py1-py0, L=Math.hypot(dx,dy)||1, nx=-dy/L*5, ny=dx/L*5;
    line(px0+nx,py0+ny,px1+nx,py1+ny,S.poles.net[i]===1?'#4fd1c5':'#4a3030',1);
  }
  for(let i=0;i<G.houses.x.length;i++){ const p=G.houses.pole[i]; line(G.houses.x[i],G.houses.y[i],G.poles.x[p],G.poles.y[p],'rgba(242,193,78,.12)',1); }
  line(-HR+10,12,-WR-40,12,S.net.uplink?'#4fd1c5':'#4a3030',1); line(-WR-40,12,c.tower_junction[0]-6,12,S.net.uplink?'#4fd1c5':'#4a3030',1); line(c.tower_junction[0]-6,12,c.tower_pos[0]-6,c.tower_pos[1]+40,S.net.uplink?'#4fd1c5':'#4a3030',1);
  // hub
  dot(0,0,sc*HR,'#1c2028'); ctx.beginPath(); ctx.strokeStyle=S.power.substation?'#f2c14e':'#e2574d'; ctx.lineWidth=2; ctx.arc(X(0),Y(0),sc*HR,0,Math.PI*2); ctx.stroke();
  text(0,-60,'substation',S.power.substation?'#f2c14e':'#e2574d',11); text(0,-42,`${S.power.available_kw} / ${S.power.demand_kw} kW`,'#9aa3b5',10);
  text(0,-16,`UPS center ${S.power.ups_center_kwh} kWh`,'#4fd1c5',10);
  text(0,4,S.net.comms?`comms node, ${S.net.packets_per_min} pkt/min`:'comms DOWN',S.net.comms&&S.net.uplink?'#4fd1c5':'#e2574d',11); text(0,24,'ops center, pump station','#9aa3b5',10);
  text(0,44,`tank ${S.water.tank_m3} m3, ${S.water.flow_m3_h} m3/h`,waterOn?'#5aa9ff':'#e2574d',10);
  // reactor complex
  const rc=modeColor[S.reactor.mode]||'#888'; const rx=c.reactor_pos[0], ry=c.reactor_pos[1];
  box(c.solar_pos[0],c.solar_pos[1],120,34,'#20242e','#7a6a2a','solar field',`${S.power.solar_kw} kW`);
  box(rx,ry,150,54,'#20242e',rc,`REACTOR ${S.reactor.mode}`,`${S.reactor.power_mw} MW el, core ${S.reactor.core_temp} C`);
  if(S.reactor.marines) text(rx,ry-38,'MARINES IN THE SUBLEVELS','#e2574d',10);
  box(c.water_plant_pos[0],c.water_plant_pos[1],120,34,'#20242e',S.water.plant?'#5aa9ff':'#e2574d','water plant',S.water.plant?`${S.water.plant_m3_h} m3/h`:'no heat');
  box(c.radwaste_pos[0],c.radwaste_pos[1],150,34,'#20242e','#e8d34a','radioactive waste storage',`${S.power.infra.waste_storage} kW`);
  box(c.mine_pos[0],c.mine_pos[1],110,34,'#20242e',S.power.mine?'#a08a2a':'#5a5a5a','mine',S.power.mine?`${S.power.infra.mine} kW`:'stopped');
  box(c.waste_station_pos[0],c.waste_station_pos[1],120,30,'#20242e','#9bd36a','waste processing',`${S.finance.waste_station} loads`);
  // tower
  const [tx,ty]=[c.tower_pos[0],c.tower_pos[1]];
  ctx.beginPath(); ctx.strokeStyle=S.net.uplink?'#4fd1c5':'#e2574d'; ctx.lineWidth=2; ctx.moveTo(X(tx)-10,Y(ty)+18); ctx.lineTo(X(tx),Y(ty)-18); ctx.lineTo(X(tx)+10,Y(ty)+18); ctx.stroke();
  text(tx,ty+32,S.net.uplink?'uplink OK':'uplink LOST',S.net.uplink?'#4fd1c5':'#e2574d',10);
  if(S.net.uplink){ for(let k=0;k<3;k++){ ctx.beginPath(); ctx.strokeStyle=`rgba(79,209,197,${0.5-0.15*k})`; ctx.arc(X(tx),Y(ty)-14,8+6*k+((animT*2)%6),-2.2,-0.9); ctx.stroke(); } }
  // poles and lamps
  for(let i=0;i<G.poles.x.length;i++){ const x=G.poles.x[i],y=G.poles.y[i],st=S.poles.state[i];
    if(S.poles.lamp[i]===1){ const g=ctx.createRadialGradient(X(x),Y(y),0,X(x),Y(y),sc*22); g.addColorStop(0,'rgba(255,230,140,.35)'); g.addColorStop(1,'rgba(255,230,140,0)'); ctx.fillStyle=g; ctx.beginPath(); ctx.arc(X(x),Y(y),sc*22,0,Math.PI*2); ctx.fill(); }
    if(st===2){ text(x,y+4,'x','#e2574d',13); } else dot(x,y,2.2,st===1?'#e0b04a':'#c9cfdb'); }
  // houses
  const hs=S.houses; const sz=Math.max(4,sc*12);
  for(let i=0;i<G.houses.x.length;i++){ const x=X(G.houses.x[i]),y=Y(G.houses.y[i]);
    ctx.fillStyle=tempColor(hs.t[i]); ctx.fillRect(x-sz/2,y-sz/2,sz,sz);
    if(!hs.power[i]){ ctx.strokeStyle='#e2574d'; ctx.lineWidth=1.5; ctx.strokeRect(x-sz/2,y-sz/2,sz,sz); }
    else if(hs.ups[i]){ ctx.strokeStyle='#5aa9ff'; ctx.lineWidth=1.5; ctx.strokeRect(x-sz/2,y-sz/2,sz,sz); }
    else if(hs.limit[i]>0){ ctx.strokeStyle='#e0b04a'; ctx.lineWidth=1; ctx.strokeRect(x-sz/2,y-sz/2,sz,sz); }
    if(hs.heater[i]&&hs.power[i]){ ctx.fillStyle='#ff7a30'; ctx.fillRect(x-1.5,y-1.5,3,3); }
    if(hs.burst[i]){ ctx.strokeStyle='#5aa9ff'; ctx.lineWidth=1.5; ctx.beginPath(); ctx.moveTo(x-sz/2,y-sz/2); ctx.lineTo(x+sz/2,y+sz/2); ctx.moveTo(x+sz/2,y-sz/2); ctx.lineTo(x-sz/2,y+sz/2); ctx.stroke(); }
  }
  // people
  for(const p of S.people) dot(p[0],p[1],1.6,'#ffffff');
  // internet packets along the pole tree
  const now=performance.now();
  for(const p of S.net.packets){ const key=p.t+':'+p.from+':'+p.id; if(!packetsSeen.has(key)) packetsSeen.set(key, now); }
  for(const [key,t0] of packetsSeen){ if(now-t0>1800){ packetsSeen.delete(key); continue; }
    const [t,from,id]=key.split(':'); const pk=S.net.packets.find(q=>q.t+':'+q.from+':'+q.id===key); if(!pk) continue;
    let path=[];
    if(from==='house'){ const i=+id; let p=G.houses.pole[i], s=G.houses.sector[i]; path.push([G.houses.x[i],G.houses.y[i]]); let guard=0; while(p>=0&&guard++<40){ path.push([G.poles.x[p],G.poles.y[p]]); p=G.poles.parent[p]; } path.push(polar(s*60+4.5,HR+20)); path.push([0,0]); }
    else { path.push([0,0]); }
    if(pk.kind==='reactor'||pk.kind==='lost'){ path.push([-HR+10,8]); path.push([-WR-40,8]); path.push([rx+70,8]); }
    else if(pk.uplink) path.push([-HR+10,12],[-WR-40,12],[c.tower_junction[0]-6,12],[tx-6,ty+40]);
    const u=(now-t0)/1800; let seg=Math.floor(u*(path.length-1)), f=u*(path.length-1)-seg; if(seg>=path.length-1){seg=path.length-2;f=1;}
    const [ax,ay]=path[seg],[bx,by]=path[seg+1]; dot(ax+(bx-ax)*f,ay+(by-ay)*f,2.5,pk.uplink?(pk.kind==='reactor'?'#f2c14e':'#4fd1c5'):'#e2574d'); }
  // waste bins at the ring
  for(let s=0;s<ns;s++){ const [bx,by]=polar(s*60+30,R+22); const w=S.sectors[s].waste; ctx.fillStyle=w>=1?'#e2574d':(w>=0.9?'#e0b04a':'#3d4350'); ctx.fillRect(X(bx)-5,Y(by)-5,10,10); ctx.fillStyle='#8a93a6'; ctx.fillRect(X(bx)-4,Y(by)+4-8*Math.min(1,w),8,8*Math.min(1,w)); }
  // rovers
  const rc2={garbage:['G','#9bd36a'],sludge:['S','#b48ead'],repair:['E','#f2c14e'],plumber:['P','#5aa9ff']};
  for(const r of S.rovers){ const [l,col]=rc2[r.kind]||['?','#fff']; dot(r.x,r.y,7,col); text(r.x,r.y+4,l,'#111',10); text(r.x,r.y+16,r.state.toLowerCase().replace('_',' '),'#9aa3b5',9); }
  // xenomorphs and marines
  for(const x of S.xenos){ ctx.save(); ctx.translate(X(x.x),Y(x.y)); ctx.rotate(Math.PI/4); ctx.fillStyle='#e2574d'; ctx.fillRect(-5,-5,10,10); ctx.restore(); }
  for(const m of S.marines) dot(m[0],m[1],2.5,'#8be05a');
  // issues
  for(const i of S.issues){ const col=i.sev==='critical'?'#e2574d':(i.sev==='warning'?'#e0b04a':'#8a93a6'); dot(i.x+8,i.y-8,6,col); text(i.x+8,i.y-4,'!','#111',10); }
  // banner
  const e=S.env; document.getElementById('banner').innerHTML = `<b>${S.time}</b> &nbsp; ${e.t_out} C, wind ${e.wind} m/s${e.storm?' <span class="bad">STORM</span>':''}${e.precip==='snow'?' snow':''}${e.night?' night':' day'}${S.paused?' <span class="warn">PAUSED</span>':''} &nbsp; ${S.speed} min/s`;
  const fin=document.getElementById('finished'); if(S.finished){ fin.style.display='flex'; fin.textContent='COLONY LOST: '+S.finish_reason+'. A new colony is founded in two minutes.'; } else fin.style.display='none';
  requestAnimationFrame(draw);
}

function cls(ok, warn){ return ok?'ok':(warn?'warn':'bad'); }
function renderSide(s){
  document.getElementById('time').textContent = s.time;
  document.getElementById('pause').textContent = s.paused?'Resume':'Pause';
  document.querySelectorAll('button[data-s]').forEach(b=>b.classList.toggle('on', +b.dataset.s===s.speed));
  const p=s.power, r=s.reactor, w=s.water, f=s.finance;
  const kp=[
    ['Colony budget', f.colony.toLocaleString()+' cr', f.colony>20000?'ok':(f.colony>0?'warn':'bad')],
    ['Sector budgets', f.sectors.map(x=>Math.round(x/1000)+'k').join(' '), Math.min(...f.sectors)>2000?'ok':'warn'],
    ['Power available', p.available_kw+' kW', p.available_kw>p.demand_kw?'ok':'bad'],
    ['Power demand', p.demand_kw+' kW'+(p.shedding?` / shedding L${p.shedding}`:''), p.shedding?'warn':'ok'],
    ['Water tank', w.tank_m3+' m3, '+w.houses_ok+'/300 houses', w.tank_m3>100&&w.houses_ok>280?'ok':'warn'],
    ['Pipes', `${w.frozen} frozen, ${w.burst} burst`, w.burst===0?'ok':'bad'],
    ['Internet', `${s.net.houses_online}/300 online, uplink ${s.net.uplink?'OK':'LOST'}`, s.net.uplink&&s.net.houses_online>280?'ok':'warn'],
    ['Open issues', s.issues_total+(f.unpaid?` (unpaid ${f.unpaid} cr)`:''), s.issues_total<5?'ok':'warn'],
    ['Month income (colony)', f.month_income.toLocaleString()+' cr', 'dim'],
    ['Month expense (colony)', f.month_expense.toLocaleString()+' cr', 'dim'],
  ];
  document.getElementById('kpi').innerHTML = kp.map(([l,v,c])=>`<div class="card"><div class="v ${c}">${v}</div><div class="l">${l}</div></div>`).join('');
  const inf=p.infra;
  document.getElementById('reactor').innerHTML = `<div><b class="${r.mode==='ONLINE'?'ok':(r.mode==='RUNBACK'||r.mode==='STARTING'?'warn':'bad')}">${r.mode}</b> &nbsp; ${r.power_mw} MW gross, ${r.available_mw} MW to grid, core ${r.core_temp} C${r.decay_mw?`, decay ${r.decay_mw} MW`:''}</div>
    <div class="dim">pumps A ${r.pump_a} B ${r.pump_b}, heat exchanger ${r.hx}, batteries ${r.battery_h} h, link ${r.link?'ok':'<span class="bad">lost</span>'}${r.faults.length?', faults: '+r.faults.join(', '):''}</div>
    <div class="dim">solar ${p.solar_kw} kW; loads: mine ${inf.mine}, houses ${Math.round(p.demand_kw-Object.values(inf).reduce((a,b)=>a+b,0))}, water plant ${inf.water_plant}, road heating ${inf.road_heating}, lamps ${inf.lamps}, comms ${inf.comms}, ups charge ${inf.ups_charge} kW</div>
    <div class="dim">trunk ${p.trunk?'ok':'<span class="bad">CUT</span>'}, substation ${p.substation?'ok':'<span class="bad">DOWN</span>'}, UPS center ${p.ups_center} ${p.ups_center_kwh} kWh</div>`;
  document.querySelector('#sectors tbody').innerHTML = s.sectors.map(x=>`<tr><td>${x.id}${x.dark?' <span class="warn">dark</span>':''}</td><td>${x.budget}</td><td>${x.demand_kw}</td><td class="${x.avg_t>15?'ok':(x.avg_t>4?'warn':'bad')}">${x.avg_t}</td><td class="${x.min_t>4?'ok':'bad'}">${x.min_t}</td><td class="${cls(x.power_ok===50,x.power_ok>30)}">${x.power_ok}</td><td class="${cls(x.water_ok===50,x.water_ok>30)}">${x.water_ok}</td><td class="${cls(x.net_ok===50,x.net_ok>30)}">${x.net_ok}</td><td class="${x.ups==='DISCHARGING'?'warn':(x.ups==='DEPLETED'?'bad':'dim')}">${x.ups.slice(0,4)} ${x.ups_kwh}</td><td class="${x.waste>=1?'bad':(x.waste>=0.9?'warn':'dim')}">${Math.round(x.waste*100)}%</td><td class="${x.sanitary>70?'ok':'bad'}">${x.sanitary}</td><td class="${x.gate==='OPEN'?'ok':(x.gate==='LOCKDOWN'?'bad':'warn')}">${x.gate.slice(0,4)}</td><td class="${x.road>20?'dim':'bad'}">${x.road}%</td></tr>`).join('');
  document.getElementById('nissues').textContent = `(${s.issues_total})`;
  document.getElementById('issues').innerHTML = s.issues.slice().reverse().map(i=>`<div><span class="${i.sev==='critical'?'bad':(i.sev==='warning'?'warn':'dim')}">${i.kind}</span> ${i.target} ${i.sector>0?'S'+i.sector:''} ${i.cause}, ${i.cost} cr (${i.payer}) <span class="dim">${i.status}, ${Math.round(i.age/60)} h</span></div>`).join('') || '<div>none</div>';
  document.getElementById('log').innerHTML = s.events.map(e=>`<div class="${e.level}">${String(e.t).padStart(6)} ${e.text}</div>`).join('');
  const rp=s.report; if(rp){ document.getElementById('report').textContent =
    `Month ${rp.month}: owners paid ${Math.round(rp.houses_total)} cr (energy ${Math.round(rp.energy_total)}, water ${Math.round(rp.water_total)}, repairs ${Math.round(rp.repairs_total)}), ${Math.round(rp.kwh_total)} kWh\n`+
    `colony: income ${rp.colony_income}, expense ${rp.colony_expense}, budget ${rp.colony_budget}, unpaid ${rp.unpaid}\n`+
    `sector income ${rp.sector_income.join(' | ')}\nsector expense ${rp.sector_expense.join(' | ')}\n`+
    `expense by cause: ${Object.entries(rp.by_cause).map(([k,v])=>k+' '+v).join(', ')}\n`+
    `top houses: ${rp.top_houses.map(h=>`#${h.house} (S${h.sector}) ${h.total}`).join(', ')}`; }
}
cv.addEventListener('mousemove', ev => {
  const tip=document.getElementById('tip'); if(!G||!S){ tip.style.display='none'; return; }
  const r=cv.getBoundingClientRect(), mx=ev.clientX-r.left, my=ev.clientY-r.top; let best=-1, bd=10;
  for(let i=0;i<G.houses.x.length;i++){ const d=Math.hypot(X(G.houses.x[i])-mx, Y(G.houses.y[i])-my); if(d<bd){bd=d;best=i;} }
  if(best<0){ tip.style.display='none'; return; }
  const h=S.houses, i=best;
  tip.innerHTML=`<b>House ${i+1}</b> (S${G.houses.sector[i]+1}, ${G.types[G.houses.type[i]]})<br>indoor ${h.t[i]} C, heater ${h.heater[i]?'on':'off'}<br>power ${h.power[i]?(h.ups[i]?'UPS':'grid'):'<span class="bad">none</span>'}${h.limit[i]?', limit '+h.limit[i]+' W':''}<br>water ${h.water[i]?'ok':'<span class="bad">no</span>'}${h.burst[i]?', <span class="bad">pipes burst</span>':''}<br>internet ${h.net[i]?'online':'offline'}, sludge ${Math.round(h.sludge[i]*100)}%`;
  tip.style.display='block'; tip.style.left=(mx+14)+'px'; tip.style.top=(my+14)+'px';
});
loadGeom().then(()=>{ poll(); draw(); });
window.addEventListener('resize', fit);
</script></body></html>
"""

# ------------------------------------------------------------------------------------
# 3D UI (served at /): the colony on a small planet, three.js. Flat 2D map stays at /flat.
# __THREE_BASE__ is replaced at startup (cdn or /vendor/).
# ------------------------------------------------------------------------------------

HTML3D = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Hadley's Hope</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { --bg:#07090d; --panel:#12151c; --line:#262b36; --text:#d9dde6; --dim:#8a93a6; --ok:#5ec07a; --warn:#e0b04a; --bad:#e2574d; --blue:#5aa9ff; --cyan:#4fd1c5; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font:13px/1.35 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; display:flex; height:100vh; overflow:hidden; }
  #map { flex:1 1 auto; position:relative; min-width:0; }
  canvas { display:block; }
  #side { width:470px; flex:0 0 470px; background:var(--panel); border-left:1px solid var(--line); overflow-y:auto; padding:10px 12px; }
  h1 { font-size:15px; margin:0 0 6px; } h2 { font-size:12px; color:var(--dim); text-transform:uppercase; letter-spacing:.06em; margin:14px 0 6px; }
  .row { display:flex; gap:6px; flex-wrap:wrap; align-items:center; }
  button { background:#232835; color:var(--text); border:1px solid var(--line); border-radius:6px; padding:4px 8px; cursor:pointer; font-size:12px; }
  button:hover { background:#2d3444; } button.on { border-color:var(--blue); color:var(--blue); }
  a.tab { color:var(--text); text-decoration:none; padding:4px 10px; border:1px solid var(--line); border-radius:6px; background:#1c212c; font-size:12px; } a.tab.on { border-color:var(--blue); color:var(--blue); } a.tab:hover { background:#2d3444; }
  label.chk { display:inline-flex; align-items:center; gap:4px; background:#1c212c; border:1px solid var(--line); border-radius:6px; padding:3px 7px; font-size:11.5px; cursor:pointer; }
  input[type=range] { width:190px; } input[type=text] { background:#0b0e13; color:var(--text); border:1px solid var(--line); border-radius:6px; padding:4px 6px; font-size:12px; width:150px; }
  .kpi { display:grid; grid-template-columns:1fr 1fr; gap:6px; }
  .card { background:#1a1f2a; border:1px solid var(--line); border-radius:8px; padding:6px 8px; }
  .card .v { font-size:17px; font-weight:600; } .card .l { color:var(--dim); font-size:11px; }
  table { width:100%; border-collapse:collapse; font-size:11.5px; } th,td { padding:2px 3px; text-align:right; border-bottom:1px solid var(--line); white-space:nowrap; } th { color:var(--dim); font-weight:500; } td:first-child, th:first-child { text-align:left; }
  tr.sec { cursor:pointer; } tr.sec:hover { background:#1c212c; }
  .ok { color:var(--ok); } .warn { color:var(--warn); } .bad { color:var(--bad); } .dim { color:var(--dim); }
  #log { font-family:ui-monospace,Menlo,Consolas,monospace; font-size:11px; max-height:220px; overflow-y:auto; background:#0b0e13; border:1px solid var(--line); border-radius:6px; padding:6px; }
  #log div { padding:1px 0; } .ALARM { color:var(--bad); } .WARN { color:var(--warn); } .INFO { color:var(--dim); }
  #banner { position:absolute; left:10px; top:10px; background:rgba(18,21,28,.88); border:1px solid var(--line); border-radius:8px; padding:6px 10px; font-size:13px; pointer-events:none; }
  #hint { position:absolute; left:10px; bottom:10px; background:rgba(18,21,28,.88); border:1px solid var(--line); border-radius:8px; padding:6px 10px; font-size:11px; color:var(--dim); pointer-events:none; } #hint a { pointer-events:auto; }
  #tip { position:absolute; display:none; background:rgba(18,21,28,.95); border:1px solid var(--line); border-radius:6px; padding:6px 8px; font-size:11px; pointer-events:none; max-width:260px; }
  #info { position:absolute; right:10px; top:10px; display:none; width:300px; background:rgba(18,21,28,.94); border:1px solid var(--line); border-radius:8px; padding:8px 10px; font-size:12px; }
  #info h3 { margin:0 0 6px; font-size:13px; } #info .close { float:right; cursor:pointer; color:var(--dim); } #info table { font-size:11.5px; } #info td { text-align:left; }
  #alerts { position:absolute; left:10px; top:48px; display:none; background:rgba(120,30,30,.85); border:1px solid #e2574d; border-radius:8px; padding:6px 10px; font-size:12px; color:#ffd9d6; pointer-events:none; }
  #toast { position:absolute; left:50%; top:14px; transform:translateX(-50%); display:none; background:rgba(18,21,28,.95); border:1px solid var(--blue); border-radius:8px; padding:8px 14px; font-size:13px; pointer-events:none; }
  #finished { position:absolute; inset:0; display:none; align-items:center; justify-content:center; background:rgba(0,0,0,.6); font-size:28px; color:var(--bad); }
  pre { white-space:pre-wrap; font-size:11px; background:#0b0e13; padding:6px; border-radius:6px; border:1px solid var(--line); }
  @media (max-width: 900px) { body { flex-direction:column; overflow:auto; height:auto; } #map { flex:none; height:64vh; min-height:360px; } #side { width:100%; flex:none; border-left:none; border-top:1px solid var(--line); } #hint { display:none; } #info { width:220px; } }
/* 3D-only survey HUD. The world owns the viewport; instruments float above it. */
:root{--bg:#080c0e;--panel:#10191a;--line:#839a893f;--text:#e1e9cf;--dim:#b6bda7;--blue:#a4d0ca;--ok:#b5d4a0;--warn:#e8c17b;--bad:#eb8e73}
body{display:block;height:100dvh;overflow:hidden;font:12px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace}
#map{position:absolute;inset:0;width:100%;height:100%;min-height:0}
#commandbar{position:absolute;top:0;left:0;right:0;z-index:10;display:flex;align-items:center;gap:22px;padding:17px 24px;background:linear-gradient(#071012e8,#0710126b,transparent);border:0;pointer-events:none}
#commandbar>*{pointer-events:auto}.brand{display:flex;align-items:center;gap:10px;flex-shrink:0}.brand-mark{display:none}.brand strong{font-size:12px;font-weight:500;letter-spacing:.16em}.brand small{display:block;color:#adb9a7;font-size:8px;letter-spacing:.22em;margin-top:3px}
.main-nav{display:flex;gap:14px;overflow-x:auto;scrollbar-width:none}.main-nav a{padding:5px 0;color:#a9b4a5;text-decoration:none;font-size:10px;white-space:nowrap;border:0;border-bottom:1px solid transparent;text-transform:uppercase;letter-spacing:.06em}.main-nav a:hover,.main-nav a:focus-visible{color:#f2f4dc;border-color:#dce3b7}.main-nav a[aria-current=page]{color:#e7e8cb;border-color:#e0c890}.main-nav a.attr-link{color:#a4d0ca}
.transport{margin-left:auto;display:flex;align-items:center;gap:8px}.transport #time{display:none}.transport label{font-size:9px;color:var(--dim)}.transport input{width:64px;accent-color:#d3d6af}.transport #speedv{font-size:9px;white-space:nowrap}
button,a.tab,label.chk{font:inherit;border-radius:0;background:#0b151a60;border:1px solid #adbaa144;color:var(--text)}button{padding:7px 10px;cursor:pointer;font-size:10px}button:hover{background:#8b9e7d22;border-color:#bfc9a7}button:focus-visible,a:focus-visible,summary:focus-visible{outline:2px solid #d8deae;outline-offset:3px}#pause{border:0;border-left:1px solid #b5bda15c}#panel-toggle{border:0;border-bottom:1px solid #b5bda16e;white-space:nowrap}
#banner{left:24px;top:83px;padding:9px 12px;border:0;border-left:2px solid #d2c99b;border-radius:0;background:linear-gradient(90deg,#0a131b9e,transparent);backdrop-filter:none;color:#d9ddc6;font-size:10px;max-width:calc(100% - 48px);letter-spacing:.03em;text-shadow:0 1px 3px #000}
#alerts{top:128px;left:24px;border:0;border-left:2px solid #df815d;border-radius:0;background:#291710ac;padding:8px 12px;font-size:10px}#toast{top:125px;border-radius:0;background:#10191de0;font-size:11px}
#side{position:absolute;right:22px;top:82px;bottom:102px;z-index:8;width:315px;max-width:calc(100% - 44px);padding:0;overflow:auto;background:linear-gradient(90deg,#0b141a75,#0b141ae6);border:0;border-top:1px solid #bec8a480;border-bottom:1px solid #bec8a440;backdrop-filter:blur(9px);scrollbar-width:thin;scrollbar-color:#718376 transparent}
body.panel-collapsed #side{display:none}.panel-tabs{display:grid;grid-template-columns:repeat(4,1fr);gap:0;position:sticky;top:0;background:#0d191de8;z-index:2}.panel-tabs button{border:0;border-bottom:1px solid transparent;background:none;font-size:9px;color:#aab6a4;padding:14px 3px}.panel-tabs button[aria-selected=true]{border-color:#dfd1a3;color:#f1ebc5}
.hud-panel{padding:15px 15px 20px}.hud-panel[hidden]{display:none}.section-kicker{font-size:8px;letter-spacing:.18em;color:#adbaa1;margin-bottom:6px}.hud-panel h2{font-size:13px;font-weight:400;letter-spacing:.08em;text-transform:uppercase;margin:0 0 14px;color:#e2e5c7}.hud-panel h3{font-size:10px;color:#c7ceaf;letter-spacing:.1em;margin:22px 0 10px}
.kpi{display:flex;flex-direction:column;gap:0}.card{border:0;border-bottom:1px solid #b4c19b26;background:none;padding:8px 0;border-radius:0}.kpi .card{display:flex;flex-direction:row-reverse;justify-content:space-between;align-items:baseline;gap:12px}.card .v{font-size:13px;font-weight:400;letter-spacing:0;text-align:right}.card .l{font-size:9px;color:#b1bca6;min-width:90px}.hud-panel details{border-top:1px solid #b4c19b26;padding:12px 0}.hud-panel summary{font-size:10px;cursor:pointer}.table-scroll{overflow:auto}.sector-grid{display:flex;flex-direction:column;gap:0}.sector-card{display:grid;grid-template-columns:1fr auto;text-align:left;border:0;border-bottom:1px solid #b4c19b26;background:none;padding:8px 0}.sector-card strong{font-size:10px;font-weight:400}.sector-card small{font-size:8px;color:#a6b69e}.service-bars{display:flex;grid-column:1/-1;gap:3px;margin-top:4px}.service-bars span{height:2px;flex:1;background:#41554b}.service-bars .good{background:#b0c39a}.service-bars .warn{background:#d4a16c}
#layers fieldset{border:0;padding:0;margin:0 0 17px}#layers legend{font-size:9px;letter-spacing:.12em;color:#bcc4a5;padding:0 0 9px}.layer-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}label.chk{display:flex;align-items:center;gap:6px;padding:6px;font-size:9px;border-color:#839a8930;background:none}input[type=checkbox]{accent-color:#b9ca9c}.muted-copy{font-size:9px;color:#a7b39b;line-height:1.7}#fly{display:grid;grid-template-columns:1fr 1fr;gap:6px}#fly button{text-align:left}.destination-primary{grid-column:1/-1}.ops-actions{display:grid;grid-template-columns:1fr 1fr;gap:6px}#token{width:100%;margin:8px 0}
#view-tools{position:absolute;left:24px;bottom:48px;display:flex;flex-direction:column-reverse;gap:15px;max-width:calc(100% - 48px);z-index:3}.view-presets{display:flex;gap:22px;background:linear-gradient(90deg,#0a131ba6,transparent);border:0;padding:10px 15px 9px 0}.view-presets button{border:0;border-top:1px solid #c1c6a146;border-radius:0;background:none;padding:9px 2px 0;color:#aab6a2;text-transform:uppercase;font-size:10px;letter-spacing:.13em}.view-presets button[aria-pressed=true]{border-color:#f0d18d;color:#f0dfae}.view-presets button::before{content:attr(data-key);font-size:8px;display:inline-block;margin-right:7px;color:#c4c5a5}
.map-key{display:flex;flex-direction:column;gap:7px;font-size:9px;text-shadow:0 1px 3px #000;color:#d0d7bf;background:linear-gradient(90deg,#0a131b88,transparent);border:0;border-left:1px solid #b5c09a70;padding:10px 13px;max-width:270px}.map-key span{display:flex;align-items:center;gap:9px}.map-key i{width:19px;height:2px;display:inline-block;background:var(--swatch)}#hint{left:24px;bottom:17px;font-size:9px;letter-spacing:.04em;background:none;border:0;padding:0;color:#b5bfa8;text-shadow:0 1px 4px #000}
#info{right:24px;top:84px;width:310px;max-height:calc(100% - 220px);overflow:auto;padding:14px;background:#0c171cda;border:0;border-left:2px solid #cabd91;border-radius:0;backdrop-filter:blur(8px);z-index:9;font-size:10px}#info h3{font-size:11px;letter-spacing:.06em}#infoclose{float:right;background:none;border:0;font-size:9px}#tip{border:0;border-left:1px solid #d1ceab;border-radius:0;background:#0c171ce8;font-size:10px}
@media(max-width:1150px){#commandbar{gap:15px}.main-nav{gap:9px}.main-nav a{font-size:9px}.transport label{display:none}.transport input{width:44px}.brand strong{font-size:10px}}
@media(max-width:850px){#commandbar{flex-wrap:wrap;gap:8px;padding:13px 15px}.main-nav{order:3;width:100%;gap:17px}.transport input,.transport #speedv{display:none}#banner{top:105px;left:15px}#alerts{top:143px;left:15px}#side,#info{top:155px;right:15px;bottom:135px}#view-tools{left:15px;bottom:45px}.view-presets{gap:17px}.map-key{font-size:8px;gap:4px;padding:8px}#hint{left:15px;font-size:8px}#info{bottom:auto;max-height:55vh}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}

</style>
<script type="importmap">{"imports":{"three":"__THREE_BASE__build/three.module.js","three/addons/":"__THREE_BASE__examples/jsm/"}}</script>
</head>
<body class="panel-collapsed">
<header id="commandbar">
 <div class="brand"><span class="brand-mark" aria-hidden="true">HH</span><div><strong>HADLEY'S HOPE</strong><small>LV–426 · COLONY OPERATIONS</small></div></div>
 <nav class="main-nav" aria-label="Main navigation"><a href="/" aria-current="page">3D map</a><a href="/flat">Map</a><a href="/attractors" class="attr-link">Attractors</a><a href="/graph">Systems</a><a href="/bus">Controllers</a><a href="/house">House</a></nav>
 <div class="transport"><span id="time"></span><button id="pause" title="Pause or resume simulation">Pause</button><label for="speed">Speed</label><input type="range" id="speed" min="0" max="100" value="45"><span id="speedv"></span><button id="panel-toggle" aria-expanded="false" aria-controls="side" title="Show or hide management panel">M · Console</button></div>
</header>
<div id="map">
 <div id="banner" role="status">Connecting to colony…</div>
 <div id="hint">DRAG pan · RMB orbit · WASD / ↑↓←→ move · Q/E altitude · SHIFT fast · PINCH zoom · F focus · M console</div>
 <div id="tip"></div>
 <div id="info"><button class="close" id="infoclose" aria-label="Close inspector">Close</button><h3 id="infotitle"></h3><div id="infobody"></div></div>
 <div id="alerts" role="status"></div><div id="toast" role="status"></div><div id="finished"></div>
 <div id="view-tools"><div class="view-presets" role="group" aria-label="Map view"><button data-key="01" data-view="colony" aria-pressed="true">Colony</button><button data-key="02" data-view="water" aria-pressed="false">Water</button><button data-key="03" data-view="power" aria-pressed="false">Power</button><button data-key="04" data-view="network" aria-pressed="false">Network</button></div><div id="map-key" class="map-key" aria-label="Map legend"></div></div>
</div>
<aside id="side" aria-label="Colony management">
 <div class="panel-tabs" role="tablist" aria-label="Management panels"><button id="tab-overview" role="tab" aria-controls="panel-overview" aria-selected="true" data-panel="overview">Overview</button><button id="tab-layers" role="tab" aria-controls="panel-layers" aria-selected="false" data-panel="layers" tabindex="-1">Layers</button><button id="tab-places" role="tab" aria-controls="panel-places" aria-selected="false" data-panel="places" tabindex="-1">Places</button><button id="tab-operations" role="tab" aria-controls="panel-operations" aria-selected="false" data-panel="operations" tabindex="-1">Operations</button></div>
 <section id="panel-overview" class="hud-panel" role="tabpanel" aria-labelledby="tab-overview">
  <div class="section-kicker">Colony telemetry</div><h2>Current situation</h2><div class="kpi" id="kpi"></div>
  <h3>Districts</h3><div id="sector-cards" class="sector-grid"></div>
  <details><summary>Reactor &amp; power</summary><div id="reactor" class="card"></div></details>
  <details><summary>District data</summary><div class="table-scroll"><table id="sectors"><thead><tr><th>#</th><th>cr</th><th>kW</th><th>avg °C</th><th>min °C</th><th>power</th><th>water</th><th>net</th><th>UPS</th><th>waste</th><th>san.</th><th>gate</th><th>road</th></tr></thead><tbody></tbody></table></div></details>
  <details open><summary>Maintenance <span id="nissues" class="dim"></span></summary><div id="issues" class="dim" style="font-size:11px;max-height:150px;overflow:auto"></div></details>
  <details><summary>Event log</summary><div id="log"></div></details><details><summary>Monthly report</summary><pre id="report">No month closed yet.</pre></details>
 </section>
 <section id="panel-layers" class="hud-panel" role="tabpanel" aria-labelledby="tab-layers" hidden>
  <div class="section-kicker">Display controls</div><h2>Read the city</h2>
  <div id="layers">
   <fieldset><legend>World</legend><div class="layer-grid"><label class="chk"><input type="checkbox" data-l="people" checked>Colonists</label><label class="chk"><input type="checkbox" data-l="threats" checked>Threats &amp; marines</label><label class="chk"><input type="checkbox" data-l="labels">Place labels</label><label class="chk"><input type="checkbox" data-l="cutaway">Roof transparency</label></div></fieldset>
   <fieldset><legend>Infrastructure</legend><div class="layer-grid"><label class="chk"><input type="checkbox" data-l="underground">Buried utilities</label><label class="chk"><input type="checkbox" data-l="water" checked>Water flow</label><label class="chk"><input type="checkbox" data-l="power" checked>Power flow</label><label class="chk"><input type="checkbox" data-l="packets" checked>Data packets</label></div></fieldset>
   <fieldset><legend>Indicators</legend><div class="layer-grid"><label class="chk"><input type="checkbox" data-l="issues" checked>Faults</label><label class="chk"><input type="checkbox" data-l="nonet">Offline homes</label><label class="chk"><input type="checkbox" data-l="ups">UPS activity</label><label class="chk"><input type="checkbox" data-l="heater">Heating</label><label class="chk"><input type="checkbox" data-l="ctrl">House programs</label></div></fieldset>
   <fieldset><legend>Graphics</legend><div class="layer-grid"><label class="chk"><input type="checkbox" data-l="bloom" checked>Light bloom</label><label class="chk"><input type="checkbox" data-l="shadows" checked>Shadows</label></div></fieldset>
  </div><p class="muted-copy">Select Water below the map to inspect underground pipes. Colours identify separate networks; click a pipe for its material, diameter and live flow.</p>
 </section>
 <section id="panel-places" class="hud-panel" role="tabpanel" aria-labelledby="tab-places" hidden>
  <div class="section-kicker">Camera navigation</div><h2>Explore the colony</h2>
  <div id="fly"><button data-f="home" class="destination-primary">Inspect selected home</button><button data-f="city">Colony overview</button><button data-f="street">Residential street</button><button data-f="hub">Operations hub</button><button data-f="gate">West gate</button><button data-f="reactor">Reactor</button><button data-f="solar">Solar field</button><button data-f="dish">Space dish</button><button data-f="intake">Ocean intake</button><button data-f="cargo">Freight</button><button data-f="tower">Comms tower</button><button data-f="mine">Mine</button><button data-f="planet">Planet</button></div>
  <p class="muted-copy">Close views reveal furnished rooms and building services. Enable Roof transparency in Layers to adjust roof translucency; roofs and equipment always remain present.</p>
  <h3>Research</h3><a href="/attractors" class="tab">Open attractor observatory →</a>
 </section>
 <section id="panel-operations" class="hud-panel" role="tabpanel" aria-labelledby="tab-operations" hidden>
  <div class="section-kicker">Operator console</div><h2>Simulation controls</h2>
  <details><summary>Operator access <span id="tokenstate" class="dim"></span></summary><label for="token" class="muted-copy">Admin token</label><input type="password" id="token" placeholder="Enter token" autocomplete="off"><button id="tokenbtn">Enable controls</button></details>
  <details><summary>House controllers</summary><div id="ctrl" class="dim" style="font-size:11px"></div><p><a href="/bus">Controller messages &amp; programs →</a></p></details>
  <details><summary>Scenario events</summary><p class="muted-copy">These actions change the running simulation.</p><div class="ops-actions"><button data-i="storm">Storm</button><button data-i="xeno">Xenomorphs</button><button data-i="span">Break power span</button><button data-i="pole">Fell pole</button><button data-i="trunk">Cut main cable</button><button data-i="pump">Pump trip</button><button data-i="marines">Marine response</button><button data-i="road">Damage road</button><button data-i="money">Add 50k credits</button><button data-i="scram" class="danger">Reactor SCRAM</button><button id="reset" class="danger">Found new colony</button></div></details>
 </section>
</aside>
<script type="module">
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';

// ---------- state, polling, controls ----------
let ADMIN = new URLSearchParams(location.search).get('admin') || localStorage.getItem('hh_admin') || '';
if (ADMIN) localStorage.setItem('hh_admin', ADMIN);
let G = null, S = null, prevS = null, lastPoll = 0, pollGap = 300;
const tokenEl = document.getElementById('token'), tokenState = document.getElementById('tokenstate');
tokenEl.value = ADMIN;
async function checkToken(){ const r = await (await fetch('/cmd', {method:'POST', body: JSON.stringify({cmd:'auth', token: ADMIN})})).json(); tokenState.textContent = !r.protected ? 'open server' : (r.ok ? 'control enabled' : 'view only'); tokenState.className = r.ok ? 'ok' : 'warn'; }
document.getElementById('tokenbtn').onclick = () => { ADMIN = tokenEl.value.trim(); localStorage.setItem('hh_admin', ADMIN); checkToken(); };
checkToken();
const post = async (o) => { const r = await fetch('/cmd', {method:'POST', body: JSON.stringify({...o, token: ADMIN})}); if(r.status===403){ tokenState.textContent='view only: paste the admin token above'; tokenState.className='bad'; } };
document.getElementById('pause').onclick = () => post({cmd:'pause'});
document.querySelectorAll('button[data-i]').forEach(b => b.onclick = async () => { const r = await fetch('/cmd', {method:'POST', body: JSON.stringify({cmd:'inject', value:b.dataset.i, token: ADMIN})}); if(r.status===403){ toast('view only: paste the admin token'); return; } const info=await r.json(); toast(info.text||b.dataset.i); if(info.x!==undefined && G) flyTo(info.x, info.y, 420); });
function toast(text){ const t=document.getElementById('toast'); t.textContent=text; t.style.display='block'; clearTimeout(t._h); t._h=setTimeout(()=>{ t.style.display='none'; }, 3500); }
document.getElementById('reset').onclick = () => { if(confirm('Abandon this colony and found a new one? History is kept.')) { post({cmd:'reset'}); selected=null; } };
const speedEl = document.getElementById('speed'), speedV = document.getElementById('speedv');
const sliderToSpeed = v => v===0?0:Math.round(Math.exp(Math.log(600) * v / 100));
const speedToSlider = s => s<=0?0:Math.round(Math.log(Math.max(1, s)) / Math.log(600) * 100);
speedEl.oninput = () => { speedV.textContent = sliderToSpeed(+speedEl.value) + ' min/s'; };
speedEl.onchange = () => post({cmd:'speed', value: sliderToSpeed(+speedEl.value)});
const layers = {}; document.querySelectorAll('#layers input').forEach(c => { layers[c.dataset.l] = c.checked; c.onchange = () => { layers[c.dataset.l] = c.checked; applyLayers(); }; });

function selectPanel(name){document.querySelectorAll('[data-panel]').forEach(b=>{const on=b.dataset.panel===name;b.setAttribute('aria-selected',String(on));b.tabIndex=on?0:-1;});document.querySelectorAll('.hud-panel').forEach(p=>p.hidden=p.id!=='panel-'+name);}
document.querySelectorAll('[data-panel]').forEach(b=>{b.onclick=()=>selectPanel(b.dataset.panel);b.onkeydown=e=>{const names=['overview','layers','places','operations'];if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();let i=names.indexOf(b.dataset.panel);i=e.key==='Home'?0:e.key==='End'?3:(i+(e.key==='ArrowRight'?1:3))%4;selectPanel(names[i]);document.querySelector('[data-panel="'+names[i]+'"]').focus();}};});
document.getElementById('panel-toggle').onclick=()=>{const hidden=document.body.classList.toggle('panel-collapsed');document.getElementById('panel-toggle').setAttribute('aria-expanded',String(!hidden));resize();};
const VIEW_PRESETS={colony:{power:true,packets:true,underground:false,nonet:false,ups:false,heater:false,ctrl:false,labels:false},water:{power:false,packets:false,underground:true,water:true,nonet:false,ups:false,ctrl:false,labels:false},power:{power:true,packets:false,underground:false,nonet:false,ups:true,ctrl:false,labels:false},network:{power:false,packets:true,underground:false,nonet:true,ups:false,ctrl:true,labels:false}};
function updateMapKey(){const items=[];const add=(color,label)=>items.push(`<span><i style="--swatch:${color}"></i>${label}</span>`);
 if(layers.underground){add('#4b9bb9','Potable');add('#b99865','Sanitary');add('#71988b','Storm');if(layers.water)add('#c8f6ff','Flow direction');}
 if(layers.power)add('#f2c14e','3φ power / moving load');if(layers.packets)add('#4fd1c5','Fibre / data packets');if(layers.water&&!layers.underground){add('#64c6d4','Water / direction of flow');add('#b6dfff','Ice / supply blocked');}if(layers.issues)add('#e2574d','Fault');if(layers.nonet)add('#d98082','Offline');if(layers.ups)add('#4fd1c5','UPS');
 if(!layers.underground&&!layers.power&&!layers.packets){add('#a7af94','Habitat');add('#ffd18c','Lighting');}
 document.getElementById('map-key').innerHTML=items.join('');
}
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{Object.assign(layers,VIEW_PRESETS[b.dataset.view]);document.querySelectorAll('#layers input').forEach(c=>c.checked=!!layers[c.dataset.l]);document.querySelectorAll('[data-view]').forEach(t=>t.setAttribute('aria-pressed',String(t===b)));applyLayers();});
document.querySelectorAll('#layers input').forEach(c=>c.addEventListener('change',()=>{document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed','false'));updateMapKey();}));
document.addEventListener('keydown',e=>{if(e.target.matches('input,textarea,select')||e.ctrlKey||e.metaKey||e.altKey)return;const k=e.key.toLowerCase();if(k==='m'){document.getElementById('panel-toggle').click();}if(k==='c'){const box=document.querySelector('[data-l="cutaway"]');box.checked=!box.checked;box.dispatchEvent(new Event('change'));}if('1234'.includes(k)&&k.length===1)document.querySelectorAll('[data-view]')[+k-1].click();});
function sectorCards(s){const total=G.houses.x.length/G.cfg.sectors;document.getElementById('sector-cards').innerHTML=s.sectors.map((x,i)=>`<button class="sector-card" data-district="${i}" title="Fly to district ${i+1}"><strong>District ${String(i+1).padStart(2,'0')} <span class="${x.min_t<0?'bad':x.avg_t<15?'warn':'ok'}">${x.avg_t}°</span></strong><small>Power ${x.power_ok}/${total} · Water ${x.water_ok}/${total}</small><span class="service-bars" aria-hidden="true"><span class="${x.power_ok===total?'good':'warn'}"></span><span class="${x.water_ok===total?'good':'warn'}"></span><span class="${x.net_ok===total?'good':'warn'}"></span></span></button>`).join('');}
document.getElementById('sector-cards').onclick=e=>{const b=e.target.closest('[data-district]');if(b)flyTo(...polar(+b.dataset.district*60+30,420),380);};

async function loadGeom(){ G = await (await fetch('/geometry')).json();TER={hub:G.cfg.hub_radius,row0:G.cfg.house_radius_min,step:G.cfg.house_ring_step,rows:G.cfg.house_rows,ring:G.cfg.ring_road_radius,wall:G.cfg.wall_radius}; }
async function poll(){
  try { const s = await (await fetch('/state')).json(); const first = !S; prevS = S; S = s; const now=performance.now(); pollGap = lastPoll ? Math.min(1200, now-lastPoll) : 300; lastPoll = now; renderSide(s); onState(s, first); renderInfo(); }
  catch(e) { console.error('poll failed', e); document.getElementById('banner').textContent = 'update failed: '+(e&&e.message||e); }
  setTimeout(poll, 300);
}

// ---------- planet helpers ----------
const RP = 3200;
const UP = new THREE.Vector3(0,1,0);
let TER={hub:140, row0:300, step:60, rows:5, ring:640, wall:690};
const sstep=(e0,e1,t)=>{ t=Math.min(1,Math.max(0,(t-e0)/(e1-e0))); return t*t*(3-2*t); };
function terrainH(x,y){ const r=Math.hypot(x,y); const T=TER; let h;
  if(r<T.hub) h=8.0; else if(r<T.row0-30) h=8.0-3.0*sstep(T.hub,T.row0-30,r);                                   // hub on a mound, sloping to the first street
  else if(r<T.ring){ const k=Math.floor((r-(T.row0-30))/T.step); const f=(r-(T.row0-30))/T.step-k; h=5.0+k*3.4+3.4*sstep(0.62,1.0,f); }   // terraces, one per row of houses
  else if(r<T.wall+20) h=5.0+T.rows*3.4; else h=(5.0+T.rows*3.4)*(1-sstep(T.wall+20,T.wall+260,r));                // outside the wall the ground eases down
  let natural=22+24*Math.sin(x*.0018)*Math.cos(y*.0024)+14*Math.sin(x*.004+y*.001);for(const [px,py,height,width] of [[1250,850,180,280],[-450,-1350,145,360],[-1640,980,220,310],[450,1650,190,330]])natural+=height*Math.exp(-((x-px)**2+(y-py)**2)/(width*width));return coastHeight(x,y,h+sstep(T.wall+20,T.wall+320,r)*natural+0.5*Math.sin(x*0.031)*Math.cos(y*0.027)); }
function sph(x, y, h=0){ const d=Math.hypot(x,y), th=d/RP, ph=Math.atan2(y,x), r=RP+h+terrainH(x,y); return new THREE.Vector3(r*Math.sin(th)*Math.cos(ph), r*Math.cos(th), r*Math.sin(th)*Math.sin(ph)); }
function quatAt(x, y, yaw=0){ const n=sph(x,y).normalize(); const q=new THREE.Quaternion().setFromUnitVectors(UP, n); if(yaw) q.multiply(new THREE.Quaternion().setFromAxisAngle(UP, yaw)); return q; }
function polar(a, r){ const t=a*Math.PI/180; return [r*Math.cos(t), r*Math.sin(t)]; }
function subdiv(pts, step=14){ const out=[]; for(let i=0;i<pts.length-1;i++){ const [x0,y0]=pts[i],[x1,y1]=pts[i+1]; const n=Math.max(1,Math.ceil(Math.hypot(x1-x0,y1-y0)/step)); for(let k=0;k<n;k++) out.push([x0+(x1-x0)*k/n, y0+(y1-y0)*k/n]); } out.push(pts[pts.length-1]); return out; }
function arcPts(a0, a1, r, n=24){ const out=[]; for(let i=0;i<=n;i++) out.push(polar(a0+(a1-a0)*i/n, r)); return out; }
function offsetArc(a0,a1,r,off,n=24){ return arcPts(a0,a1,r+off,n); }

function ribbon(flat, width, h, color, opts={}){
  const pts = subdiv(flat, 10); const pos=[], idx=[],uv=[];let distance=0;
  for(let i=0;i<pts.length;i++){ const p=pts[i], q=pts[Math.min(i+1,pts.length-1)], o=pts[Math.max(i-1,0)]; let dx=q[0]-o[0], dy=q[1]-o[1]; const L=Math.hypot(dx,dy)||1; dx/=L; dy/=L; const nx=-dy*width/2, ny=dx*width/2;
    if(i)distance+=Math.hypot(p[0]-pts[i-1][0],p[1]-pts[i-1][1]);uv.push(0,distance/4,width/4,distance/4);
    const a=sph(p[0]+nx,p[1]+ny,h), b=sph(p[0]-nx,p[1]-ny,h); pos.push(a.x,a.y,a.z,b.x,b.y,b.z); if(i<pts.length-1){ const k=i*2; idx.push(k,k+2,k+1, k+1,k+2,k+3); } }
  const g=new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos,3)); g.setAttribute('uv',new THREE.Float32BufferAttribute(uv,2));g.setIndex(idx); g.computeVertexNormals();
  const m=new THREE.Mesh(g, new THREE.MeshStandardMaterial({color, roughness:1, metalness:0, polygonOffset:true, polygonOffsetFactor:-1, ...opts})); world.add(m); return m;
}
function tube(pts3, radius, color, opts={}){ const g=new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts3), Math.max(8, pts3.length*3), radius, 6, false); const m=new THREE.Mesh(g, new THREE.MeshStandardMaterial({color, roughness:.5, metalness:.3, ...opts})); world.add(m); return m; }
function cap(radius, h, color, rings=24, segs=96, bump=0, cx=0, cy=0){ const pos=[], idx=[]; for(let r=0;r<=rings;r++){ const rr=radius*r/rings; for(let s=0;s<segs;s++){ const [x,y]=polar(s*360/segs, rr); const b=bump*(Math.sin(x*0.07)*Math.cos(y*0.05)+0.6*Math.sin(x*0.19+y*0.13)); const p=sph(x+cx,y+cy,h+b); pos.push(p.x,p.y,p.z); } }
  for(let r=0;r<rings;r++) for(let s=0;s<segs;s++){ const a=r*segs+s, b=r*segs+(s+1)%segs, c2=(r+1)*segs+s, d=(r+1)*segs+(s+1)%segs; idx.push(a,c2,b, b,c2,d); }
  const g=new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos,3)); g.setIndex(idx); g.computeVertexNormals(); const m=new THREE.Mesh(g, new THREE.MeshStandardMaterial({color, roughness:1, side:THREE.DoubleSide})); m.receiveShadow=true; world.add(m); return m; }
function road(flat,width,h,color){return markedRoad(flat,width,h);}
const pipeTex=(()=>{ const c=document.createElement('canvas'); c.width=64; c.height=8; const x=c.getContext('2d'); x.fillStyle='#3a78c8'; x.fillRect(0,0,64,8); x.fillStyle='#bfe0ff'; x.fillRect(0,0,14,8); x.fillStyle='#7ab8ff'; x.fillRect(14,0,10,8); const t=new THREE.CanvasTexture(c); t.wrapS=THREE.RepeatWrapping; t.wrapT=THREE.ClampToEdgeWrapping; return t; })();
const pipeMats=[];
function flowTube(pts3, radius, len){ const t=pipeTex.clone(); t.needsUpdate=true; t.repeat.set(Math.max(1,len/40),1); const mat=new THREE.MeshStandardMaterial({map:t, roughness:.4, metalness:.3}); mat.userData={rate:0, tex:t}; pipeMats.push(mat); const g=new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts3), Math.max(8, pts3.length*3), radius, 8, false); const m=new THREE.Mesh(g, mat); m.castShadow=true; world.add(m); return m; }
function polyLen(pts3){ let L=0; for(let i=1;i<pts3.length;i++) L+=pts3[i].distanceTo(pts3[i-1]); return L; }
function flat3(flat, h){ return subdiv(flat, 20).map(p=>sph(p[0],p[1],h)); }
function catenary(a3, b3, sag){ const out=[]; const mid=a3.clone().add(b3).multiplyScalar(0.5); const n=mid.clone().normalize(); for(let i=0;i<=8;i++){ const t=i/8; const p=a3.clone().lerp(b3,t); p.addScaledVector(n, -sag*4*t*(1-t)); out.push(p); } return out; }

class LineLayer {   // many 3D polylines, colour per polyline
  constructor(polylines3, baseColor){ this.ranges=[]; const pos=[], col=[]; const c=new THREE.Color(baseColor);
    for(const pts of polylines3){ const start=pos.length/3; for(let i=0;i<pts.length-1;i++){ const a=pts[i], b=pts[i+1]; pos.push(a.x,a.y,a.z,b.x,b.y,b.z); col.push(c.r,c.g,c.b,c.r,c.g,c.b); } this.ranges.push([start, pos.length/3]); }
    const g=new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos,3)); g.setAttribute('color', new THREE.Float32BufferAttribute(col,3));
    this.mesh=new THREE.LineSegments(g, new THREE.LineBasicMaterial({vertexColors:true})); this.polylines=polylines3; this.mesh.frustumCulled=false; world.add(this.mesh); }
  setColor(i, color){ const c=new THREE.Color(color), a=this.mesh.geometry.attributes.color; const [s,e]=this.ranges[i]; for(let k=s;k<e;k++) a.setXYZ(k,c.r,c.g,c.b); a.needsUpdate=true; }
}
class FlowLayer {   // dots moving along 3D polylines
  constructor(polylines3, color, size, perLine=3, speed=40){ this.pls=polylines3.map(pts=>{ const cum=[0]; for(let i=1;i<pts.length;i++) cum.push(cum[i-1]+pts[i].distanceTo(pts[i-1])); return {pts,cum,len:cum[cum.length-1]}; });
    this.active=new Array(polylines3.length).fill(false); this.per=perLine; this.speed=speed; const n=polylines3.length*perLine;
    const g=new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(n*3),3));
    this.mesh=new THREE.Points(g, new THREE.PointsMaterial({color, size, map:TEX.dot, transparent:true, depthWrite:false, sizeAttenuation:true})); this.mesh.frustumCulled=false; world.add(this.mesh); }
  update(t){ const a=this.mesh.geometry.attributes.position; let k=0; for(let i=0;i<this.pls.length;i++){ const pl=this.pls[i]; for(let j=0;j<this.per;j++){ if(!this.active[i]||pl.len===0){ a.setXYZ(k++, 0,-99999,0); continue; } const u=((t*this.speed/pl.len)+j/this.per)%1; const p=sample(pl,u); a.setXYZ(k++, p.x,p.y,p.z); } } a.needsUpdate=true; }
}
function sample(pl, u){ const d=u*pl.len; let i=1; while(i<pl.cum.length-1 && pl.cum[i]<d) i++; const t=(d-pl.cum[i-1])/((pl.cum[i]-pl.cum[i-1])||1); return pl.pts[i-1].clone().lerp(pl.pts[i], t); }

// ---------- textures and sprites ----------
function tex(draw){ const c=document.createElement('canvas'); c.width=c.height=64; draw(c.getContext('2d')); return new THREE.CanvasTexture(c); }
const TEX = {
  dot: tex(x=>{ const g=x.createRadialGradient(32,32,2,32,32,30); g.addColorStop(0,'rgba(255,255,255,1)'); g.addColorStop(0.5,'rgba(255,255,255,.6)'); g.addColorStop(1,'rgba(255,255,255,0)'); x.fillStyle=g; x.fillRect(0,0,64,64); }),
  glow: tex(x=>{ const g=x.createRadialGradient(32,32,0,32,32,32); g.addColorStop(0,'rgba(255,240,180,.9)'); g.addColorStop(0.3,'rgba(255,220,120,.35)'); g.addColorStop(1,'rgba(255,200,80,0)'); x.fillStyle=g; x.fillRect(0,0,64,64); }),
  bang: tex(x=>{ x.fillStyle='#e2574d'; x.beginPath(); x.arc(32,32,26,0,7); x.fill(); x.fillStyle='#fff'; x.font='bold 40px sans-serif'; x.textAlign='center'; x.textBaseline='middle'; x.fillText('!',32,34); }),
  diamond: tex(x=>{ x.fillStyle='#ff3b3b'; x.beginPath(); x.moveTo(32,4); x.lineTo(60,32); x.lineTo(32,60); x.lineTo(4,32); x.closePath(); x.fill(); x.fillStyle='#200'; x.beginPath(); x.arc(32,32,7,0,7); x.fill(); }),
  bolt: tex(x=>{ x.fillStyle='#4fd1c5'; x.beginPath(); x.arc(32,32,28,0,7); x.fill(); x.fillStyle='#062'; x.beginPath(); x.moveTo(36,6); x.lineTo(18,36); x.lineTo(31,36); x.lineTo(27,58); x.lineTo(46,26); x.lineTo(33,26); x.closePath(); x.fill(); }),
  nonet: tex(x=>{ x.fillStyle='#d857d8'; x.beginPath(); x.arc(32,32,26,0,7); x.fill(); x.strokeStyle='#fff'; x.lineWidth=6; x.beginPath(); x.moveTo(18,18); x.lineTo(46,46); x.moveTo(46,18); x.lineTo(18,46); x.stroke(); }),
  person: tex(x=>{ x.fillStyle='#ffffff'; x.beginPath(); x.arc(32,16,8,0,7); x.fill(); x.beginPath(); x.roundRect(22,28,20,32,8); x.fill(); }),
  marine: tex(x=>{ x.fillStyle='#8be05a'; x.beginPath(); x.arc(32,16,8,0,7); x.fill(); x.beginPath(); x.roundRect(22,28,20,32,8); x.fill(); x.fillStyle='#233'; x.fillRect(10,40,44,6); }),
  flame: tex(x=>{ x.fillStyle='#ff7a30'; x.beginPath(); x.moveTo(32,6); x.bezierCurveTo(50,26,50,44,32,58); x.bezierCurveTo(14,44,14,26,32,6); x.fill(); }),
  rad: tex(x=>{ x.fillStyle='#e8d34a'; x.beginPath(); x.arc(32,32,28,0,7); x.fill(); x.fillStyle='#222'; for(let k=0;k<3;k++){ x.beginPath(); x.moveTo(32,32); x.arc(32,32,24, k*2.094+0.35, k*2.094+1.4); x.closePath(); x.fill(); } x.beginPath(); x.arc(32,32,5,0,7); x.fill(); }),
  steam: tex(x=>{ const g=x.createRadialGradient(32,32,0,32,32,30); g.addColorStop(0,'rgba(230,235,245,.55)'); g.addColorStop(1,'rgba(230,235,245,0)'); x.fillStyle=g; x.fillRect(0,0,64,64); }),
  red: tex(x=>{ const g=x.createRadialGradient(32,32,0,32,32,30); g.addColorStop(0,'rgba(255,60,60,1)'); g.addColorStop(0.4,'rgba(255,60,60,.5)'); g.addColorStop(1,'rgba(255,60,60,0)'); x.fillStyle=g; x.fillRect(0,0,64,64); }),
};
const spriteCache=new Map();
function textSprite(text, color='#d9dde6', px=28){ const key=text+'|'+color+'|'+px; if(!spriteCache.has(key)){ const c=document.createElement('canvas'); const x=c.getContext('2d'); x.font=`600 ${px}px sans-serif`; const w=Math.ceil(x.measureText(text).width)+16; c.width=w; c.height=px+14; const x2=c.getContext('2d'); x2.font=`600 ${px}px sans-serif`; x2.fillStyle='rgba(10,12,18,.78)'; x2.beginPath(); x2.roundRect(0,0,w,px+14,8); x2.fill(); x2.fillStyle=color; x2.textBaseline='middle'; x2.fillText(text,8,(px+14)/2); spriteCache.set(key, {map:new THREE.CanvasTexture(c), w, h:px+14}); }
  const e=spriteCache.get(key); const s=new THREE.Sprite(new THREE.SpriteMaterial({map:e.map, transparent:true, depthTest:false})); s.scale.set(e.w/px*4.6, 4.6*e.h/px, 1); s.userData.px=px; return s; }
function retext(sprite, text, color){ const key=text+'|'+color+'|'+sprite.userData.px; if(sprite.userData.key===key) return; sprite.userData.key=key; const tmp=textSprite(text,color,sprite.userData.px); sprite.material.map=tmp.material.map; sprite.material.needsUpdate=true; sprite.scale.copy(tmp.scale); }

// ---------- scene ----------
const mapEl=document.getElementById('map');
const renderer=new THREE.WebGLRenderer({antialias:true}); renderer.setPixelRatio(Math.min(devicePixelRatio,2)); renderer.shadowMap.enabled=true; renderer.shadowMap.type=THREE.PCFSoftShadowMap; renderer.toneMapping=THREE.ACESFilmicToneMapping; renderer.toneMappingExposure=1.05; mapEl.appendChild(renderer.domElement);
const scene=new THREE.Scene(); scene.background=new THREE.Color(0x05070b);
const camera=new THREE.PerspectiveCamera(50,1,.15,80000); camera.position.set(360, RP+1050, 1180);
const controls=new OrbitControls(camera, renderer.domElement); controls.target.set(0,RP,0); controls.minDistance=.7; controls.maxDistance=RP*4; controls.enablePan=true; controls.screenSpacePanning=true; controls.panSpeed=1.35; controls.zoomSpeed=.65; controls.enableDamping=true; controls.dampingFactor=0.1; controls.keyPanSpeed=40; 
controls.mouseButtons={LEFT:THREE.MOUSE.PAN,MIDDLE:THREE.MOUSE.PAN,RIGHT:THREE.MOUSE.ROTATE};controls.touches={ONE:THREE.TOUCH.PAN,TWO:THREE.TOUCH.DOLLY_ROTATE};
const composer=new EffectComposer(renderer); composer.addPass(new RenderPass(scene,camera)); const bloomPass=new UnrealBloomPass(new THREE.Vector2(800,600), 0.45, 0.5, 0.86); composer.addPass(bloomPass);
const cameraKeys=new Set();let cameraLast=performance.now();
function updateCameraMotion(now){
 const dt=Math.min(.05,(now-cameraLast)/1000);cameraLast=now;if(!cameraKeys.size)return;
 const distance=camera.position.distanceTo(controls.target),speed=Math.max(2.5,distance*.85)*(cameraKeys.has('shift')?4:1)*dt;
 const right=new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld,0),up=new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld,1),vertical=camera.position.clone().normalize(),move=new THREE.Vector3();
 if(cameraKeys.has('a')||cameraKeys.has('arrowleft'))move.addScaledVector(right,-1);
 if(cameraKeys.has('d')||cameraKeys.has('arrowright'))move.add(right);
 if(cameraKeys.has('w')||cameraKeys.has('arrowup'))move.add(up);
 if(cameraKeys.has('s')||cameraKeys.has('arrowdown'))move.addScaledVector(up,-1);
 if(cameraKeys.has('q'))move.addScaledVector(vertical,-1);if(cameraKeys.has('e'))move.add(vertical);
 if(move.lengthSq()){move.normalize().multiplyScalar(speed);camera.position.add(move);controls.target.add(move);flyAnim=null;}
}
window.addEventListener('keydown',e=>{if(e.target.matches('input,textarea,select')||e.ctrlKey||e.metaKey)return;const key=e.key.toLowerCase();if(['w','a','s','d','q','e','shift','arrowleft','arrowright','arrowup','arrowdown'].includes(key)){e.preventDefault();cameraKeys.add(key);}if(key==='f')focusSelection();});
window.addEventListener('keyup',e=>cameraKeys.delete(e.key.toLowerCase()));window.addEventListener('blur',()=>cameraKeys.clear());
renderer.domElement.addEventListener('wheel',e=>{
 e.preventDefault();e.stopImmediatePropagation();flyAnim=null;
 const rect=renderer.domElement.getBoundingClientRect(),cursor=new THREE.Vector2((e.clientX-rect.left)/rect.width*2-1,-(e.clientY-rect.top)/rect.height*2+1),r=new THREE.Raycaster();r.setFromCamera(cursor,camera);
 const direction=camera.getWorldDirection(new THREE.Vector3()),plane=new THREE.Plane().setFromNormalAndCoplanarPoint(direction,controls.target),anchor=r.ray.intersectPlane(plane,new THREE.Vector3())||controls.target.clone();
 const delta=e.deltaY*(e.deltaMode===1?16:e.deltaMode===2?rect.height:1),distance=camera.position.distanceTo(controls.target),next=THREE.MathUtils.clamp(distance*Math.exp(THREE.MathUtils.clamp(delta,-180,180)*.0018),.7,RP*4),ratio=next/Math.max(distance,.001);
 camera.position.sub(anchor).multiplyScalar(ratio).add(anchor);controls.target.sub(anchor).multiplyScalar(ratio).add(anchor);controls.update();
},{passive:false,capture:true});
function focusPoint(point,distance=12,normal=null){
 const direction=normal?normal.clone().normalize():camera.position.clone().sub(controls.target).normalize();
 flyAnim={from:camera.position.clone(),to:point.clone().addScaledVector(direction,distance),tfrom:controls.target.clone(),tto:point.clone(),t0:performance.now()};
}
function focusSelection(){
 if(!selected)return;
 if(selected.kind==='pole'){const meter=cabinetMeters[selected.id];focusPoint(meter.position,3,new THREE.Vector3(0,.15,1).applyQuaternion(meter.quaternion));return;}
 if(selected.kind==='house'){const h=houseShells[selected.id],dim=DIM[G.houses.type[selected.id]];focusPoint(h.base.clone().addScaledVector(h.base.clone().normalize(),dim[1]/2),Math.max(dim[0],dim[2])*1.5);return;}
 const obj=clickables.find(o=>o.userData.click?.id===selected.id);if(obj){const bounds=new THREE.Box3().setFromObject(obj),center=bounds.getCenter(new THREE.Vector3());focusPoint(center,Math.max(8,bounds.getSize(new THREE.Vector3()).length()*1.2));}
}

scene.add(new THREE.AmbientLight(0xa8b0c4, 1.35)); scene.add(new THREE.HemisphereLight(0x778ab0, 0x2a2118, 1.2));
const sun=new THREE.DirectionalLight(0xffe0b0, 1.3); scene.add(sun); sun.castShadow=true; sun.shadow.mapSize.set(2048,2048); sun.shadow.camera.near=100; sun.shadow.camera.far=30000; sun.shadow.bias=-0.0008; sun.shadow.normalBias=.12;
const sunTarget=new THREE.Object3D(); scene.add(sunTarget); sun.target=sunTarget; const sunSprite=new THREE.Sprite(new THREE.SpriteMaterial({map:TEX.glow, transparent:true, depthTest:false})); sunSprite.scale.set(1800,1800,1); scene.add(sunSprite);
{ const n=3000, p=new Float32Array(n*3); for(let i=0;i<n;i++){ const v=new THREE.Vector3().randomDirection().multiplyScalar(60000); p.set([v.x,v.y,v.z], i*3); } const g=new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(p,3)); scene.add(new THREE.Points(g, new THREE.PointsMaterial({color:0xbfc8dc, size:2.2, sizeAttenuation:false}))); }
// planet: procedural terrain baked once on the CPU (value noise, ridges, craters; flat under the colony),
// shaded in a fragment shader: rock, snow by height and cold, colony glow on the night side, rim light.
function makePlanet(){
  const hash=(x,y,z)=>{ const s=Math.sin(x*127.1+y*311.7+z*74.7)*43758.5453; return s-Math.floor(s); };
  const lerp=(a,b,t)=>a+(b-a)*t;
  const noise=(x,y,z)=>{ const i=Math.floor(x), j=Math.floor(y), k=Math.floor(z); const fx=x-i, fy=y-j, fz=z-k; const u=fx*fx*(3-2*fx), v=fy*fy*(3-2*fy), w=fz*fz*(3-2*fz);
    const c=(a,b,c2)=>hash(i+a,j+b,k+c2); return lerp(lerp(lerp(c(0,0,0),c(1,0,0),u),lerp(c(0,1,0),c(1,1,0),u),v), lerp(lerp(c(0,0,1),c(1,0,1),u),lerp(c(0,1,1),c(1,1,1),u),v), w)*2-1; };
  const fbm=(x,y,z,o=6)=>{ let val=0, amp=0.5, f=1; for(let q=0;q<o;q++){ val+=amp*noise(x*f+1.7*q,y*f+9.2*q,z*f+3.1*q); f*=2.03; amp*=0.5; } return val; };
  const craters=(x,y,z)=>{ let c=0; for(let q=0;q<2;q++){ const s=2+q*3; const qx=x*s,qy=y*s,qz=z*s; const cx=Math.floor(qx),cy=Math.floor(qy),cz=Math.floor(qz); const h1=hash(cx,cy,cz),h2=hash(cx+7,cy+3,cz+1),h3=hash(cx+2,cy+9,cz+5); const fx=qx-cx-0.5+(h2-0.5)*0.4, fy=qy-cy-0.5+(h3-0.5)*0.4, fz=qz-cz-0.5; const r=0.18+0.22*h1; const d=Math.sqrt(fx*fx+fy*fy+fz*fz); const sm=(e0,e1,t)=>{ t=Math.min(1,Math.max(0,(t-e0)/(e1-e0))); return t*t*(3-2*t); }; const rim=sm(r,r*0.75,d)*(1-sm(r*0.75,r*0.35,d))*0.5; const bowl=sm(r*0.75,0,d); c+=(rim-bowl*0.8)*(0.5+0.5*h1)/(1+q); } return c; };
  const colonyAngle=1500/RP;
  const geo=new THREE.SphereGeometry(RP,256,192); const pos=geo.attributes.position; const hArr=new Float32Array(pos.count); const AMP=90;
  for(let i=0;i<pos.count;i++){ const x=pos.getX(i),y=pos.getY(i),z=pos.getZ(i); const L=Math.hypot(x,y,z); const nx=x/L,ny=y/L,nz=z/L; const ang=Math.acos(Math.max(-1,Math.min(1,ny)));
    const mask=1-Math.min(1,Math.max(0,(ang-colonyAngle)/(colonyAngle*0.6))); const m=mask*mask*(3-2*mask);
    const h=(fbm(nx*3,ny*3,nz*3)*1.0 + (1-Math.abs(noise(nx*7,ny*7,nz*7)))*0.35 + craters(nx,ny,nz)*0.5 + fbm(nx*22,ny*22,nz*22,3)*0.08)*(1-m);
    const dist=ang*RP,az=Math.atan2(nz,nx),local=terrainH(dist*Math.cos(az),dist*Math.sin(az)),height=dist<3750?local-45:THREE.MathUtils.lerp(local-45,h*AMP,sstep(3750,4100,dist));hArr[i]=height/AMP; const r=RP+height; pos.setXYZ(i,nx*r,ny*r,nz*r); }
  geo.setAttribute('aH', new THREE.BufferAttribute(hArr,1)); geo.computeVertexNormals();
  const mat=new THREE.ShaderMaterial({
    uniforms:{ uSun:{value:new THREE.Vector3(1,0.3,0)}, uColony:{value:new THREE.Vector3(0,1,0)}, uCold:{value:0.6}, uStorm:{value:0.0}, uTime:{value:0}, uColonyAngle:{value:colonyAngle} },
    vertexShader:`attribute float aH; varying vec3 vN; varying vec3 vP; varying float vH; void main(){ vN=normalize(normalMatrix*normal); vP=(modelMatrix*vec4(position,1.0)).xyz; vH=aH; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }`,
    fragmentShader:`uniform vec3 uSun; uniform vec3 uColony; uniform float uCold; uniform float uStorm; uniform float uTime; uniform float uColonyAngle;
      varying vec3 vN; varying vec3 vP; varying float vH;
      float hash(vec3 p){ return fract(sin(dot(p,vec3(127.1,311.7,74.7)))*43758.5453); }
      float vnoise(vec3 p){ vec3 i=floor(p), f=fract(p); vec3 u=f*f*(3.0-2.0*f); return mix(mix(mix(hash(i),hash(i+vec3(1,0,0)),u.x),mix(hash(i+vec3(0,1,0)),hash(i+vec3(1,1,0)),u.x),u.y),mix(mix(hash(i+vec3(0,0,1)),hash(i+vec3(1,0,1)),u.x),mix(hash(i+vec3(0,1,1)),hash(i+vec3(1,1,1)),u.x),u.y),u.z); }
      void main(){ vec3 n=normalize(vN); vec3 sn=normalize(vP); vec3 sd=normalize(uSun); float sun=max(dot(n,sd),0.0); float day=smoothstep(-0.15,0.25,dot(sn,sd));
        float grain=vnoise(sn*140.0)*0.6+vnoise(sn*900.0)*0.4;
        vec3 rock=mix(vec3(0.15,0.13,0.11), vec3(0.36,0.31,0.26), grain); rock=mix(rock, vec3(0.44,0.38,0.31), smoothstep(0.2,0.6,vH));
        float snow=smoothstep(0.30-0.35*uCold, 0.60-0.35*uCold, vH+0.25*(grain-0.5)) + 0.35*uStorm; float slope=1.0-max(dot(n,sn),0.0); snow*=1.0-smoothstep(0.25,0.6,slope*3.0); snow=clamp(snow,0.0,1.0);
        vec3 col=mix(rock, vec3(0.86,0.89,0.94), snow);
        float ang=acos(clamp(dot(sn,uColony),-1.0,1.0)); float glow=(1.0-smoothstep(uColonyAngle*0.8, uColonyAngle*2.2, ang))*(1.0-day);
        vec3 lit=col*(0.10+0.95*sun*day+0.07*(1.0-day)) + vec3(1.0,0.75,0.45)*glow*0.35;
        float rim=pow(1.0-max(dot(n,normalize(cameraPosition-vP)),0.0),3.0); lit+=vec3(0.25,0.35,0.55)*rim*0.5*(0.4+0.6*day);
        gl_FragColor=vec4(lit,1.0); }`
  });
  return new THREE.Mesh(geo, mat);
}
const planetMesh=makePlanet(); const planetMat=planetMesh.material; scene.add(planetMesh);scene.add(new THREE.Mesh(new THREE.SphereGeometry(RP-10,256,192),new THREE.MeshStandardMaterial({color:0x749da8,roughness:.42,metalness:.18})));
scene.add(new THREE.Mesh(new THREE.SphereGeometry(RP*1.035,64,48), new THREE.MeshBasicMaterial({color:0x4a6a9a, transparent:true, opacity:0.10, side:THREE.BackSide, depthWrite:false})));
// weather: snow and blizzard particles around the camera target, fog, a rare tornado
const weather={snow:null, snowVel:null, tornado:null, wind:8, precip:'none', storm:false, tornadoOn:false};
{ const n=6000, p=new Float32Array(n*3); for(let i=0;i<n;i++){ p[i*3]=(Math.random()-0.5)*1600; p[i*3+1]=Math.random()*500; p[i*3+2]=(Math.random()-0.5)*1600; }
  const g=new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(p,3)); weather.snow=new THREE.Points(g, new THREE.PointsMaterial({color:0xe8eef8, size:6, map:TEX.dot, transparent:true, opacity:0.0, depthWrite:false, sizeAttenuation:true})); weather.snow.frustumCulled=false; scene.add(weather.snow);
  weather.tornado=new THREE.Mesh(new THREE.CylinderGeometry(14,70,260,24,8,true), new THREE.MeshBasicMaterial({color:0x9aa3b5, transparent:true, opacity:0.0, side:THREE.DoubleSide, depthWrite:false})); weather.tornado.visible=false; scene.add(weather.tornado); }
scene.fog=new THREE.FogExp2(0x2a2e38, 0.0);
const world=new THREE.Group(); scene.add(world);
const labelGroup=new THREE.Group(); world.add(labelGroup);
const lod={near:[], mid:[]};
function addLabel(text, x, y, h, color, tier='mid', live=false){ const s=textSprite(text,color); s.position.copy(sph(x,y,h)); labelGroup.add(s); lod[tier].push(s); if(live) liveLabels.push(s); return s; }
const liveLabels=[];
const clickables=[];   // {obj, id, kind, extra}
function clickable(obj, id, kind, extra){ obj.traverse(o=>{ o.userData.click={id,kind,extra}; }); obj.userData.click={id,kind,extra}; clickables.push(obj); return obj; }
let housesMesh, windowsMesh, windowSlots=[], lockWedges=[], xenoPool=[], squadGroup=null, wallPanels=null, wallSegs=[], polesMesh, armsMesh, lampsMesh, wallMesh, benchMesh, spanLines, netLines, flowPower, flowWater, packetsPts, markers={}, gates=[], rovers={}, hub={}, complex={}, roadMeshes={ring:[]}, pipes={}, rpBoxes=[], cabBoxes=[];
const flatHouses=[]; let spanCurves=[], trunkCurves=[], towerCurves=[], solarCurves=[], feederCurves=[], waterMainPts=[], waterSectorPts=[], cableTowerCurves=[];

function box(x,y,w,h,d,color,edge,yaw){ const m=new THREE.Mesh(new THREE.BoxGeometry(w,h,d), new THREE.MeshStandardMaterial({color, roughness:.8})); m.position.copy(sph(x,y,h/2)); m.quaternion.copy(quatAt(x,y,yaw===undefined?-Math.atan2(y,x):yaw)); world.add(m); if(edge){ m.add(new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry), new THREE.LineBasicMaterial({color:edge}))); } return m; }
function cyl(x,y,r,h,color,opts={}){ const m=new THREE.Mesh(new THREE.CylinderGeometry(r,r,h,18), new THREE.MeshStandardMaterial({color, roughness:.7, ...opts})); m.position.copy(sph(x,y,h/2)); m.quaternion.copy(quatAt(x,y)); world.add(m); return m; }
function localGroup(x,y,h,yaw){ const g=new THREE.Group(); g.position.copy(sph(x,y,h)); g.quaternion.copy(quatAt(x,y,yaw||0)); world.add(g); return g; }
function pointsLayer(n, map, color, size, additive){ const g=new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(n*3).fill(-99999),3)); const m=new THREE.Points(g, new THREE.PointsMaterial({map, color, size, transparent:true, depthWrite:false, blending: additive?THREE.AdditiveBlending:THREE.NormalBlending, sizeAttenuation:true})); m.frustumCulled=false; world.add(m); return m; }
function setPoints(layer, flatPts, h){ const a=layer.geometry.attributes.position; const n=a.count; for(let i=0;i<n;i++){ if(i<flatPts.length){ const p=sph(flatPts[i][0],flatPts[i][1],h); a.setXYZ(i,p.x,p.y,p.z); } else a.setXYZ(i,0,-99999,0); } a.needsUpdate=true; }

// ---------- colony construction kit: batched geometry, deterministic detail ----------
const DIM=[[20,7.25,18],[16,10.65,18],[17,7.25,18],[20,10.65,20]];
const houseDetails=new Map(), houseShells=[], roofProxies=[];
let utilityGroup=new THREE.Group(), utilityBatches=[], utilityDrops=null, utilityPaths=[],utilityTime=0,utilityLastTime=0;
let streetDetail=new THREE.Group(), cityPlate=null, detailFrame=0;
world.add(utilityGroup,streetDetail);
const UNIT={box:new THREE.BoxGeometry(1,1,1),cyl:new THREE.CylinderGeometry(1,1,1,10),
  ball:new THREE.SphereGeometry(1,8,6),ring:new THREE.TorusGeometry(1,.13,5,12)};
const MAT={};
function material(name,color,opts={}){ if(!MAT[name]) MAT[name]=new THREE.MeshStandardMaterial({color,roughness:.78,...opts}); return MAT[name]; }
const M={
  roof:material('roof-slab',0x6e7775,{transparent:true,opacity:.84,depthWrite:false,side:THREE.DoubleSide,metalness:.5,roughness:.48}),
  steel:material('steel',0x465052,{metalness:.72,roughness:.48}),
  trim:material('trim',0x929c98,{metalness:.65,roughness:.38}),
  panel:material('panel',0x918e7c,{metalness:.35}),
  dark:material('dark',0x1d2528), concrete:material('concrete',0x696a60),
  brick:material('brick',0x716050), grout:material('grout',0x363a36),
  wood:material('wood',0x896a46), fabric:material('fabric',0x656e5a),
  white:material('white',0xc1c6ba), amber:material('amber',0xc99742),
  rubber:material('rubber',0x171d20), blue:material('blue',0x2e7083),
  glow:material('glow',0xffcf85,{emissive:0xffa849,emissiveIntensity:.7}),
  glass:new THREE.MeshPhysicalMaterial({color:0x9abcc1,metalness:.08,roughness:.12,transparent:true,
    opacity:.28,depthWrite:false,side:THREE.DoubleSide,envMapIntensity:1.5,clearcoat:1}),
  screen:material('screen',0x263e47,{emissive:0x386575,emissiveIntensity:.6})
};
// An inexpensive procedural environment provides view-dependent glass reflections.
{ const sky=new THREE.Scene(); sky.background=new THREE.Color(0x46535b);
  const a=new THREE.Mesh(new THREE.SphereGeometry(40,16,12),new THREE.MeshBasicMaterial({color:0x121b21,side:THREE.BackSide})); sky.add(a);
  for(let i=0;i<8;i++){ const p=new THREE.Mesh(new THREE.PlaneGeometry(7,18),new THREE.MeshBasicMaterial({color:i%2?0xa7b7b5:0xddd0ab,side:THREE.DoubleSide})); p.position.set(Math.sin(i)*25,8,Math.cos(i)*25); p.lookAt(0,0,0); sky.add(p); }
  const pmrem=new THREE.PMREMGenerator(renderer); const env=pmrem.fromScene(sky,.06); scene.environment=env.texture;
  sky.traverse(o=>{if(o.isMesh){o.geometry.dispose();o.material.dispose();}});pmrem.dispose(); }
class Kit {
  constructor(parent){ this.parent=parent;this.buckets=new Map(); }
  add(shape,mat,p,s=[1,1,1],rotation=null,color=null,tag=null){
    const key=shape+'|'+mat.uuid; if(!this.buckets.has(key))this.buckets.set(key,{shape,mat,items:[]});
    const q=rotation instanceof THREE.Quaternion?rotation:new THREE.Quaternion().setFromEuler(new THREE.Euler(...(rotation||[0,0,0])));
    const matrix=new THREE.Matrix4().compose(new THREE.Vector3(...p),q,new THREE.Vector3(...s));
    this.buckets.get(key).items.push({matrix,color,tag});
  }
  box(mat,x,y,z,w,h,d,rot=null,col=null){this.add('box',mat,[x,y,z],[w,h,d],rot,col);}
  pipe(mat,a,b,r,tag=null){ const p=new THREE.Vector3(...a),q=new THREE.Vector3(...b),delta=q.clone().sub(p);if(delta.length()<1e-5)return;
    this.add('cyl',mat,p.add(q).multiplyScalar(.5).toArray(),[r,delta.length(),r],new THREE.Quaternion().setFromUnitVectors(UP,delta.normalize()),null,tag); }
  finish(){const meshes=[];for(const {shape,mat,items} of this.buckets.values()){
    const mesh=new THREE.InstancedMesh(UNIT[shape],mat,items.length);
    items.forEach((v,i)=>{mesh.setMatrixAt(i,v.matrix);if(v.color!==null)mesh.setColorAt(i,new THREE.Color(v.color));});
    mesh.instanceMatrix.needsUpdate=true;mesh.castShadow=!mat.transparent;mesh.receiveShadow=true;mesh.userData.tags=items.map(v=>v.tag);
    mesh.computeBoundingSphere();this.parent.add(mesh);meshes.push(mesh);
  }return meshes;}
}
function patternTexture(kind){
 const c=document.createElement('canvas');c.width=c.height=256;const x=c.getContext('2d');let seed=814;
 const rnd=()=>{seed=(seed*16807)%2147483647;return seed/2147483647;};
 x.fillStyle=kind==='paving'?'#494b46':'#303637';x.fillRect(0,0,256,256);
 if(kind==='paving'){for(let row=0;row<16;row++)for(let col=-1;col<8;col++){const v=155+Math.floor(rnd()*35);x.fillStyle=`rgb(${v},${v+3},${v-3})`;x.fillRect(col*36+(row%2)*18+1,row*16+1,34,14);}}
 else for(let k=0;k<19000;k++){const v=35+rnd()*45;x.fillStyle=`rgba(${v},${v+3},${v+4},.5)`;x.fillRect(rnd()*256,rnd()*256,1,1);}
 const t=new THREE.CanvasTexture(c);t.wrapS=t.wrapT=THREE.RepeatWrapping;t.colorSpace=THREE.SRGBColorSpace;t.anisotropy=Math.min(8,renderer.capabilities.getMaxAnisotropy());return t;
}
const pavingTexture=patternTexture('paving'),asphaltTexture=patternTexture('asphalt');
function buildNeighborhood(){
 const n=G.houses.x.length,m4=new THREE.Matrix4();
 housesMesh=new THREE.InstancedMesh(UNIT.box,new THREE.MeshStandardMaterial({roughness:.8,transparent:true,opacity:0,depthWrite:false}),n);housesMesh.castShadow=true;world.add(housesMesh);
 const roofs=new THREE.InstancedMesh(UNIT.box,M.steel,n);roofs.visible=false;world.add(roofs);
 windowsMesh=new THREE.InstancedMesh(UNIT.box,M.glow,1);windowsMesh.count=0;world.add(windowsMesh);windowSlots=[];
 const trim=new Kit(world);
 for(let i=0;i<n;i++){
   const x=G.houses.x[i],y=G.houses.y[i],a=G.houses.angle[i]*Math.PI/180,[w,h,d]=DIM[G.houses.type[i]],yaw=-a-Math.PI/2;
   flatHouses.push([x,y]);const q=quatAt(x,y,yaw),base=sph(x,y,2.35);
   const matrix=new THREE.Matrix4().compose(base.clone().add(new THREE.Vector3(0,h/2,0).applyQuaternion(q)),q,new THREE.Vector3(w,h,d));
   housesMesh.setMatrixAt(i,matrix);housesMesh.setColorAt(i,new THREE.Color([0x898674,0x999786,0x7e8c85,0xb0a48a][G.houses.type[i]]));
   const rm=new THREE.Matrix4().compose(base.clone().add(new THREE.Vector3(0,h+.18,0).applyQuaternion(q)),q,new THREE.Vector3(w+.5,.36,d+.5));roofs.setMatrixAt(i,rm);
   roofProxies.push({mesh:roofs,matrix:rm});houseShells.push({matrix,base,q,yaw});
   // Silhouettes stay present at colony scale: rooftop HVAC, duct, parapet bands.
   for(const [p,scale,mat] of [[[w*.25,h+.85,-d*.15],[3.5,1.4,2.5],M.trim],
      [[-w*.28,h+.9,-d*.2],[.55,1.8,.55],M.steel]]){
     const pos=base.clone().add(new THREE.Vector3(...p).applyQuaternion(q));trim.add('box',mat,pos.toArray(),scale,q);
   }
 }
 mediumHomes();housesMesh.instanceMatrix.needsUpdate=true;roofs.instanceMatrix.needsUpdate=true;
}
function makeHouse(i){
 const [w,h,d]=DIM[G.houses.type[i]],type=G.houses.type[i],floors=Math.round((h-.45)/3.4);
 const g=new THREE.Group(),shell=new THREE.Group(),roof=new THREE.Group(),inside=new THREE.Group();g.add(shell,inside,roof);
 g.position.copy(houseShells[i].base);g.quaternion.copy(houseShells[i].q);world.add(g);
 const k=new Kit(shell),r=new Kit(roof),interiorKit=new Kit(inside),accent=[0xaaa18a,0x8d9e99,0xa58b62,0x788681][i%4];
 const floorH=(h-.45)/floors;
 k.box(M.concrete,0,-.4,0,w+.8,.8,d+.8);
 // Actual individual brick plinth, running bond, on all four sides.
 for(let side=0;side<4;side++){const width=side%2?d:w;for(let row=0;row<3;row++)for(let j=0;j<Math.floor(width/.62);j++){
   const along=-width/2+.31+j*.62+(row%2)*.29;if(along>width/2-.12)continue;
   const x=side===0?along:side===2?-along:(side===1?w/2:-w/2),z=side===0?d/2:side===2?-d/2:(side===1?-along:along);
   k.box(M.brick,x,-.69+row*.23,z,side%2?.24:.59,.205,side%2?.59:.24,null,0x756650+(i%3)*0x030303);
 }}
 // Hollow four-wall shell: prefab bays assembled around genuine glass apertures.
 for(let side=0;side<4;side++){
  const width=side%2?d:w,depth=side%2?w:d;
  const wall=(mat,u,v,ww,hh,thick=.22,offset=0)=>{
    const x=side===0?u:side===2?-u:(side===1?depth/2+offset:-depth/2-offset);
    const z=side===0?depth/2+offset:side===2?-depth/2-offset:(side===1?-u:u);
    k.box(mat,x,v,z,side%2?thick:ww,hh,side%2?ww:thick,null,mat===M.panel?accent:null);
  };
  const bays=Math.floor(width/3.2),bw=width/bays;
  for(let level=0;level<floors;level++)for(let b=0;b<bays;b++){
   const u=-width/2+(b+.5)*bw,y=level*floorH;const door=side===0&&b===Math.floor(bays/2)&&level===0;
   wall(M.steel,-width/2+b*bw,y+floorH/2,.14,floorH,.34,.05);
   if(door){wall(M.panel,u,y+floorH-.35,bw-.12,.7);wall(M.dark,u,1.23,1.65,2.46,.18,.04);
     wall(M.trim,u-1.02,1.23,.18,2.6,.32,.13);wall(M.trim,u+1.02,1.23,.18,2.6,.32,.13);
     wall(M.glass,u,1.7,.85,.5,.09,.15);wall(M.amber,u+.58,1.1,.11,.16,.2,.22);
     continue;}
   const sill=.85,wh=1.65,ww=bw-.6;
   wall(M.panel,u,y+sill/2,bw-.12,sill);wall(M.panel,u,y+(sill+wh+floorH)/2,bw-.12,floorH-sill-wh);
   wall(M.panel,u-bw/2+.18,y+sill+wh/2,.32,wh);wall(M.panel,u+bw/2-.18,y+sill+wh/2,.32,wh);
   wall(M.glass,u,y+sill+wh/2,ww,wh,.055,.04);
   for(const uu of [u-ww/2,u,u+ww/2])wall(M.trim,uu,y+sill+wh/2,.075,wh+.12,.16,.12);
   for(const yy of [y+sill,y+sill+wh])wall(M.trim,u,yy,ww+.16,.09,.23,.15);
   wall(M.trim,u,y+sill-.08,ww+.35,.11,.45,.25); // drip sill
   // Bolt heads and shallow corrugations in each modular panel.
   for(const uu of [u-bw/2+.1,u+bw/2-.1])for(const yy of [y+.2,y+floorH-.2])wall(M.dark,uu,yy,.065,.065,.06,.19);
   for(let j=0;j<5;j++)wall(M.trim,u-ww/2+j*ww/4,y+floorH-.42,.035,.56,.06,.14);
  }
  wall(M.steel,0,h-.12,width+.3,.24,.4);
 }
 // Roof shell, parapets, access hatch, vents, HVAC louvers and service walk.
 r.box(M.roof,0,h,0,w+.55,.3,d+.55);
 for(const z of [-d/2,d/2])r.box(M.trim,0,h+.35,z,w+.55,.65,.2);
 for(const x of [-w/2,w/2])r.box(M.trim,x,h+.35,0,.2,.65,d);
 r.box(M.dark,-w*.25,h+.2,0,2,.18,2.8);r.box(M.trim,-w*.25,h+.32,0,1.8,.13,2.6);
 r.box(M.trim,w*.25,h+.8,-d*.15,3.5,1.35,2.5);
 for(let v=0;v<11;v++)r.box(M.dark,w*.25,h+.28+v*.1,-d*.15+1.27,3.12,.045,.05);
 for(let v=0;v<2;v++){r.add('cyl',M.dark,[w*.25-.85+v*1.7,h+1.53,-d*.15],[.61,.08,.61]);
   for(let j=0;j<4;j++)r.box(M.trim,w*.25-.85+v*1.7,h+1.6,-d*.15,1.1,.04,.09,[0,j*Math.PI/4,0]);}
 r.pipe(M.trim,[w*.25,h+.55,-d*.15-1.25],[w*.25,h+.55,-d*.38],.28);
 for(const x of [-w*.28,-w*.1]){r.pipe(M.steel,[x,h,-d*.2],[x,h+1.6,-d*.2],.16);r.add('cyl',M.trim,[x,h+1.65,-d*.2],[.35,.13,.35]);}
 for(let j=0;j<5;j++)r.box(M.trim,-w*.25,h+.22,-d*.4+j*.65,1.25,.035,.48);
 // Continuous rain gutters, downpipes, clips and discharge boots to storm riser.
 for(const x of [-w/2-.22,w/2+.22]){
   k.pipe(M.steel,[x,h-.15,-d/2],[x,h-.15,d/2],.13);
   k.pipe(M.steel,[x,h-.15,d/2],[x,-1.0,d/2],.085);
   k.pipe(M.steel,[x,-1,d/2],[0,-1,6],.085);
   for(let y=.3;y<h;y+=1.2)k.add('ring',M.trim,[x,y,d/2],[.11,.11,.11],[Math.PI/2,0,0]);
 }
 // Six proper treads from sidewalk to porch and guarded side ramp (1:12).
 const doorX=(-w/2+(Math.floor(Math.floor(w/3.2)/2)+.5)*(w/Math.floor(w/3.2)));
 k.box(M.concrete,doorX,-.12,d/2+1.1,3.2,.25,2.2);
 for(let j=0;j<6;j++)k.box(M.concrete,doorX,-1.2+.1*(j+1),d/2+4.25-j*.37,2.8,.2*(j+1),.38);
 for(const x of [doorX-1.5,doorX+1.5]){
   k.pipe(M.trim,[x,.85,d/2+1],[x,-.12,d/2+4.4],.045);
   for(const z of [d/2+.4,d/2+1.9,d/2+4.3])k.pipe(M.trim,[x,-.9,z],[x,z>d/2+3?-.12:.85,z],.045);
 }
 k.box(M.steel,doorX,2.9,d/2+1,4,.16,2.8); // shelter over airlock
 k.box(M.glow,doorX,2.7,d/2+.25,1.6,.08,.14);
 // Accessible ramp runs along the front facade, with landings and twin rails.
 const rampZ=d/2+1.1,run=7.2;
 for(let leg=0;leg<2;leg++){
  const midX=doorX-1.6-run/2,yy=leg===0?-.9:-.3,zz=rampZ+leg*1.6;
  k.box(M.concrete,midX,yy,zz,run,.12,1.3,[0,0,(leg===0?-1:1)*Math.atan(1/12)]);
  for(const dz of [-.72,.72])k.pipe(M.trim,[midX-run/2,yy+(leg===0?.3:-.3)+.9,zz+dz],[midX+run/2,yy+(leg===0?-.3:.3)+.9,zz+dz],.035);
 }
 k.box(M.concrete,doorX-1.6-run-.65,-.6,rampZ+.8,1.3,.12,2.9);
 k.box(M.concrete,doorX-1.6,-1.2,rampZ,1.3,.12,1.3);
 // Pavers on frontage, with individual joints and deterministic colour variation.
 for(let row=0;row<17;row++)for(let col=0;col<4;col++)k.box(M.concrete,(col-1.5)*.57,-1.04,d/2+4.5+row*.54,.55,.075,.52,null,0x74766a+((row+col+i)%4)*0x030303);
 // Meter, isolator, frost jacket and all three separate wet-core connections.
 k.box(M.trim,w/2+.35,.6,2,.7,1.2,.8);k.box(M.dark,w/2+.72,.8,2,.02,.3,.35);
 const meter=G.utilities.nodes[G.utilities.house_nodes[i]];
 const meterLocal=utilityPoint([meter.x,meter.y,meter.z]).sub(houseShells[i].base).applyQuaternion(houseShells[i].q.clone().invert());
 k.pipe(M.blue,meterLocal.toArray(),[0,-1.0,6],.065);
 k.pipe(M.blue,[0,-1.0,6],[0,.35,6],.065);k.pipe(M.blue,[0,.35,6],[w/2+.35,.35,2],.065);
 k.add('ring',M.amber,[w/2+.4,.4,2],[.18,.18,.18],[0,Math.PI/2,0]);
 // Underfloor wet services are connected to the common street riser.
 const hot=material('copper',0xa36b4b,{metalness:.78,roughness:.36});
 k.add('cyl',M.white,[w*.36,1.1,-d*.36],[.5,2.1,.5]);
 k.pipe(M.blue,[0,-.8,6],[w*.36,-.8,-d*.36],.04);
 k.pipe(M.blue,[w*.36,-.8,-d*.36],[w*.36,.25,-d*.36],.04);
 for(const end of [[w/2-1.25,.95,2.4],[w*.16,.45,-d*.26],[w*.31,.4,-d*.37],[w*.4,1.8,-d*.12]]){
   k.pipe(M.blue,[0,-.8,6],[end[0],-.8,end[2]],.025);k.pipe(M.blue,[end[0],-.8,end[2]],end,.025);
   k.pipe(M.steel,[end[0],-.55,end[2]],[0,-1,6],.055);k.pipe(M.steel,end,[end[0],-.55,end[2]],.055);
 }
 k.pipe(hot,[w*.36,2.1,-d*.36],[w/2-1.25,2.1,2.4],.023);k.pipe(hot,[w/2-1.25,2.1,2.4],[w/2-1.25,.95,2.4],.023);
 // Interior floor plates and stairs. Upper plates remain visible with the translucent roof.
 for(let level=0;level<floors;level++){
  const y=level*floorH; const f=level===0?interiorKit:r; const fk=f;
  if(level===0)fk.box(M.wood,0,y+.02,0,w-.35,.12,d-.35);
  else {const left=(-w/2+.18),right=w/2-.18,back=-d/2+.18,front=d/2-.18;
    fk.box(M.wood,(left-.1)/2,y+.02,0,-.1-left,.12,d-.35);
    fk.box(M.wood,(1.4+right)/2,y+.02,0,right-1.4,.12,d-.35);
    fk.box(M.wood,.65,y+.02,(back-d*.4-.25)/2,1.5,.12,-d*.4-.25-back);
    const stairEnd=-d*.4+5.4;fk.box(M.wood,.65,y+.02,(stairEnd+front)/2,1.5,.12,front-stairEnd);
  }
  // Bedroom/bath partitions leave full-height door openings.
  f.box(M.panel,-w*.05,y+1.35,-d*.25,.12,2.7,d*.46);
  f.box(M.panel,-w*.3,y+1.35,-.6,w*.26,2.7,.12);
  f.box(M.trim,-w*.07,y+2.5,-.6,1.1,.28,.12);
  // Bed, separate mattress, blanket, pillow and frame.
  const bx=-w*.29,bz=-d*.28;
  f.box(M.wood,bx,y+.3,bz,2.4,.45,3.8);f.box(M.white,bx,y+.65,bz,2.3,.35,3.7);
  f.box(M.fabric,bx,y+.87,bz+.4,2.32,.12,2.7,null,accent);f.box(M.white,bx,y+.96,bz-1.3,1.6,.24,.65);
  f.box(M.wood,bx,y+.8,bz-1.95,2.6,1.5,.16);
  f.box(M.wood,bx+1.85,y+.5,bz-1.4,.8,.9,.8);f.add('cyl',M.glow,[bx+1.85,y+1.25,bz-1.4],[.28,.35,.28]);
  if(type===0){for(let bunk=0;bunk<1;bunk++){
    const zz=-d*.28+bunk*4.6,xx=-w*.29;
    f.box(M.steel,xx,y+2.25,zz,2.4,.12,3.8);f.box(M.white,xx,y+2.47,zz,2.3,.3,3.7);
    for(const dx of [-1.17,1.17])for(const dz of [-1.82,1.82])f.box(M.steel,xx+dx,y+1.35,zz+dz,.08,2.7,.08);
    if(bunk===1){f.box(M.steel,xx,y+.35,zz,2.4,.12,3.8);f.box(M.white,xx,y+.57,zz,2.3,.3,3.7);}
    for(let rung=0;rung<6;rung++)f.box(M.trim,xx+1.22,y+.3+rung*.34,zz-.6,.1,.05,.8);
  }}
  // Sofa with actual cushions, arms and back; coffee table and rug.
  const sx=-w*.27,sz=d*.24;
  f.box(M.fabric,sx,y+.48,sz,3.8,.72,1.5);f.box(M.fabric,sx,y+1.12,sz-.67,3.9,1.1,.32);
  for(const dx of [-1.85,1.85])f.box(M.fabric,sx+dx,y+.95,sz,.35,.7,1.6);
  for(let j=0;j<3;j++)f.box(M.white,sx-1.2+j*1.2,y+.91,sz+.1,1.12,.19,1.2,null,accent);
  f.box(M.fabric,sx,y+.1,sz+2.1,4.4,.04,2.6);f.box(M.wood,sx,y+.67,sz+2.1,2.4,.16,1.1);
  for(const dx of [-1,1])for(const dz of [-.4,.4])f.box(M.steel,sx+dx,y+.36,sz+2.1+dz,.08,.6,.08);
  // TV on cabinet, speakers, books.
  f.box(M.wood,sx,y+.5,d/2-.65,3.8,.9,.8);f.box(M.dark,sx,y+1.85,d/2-.67,2.7,1.55,.15);
  f.box(M.screen,sx,y+1.86,d/2-.77,2.52,1.34,.025);
  for(let j=0;j<5;j++)f.box(M.fabric,sx-1.5+j*.18,y+1.1,d/2-.55,.13,.32+.06*(j%3),.3,null,[0x70594a,0x7d8959,0x536b78][j%3]);
  // Kitchen counter, four burners, oven glazing, sink bowl/rim and tap.
  const kx=w/2-1.25;
  f.box(M.white,kx,y+.52,1,1.8,1.02,5.3);f.box(M.dark,kx,y+1.1,1,1.95,.14,5.5);
  for(let j=0;j<3;j++){f.box(M.panel,kx-0.93,y+.55,-.7+j*1.6,.04,.8,1.42);f.box(M.steel,kx-.98,y+.82,-.7+j*1.6,.06,.04,.4);}
  for(const xx of [-.4,.4])for(const zz of [-.4,.4])f.add('ring',M.trim,[kx+xx,y+1.2,-.7+zz],[.23,.23,.23],[Math.PI/2,0,0]);
  f.box(M.glass,kx-.97,y+.52,-.7,.02,.57,1.02);
  f.box(M.trim,kx,y+1.2,2.4,1.15,.04,.96);f.box(M.dark,kx,y+1.23,2.4,.95,.04,.76);
  f.pipe(M.trim,[kx+.4,y+1.2,2.9],[kx+.4,y+1.7,2.9],.04);f.pipe(M.trim,[kx+.4,y+1.7,2.9],[kx+.4,y+1.7,2.5],.04);
  // Refrigerator, front-loading laundry, bathroom sanitary fixtures.
  f.box(M.white,kx,y+1.12,-d/2+1.1,1.8,2.25,1.8);f.box(M.steel,kx-.94,y+1.3,-d/2+1.7,.06,.7,.07);
  f.box(M.white,w*.16,y+.63,-d*.26,1.3,1.25,1.3);
  f.add('ring',M.steel,[w*.16,y+.65,-d*.26+.67],[.43,.43,.43]);f.add('cyl',M.glass,[w*.16,y+.65,-d*.26+.69],[.35,.03,.35],[Math.PI/2,0,0]);
  f.add('ball',M.white,[w*.31,y+.4,-d*.37],[.48,.33,.65]);f.box(M.white,w*.31,y+.8,-d*.42,.8,1.1,.32);
  f.box(M.white,w*.3,y+.1,-d*.1,1.6,.18,1.6);f.box(M.glass,w*.25,y+1.2,-d*.1,.04,2.3,1.6);
  f.pipe(M.trim,[w*.4,y+.3,-d*.12],[w*.4,y+2.3,-d*.12],.035);
  // Dining table and four chairs, kettle and plates.
  f.box(M.wood,w*.14,y+.92,d*.21,2.4,.15,1.8);
  for(const dx of [-.9,.9])for(const dz of [-.6,.6])f.box(M.steel,w*.14+dx,y+.47,d*.21+dz,.08,.85,.08);
  for(const dz of [-1.25,1.25])for(const dx of [-.7,.7]){f.box(M.wood,w*.14+dx,y+.52,d*.21+dz,.65,.12,.6);f.box(M.wood,w*.14+dx,y+.98,d*.21+dz+Math.sign(dz)*.25,.65,.9,.08);}
  for(const dx of [-.6,.6])f.add('cyl',M.white,[w*.14+dx,y+1.02,d*.21],[.23,.025,.23]);
 }
 if(floors>1){for(let j=0;j<16;j++)interiorKit.box(M.steel,.65,j*floorH/16+.1,-d*.4+j*.32,1.3,.12,.34);}
 k.finish();r.finish();interiorKit.finish();
 g.userData.house=i;g.traverse(o=>o.userData.house=i);
 const label=textSprite(`HH / ${String(i+1).padStart(3,'0')}   ${['CREW','HAB','THERMAL','ADMIN'][type]}`,'#ddd5b8',24);label.position.set(doorX,3.4,d/2+.2);label.scale.set(4.4,.65,1);shell.add(label);
 const litMaterials=[M.glow,M.screen].map(m=>m.clone());g.traverse(o=>{if(o.material===M.glow)o.material=litMaterials[0];else if(o.material===M.screen)o.material=litMaterials[1];});
 return {g,shell,roof,inside,i,litMaterials};
}
function updateDetail(){
 if(!housesMesh||++detailFrame%10!==0)return;
 const near=houseShells.map((h,i)=>[camera.position.distanceTo(h.base),i]).sort((a,b)=>a[0]-b[0]);
 const wanted=new Set(near.filter(x=>x[0]<480).slice(0,32).map(x=>x[1]));
 if(selected?.kind==='house'&&camera.position.distanceTo(houseShells[selected.id].base)<1000)wanted.add(selected.id);
 const zero=new THREE.Matrix4().makeScale(0,0,0);
 for(const [i,v] of houseDetails){if(!wanted.has(i)){
   world.remove(v.g);v.litMaterials.forEach(m=>m.dispose());v.g.traverse(o=>{if(o.isInstancedMesh)o.dispose();if(o.isSprite){o.material.dispose();}});houseDetails.delete(i);
   housesMesh.setMatrixAt(i,houseShells[i].matrix);roofProxies[i].mesh.setMatrixAt(i,roofProxies[i].matrix);
 }}
 let built=0;for(const i of wanted){if(!houseDetails.has(i)){if(built++>=2)continue;houseDetails.set(i,makeHouse(i));housesMesh.setMatrixAt(i,zero);roofProxies[i].mesh.setMatrixAt(i,zero);}
  const v=houseDetails.get(i);v.roof.visible=true;v.shell.visible=true;
  if(S){v.litMaterials[0].emissiveIntensity=S.houses.power[i]?.7:0;v.litMaterials[1].emissiveIntensity=S.houses.power[i]?.6:0;}
  // The roof and complete upper storey contents share a removable group.
 }
 syncMedium(new Set(houseDetails.keys()));housesMesh.instanceMatrix.needsUpdate=true;roofProxies[0].mesh.instanceMatrix.needsUpdate=true;
}

function utilityPoint(p){return sph(p[0],p[1],p[2]-terrainH(p[0],p[1]));}
function buildUtilities(){
 const U=G.utilities;const kit=new Kit(utilityGroup),groundKit=new Kit(streetDetail),potable=new Kit(potableGroup);
 const um=(name,color)=>material(name,color,{metalness:.45,roughness:.4,depthTest:false,transparent:true,opacity:.87});
 const waterMat=um('potable',0x4b9bb9),sewerMat=um('sewer',0xb99865),stormMat=um('storm',0x71988b),jointMat=um('coupling',0xabb8b9);
 function run(points,r,mat,tag){const pts=[];
   for(let j=0;j<points.length-1;j++){
     const a=points[j],b=points[j+1],len=Math.hypot(b[0]-a[0],b[1]-a[1]),steps=Math.max(1,Math.ceil(len/12));
     for(let t=0;t<steps;t++){const f=t/steps;pts.push(utilityPoint(a.map((v,k)=>v+(b[k]-v)*f)));}
   }pts.push(utilityPoint(points.at(-1)));
   for(const p of points.slice(1,-1))kit.add("ball",mat,utilityPoint(p).toArray(),[r,r,r],null,null,tag);
   for(let j=0;j<pts.length-1;j++){kit.pipe(mat,pts[j].toArray(),pts[j+1].toArray(),r,tag);
     if(j%3===0){const delta=pts[j+1].clone().sub(pts[j]).normalize();kit.pipe(jointMat,pts[j].clone().addScaledVector(delta,-.13).toArray(),pts[j].clone().addScaledVector(delta,.13).toArray(),r*1.4,tag);}}
   pts.cumulative=[0];for(let j=1;j<pts.length;j++)pts.cumulative.push(pts.cumulative[j-1]+pts[j-1].distanceTo(pts[j]));
   return pts;
 }
 utilityPaths=U.links.map(e=>makePotable(e.points,e.diameter_m/2,{system:'water',id:e.id},potable));
 makePotable(U.plant_feed,.34,{system:'feed',id:-1},potable);
 for(const system of U.drainage){
   system.links.forEach((e,i)=>run(e.points,e.diameter_m/2,system.name==='sanitary'?sewerMat:stormMat,{system:system.name,id:i}));
   run(system.rising_main,.22,system.name==='sanitary'?sewerMat:stormMat,{system:system.name,id:-1});
   for(let j=0;j<system.nodes.length;j++){
    const n=system.nodes[j];if(n.kind==='pump'||n.kind==='tank')continue;
    const cover=sph(n.x,n.y,1.28),bottom=utilityPoint([n.x,n.y,n.z]);
    if(n.kind==='tee'&&j%3===0){
      const q=quatAt(n.x,n.y);groundKit.add('cyl',M.steel,cover.toArray(),[.64,.11,.64],q);
      groundKit.add('ring',M.trim,cover.clone().addScaledVector(cover.clone().normalize(),.07).toArray(),[.51,.51,.51],q.clone().multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1,0,0),Math.PI/2)));
      kit.pipe(jointMat,bottom.toArray(),cover.toArray(),.54,{system:system.name,id:-1});
      // Ladder rungs in inspection shafts.
      const len=bottom.distanceTo(cover),v=cover.clone().sub(bottom).normalize();
      for(let k=.5;k<len;k+=.65){const p=bottom.clone().addScaledVector(v,k);kit.pipe(stormMat,p.clone().add(new THREE.Vector3(-.23,0,0)).toArray(),p.clone().add(new THREE.Vector3(.23,0,0)).toArray(),.035);}
    }
    if(n.kind==='meter'){
      // House foul and rain stacks terminate at wet core / downpipe manifold.
      const house=n.house,a=G.houses.angle[house]*Math.PI/180;
      const entry=houseShells[house].base.clone().add(new THREE.Vector3(0,-1,6).applyQuaternion(houseShells[house].q));
      kit.pipe(system.name==='storm'?stormMat:sewerMat,bottom.toArray(),entry.toArray(),.09,{system:system.name,id:-1});
    }
    if(system.name==='storm'&&n.kind==='tee'){
      const rr=Math.hypot(n.x,n.y),a=Math.atan2(n.y,n.x),x=n.x+Math.cos(a)*3.6,y=n.y+Math.sin(a)*3.6,q=quatAt(x,y,-a);
      const top=sph(x,y,1.14);groundKit.add('box',M.dark,top.toArray(),[1.1,.12,.65],q);
      for(let k=0;k<7;k++){const p=top.clone().add(new THREE.Vector3((k-3)*.145,.08,0).applyQuaternion(q));groundKit.add('box',M.trim,p.toArray(),[.055,.055,.63],q);}
      kit.pipe(stormMat,top.toArray(),bottom.toArray(),.14,{system:'storm',id:-1});
    }
   }
 }
 for(const n of U.nodes){if(n.kind==='tee'){const p=utilityPoint([n.x,n.y,n.z]);potable.add('ball',M.trim,p.toArray(),[.145,.145,.145]);}
 if(n.kind==='isolation'||n.kind==='meter'){
  const p=utilityPoint([n.x,n.y,n.z]);potable.add('ball',M.trim,p.toArray(),[.23,.23,.23]);
  const q=quatAt(n.x,n.y);const top=p.clone().addScaledVector(p.clone().normalize(),.52);
  potable.pipe(M.trim,p.toArray(),top.toArray(),.045);potable.add('ring',M.amber,top.toArray(),[.28,.28,.28],q.clone().multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1,0,0),Math.PI/2)));
 }}
 potableBatches=potable.finish();for(const m of potableBatches)if(m.material===MAT['pipe-ice']){m.userData.iceOriginal=m.instanceMatrix.array.slice();m.instanceMatrix.array.fill(0);m.instanceMatrix.needsUpdate=true;}utilityBatches=kit.finish();groundKit.finish();utilityGroup.renderOrder=30;
 utilityBatches.forEach(m=>{m.renderOrder=30;m.castShadow=false;});
 utilityDrops=pointsLayer(U.links.length*5,TEX.dot,0xc8f6ff,.38,true);utilityDrops.material.depthTest=true;utilityDrops.renderOrder=35;
 utilityGroup.visible=!!layers.underground;utilityDrops.visible=layers.water;
}
function updateUtilityFlow(t){
 if(!utilityDrops||!S?.hydraulics)return;
 const delta=utilityLastTime?Math.min(.25,t-utilityLastTime):0;utilityLastTime=t;utilityTime+=delta*clock.speed*60;
 if(!layers.water)return;
 const a=utilityDrops.geometry.attributes.position;const h=S.hydraulics;
 for(let particle=0;particle<utilityPaths.length*5;particle++){const i=Math.floor(particle/5);
  const pts=utilityPaths[i],v=h.velocity_m_s[i],L=G.utilities.links[i].length_m;
  if(!layers.water||Math.abs(v)<1e-7){a.setXYZ(particle,0,-99999,0);continue;}
  const u=((utilityTime*v/L+i*.381+(particle%5)/5)%1+1)%1;
  // Interpolate by actual segment length, never through a smoothed corner.
  const lengths=pts.cumulative,dist=u*lengths.at(-1);let j=1;
  while(j<lengths.length-1&&dist>lengths[j])j++;
  const p=pts[j-1].clone().lerp(pts[j],(dist-lengths[j-1])/Math.max(lengths[j]-lengths[j-1],1e-8));a.setXYZ(particle,p.x,p.y,p.z);
 }a.needsUpdate=true;
}
function buildStreetLife(){
 const c=G.cfg,k=new Kit(streetDetail);
 for(let sector=0;sector<c.sectors;sector++){
  const angle=sector*Math.PI/3,dir=[Math.cos(angle),Math.sin(angle)],normal=[-dir[1],dir[0]];
  for(const side of [-1,1]){const path=[c.hub_radius,c.wall_radius-15].map(r=>[dir[0]*r+normal[0]*side*8,dir[1]*r+normal[1]*side*8]);
    ribbon(path,3.2,1.16,0xa5a797,{map:pavingTexture,bumpMap:pavingTexture,bumpScale:.035});}
  ribbon(arcPts(sector*60+2,(sector+1)*60-2,c.ring_road_radius+10,50),3.4,1.16,0xa5a797,{map:pavingTexture});
 }
 // Streets share exact spine endpoints. Curbs stop at intersections, not across them.
 for(let s=0;s<c.sectors;s++)for(let row=0;row<=c.house_rows;row++){
  const radius=c.house_radius_min-30+row*c.house_ring_step;
  for(const side of [-1,1]){
   const r=radius+side*7.2;const start=s*60+2,end=(s+1)*60-2;
   ribbon(arcPts(start,end,r,40),3.4,1.16,0xb4b5a7,{map:pavingTexture,bumpMap:pavingTexture,bumpScale:.035});
   // Individually laid kerb blocks and expansion joints.
   const count=Math.floor((end-start)*Math.PI/180*r/1.15);
   for(let j=0;j<count;j++){
    const a=(start+(end-start)*(j+.5)/count)*Math.PI/180,[x,y]=[Math.cos(a)*(radius+side*5.1),Math.sin(a)*(radius+side*5.1)];
    k.add('box',M.concrete,sph(x,y,1.15).toArray(),[1.1,.28,.32],quatAt(x,y,-a-Math.PI/2));
   }
  }
  // Dashed lane paint and crossing marks leave junction mouths clear.

  for(const a of [s*60+1.4,(s+1)*60-1.4]){
   for(let j=-3;j<=3;j++){const [x,y]=polar(a,radius+j*.95);k.add('box',M.white,sph(x,y,1.045).toArray(),[.52,.025,3.2],quatAt(x,y,-a*Math.PI/180));}
  }
  for(let b=0;b<3;b++){
   const a=s*60+13+b*17,[x,y]=polar(a,radius+10.2),q=quatAt(x,y,-a*Math.PI/180-Math.PI/2),base=sph(x,y,1.2);
   const local=(shape,mat,p,sz,rot=null)=>k.add(shape,mat,base.clone().add(new THREE.Vector3(...p).applyQuaternion(q)).toArray(),sz,rot?q.clone().multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(...rot))):q);
   for(let j=0;j<5;j++){local('box',M.wood,[0,.65,-.4+j*.2],[2.8,.12,.15]);local('box',M.wood,[0,1.0+j*.17,-.46],[2.8,.12,.12]);}
   for(const xx of [-1,1])local('box',M.steel,[xx,.34,0],[.12,.65,.85]);
   local('cyl',M.steel,[2.4,.7,0],[.36,1.25,.36]);local('cyl',M.dark,[2.4,1.36,0],[.3,.08,.3]);
   // Pedestrian luminaires with base bolts, outreach and warm shielded heads.
   local('cyl',M.steel,[-3.8,2.9,0],[.09,5.8,.09]);local('box',M.steel,[-3.4,5.75,0],[.9,.1,.12]);
   local('box',M.glow,[-3,5.65,0],[.58,.1,.34]);local('box',M.concrete,[-3.8,.12,0],[.55,.24,.55]);
  }
 }
 // Tangential neighbourhood promenades, retaining walls and human-scale plazas.
 const names=['COMMISSARY / CANTEEN','SOCIAL CLUB','MAINTENANCE','COLONY MARKET','LAUNDRY / BATHS','RECREATION'];
 for(let s=0;s<c.sectors;s++){
  const a=s*60+38,[x,y]=polar(a,225),q=quatAt(x,y,-a*Math.PI/180-Math.PI/2);
  const plaza=sph(x,y,.95);k.add('box',M.concrete,plaza.toArray(),[38,.22,27],q);
  // Low modular civic frontage with awning, doors and sheltered waiting area.
  const base=sph(x,y,1.1),put=(mat,p,sz)=>k.add('box',mat,base.clone().add(new THREE.Vector3(...p).applyQuaternion(q)).toArray(),sz,q);
  put(M.panel,[0,3.1,-7],[28,6.2,10]);put(M.steel,[0,6.3,-7],[29,.35,11]);put(M.steel,[0,3.4,.2],[30,.25,5]);
  for(let j=-3;j<=3;j++){put(M.glass,[j*3.7,2.1,-1.9],[2.7,2.1,.06]);put(M.steel,[j*4.6,1.7,2.3],[.13,3.4,.13]);}
  const label=addLabel(names[s],x,y,10,'#c5b992','near');
  ribbon(arcPts(s*60,a,225,30),5,1.06,0x898d80,{map:pavingTexture});
 }
 k.finish();
}

// Physical infrastructure remains visible independently of diagnostic overlays.
let mediumBatches=[],mediumHidden=new Set(),potableGroup=new THREE.Group(),potableBatches=[];
let netSpanPaths=[],houseNetDrops=[],cabinetMeters=[],phaseDrops=[],phaseDropFlow=null,roadSignals=[],vehicleModels=[];
world.add(potableGroup);
function buildLandscape(){
 const land=cap(3850,-.12,0xffffff,290,420,.08),positions=land.geometry.attributes.position,colors=[];
 for(let i=0;i<positions.count;i++){
  const px=positions.getX(i),py=positions.getY(i),pz=positions.getZ(i),rr=RP*Math.atan2(Math.hypot(px,pz),py),angle=Math.atan2(pz,px),x=rr*Math.cos(angle),y=rr*Math.sin(angle),h=terrainH(x,y);
  const grain=.5+.25*Math.sin(x*.052+y*.043)*Math.cos(y*.081-x*.027)+.12*Math.sin(x*.29+y*.37);
  const frost=sstep(70,190,h),color=new THREE.Color().setRGB(.24+grain*.12+frost*.24,.255+grain*.115+frost*.27,.25+grain*.11+frost*.30);colors.push(color.r,color.g,color.b);
 }land.geometry.setAttribute('color',new THREE.Float32BufferAttribute(colors,3));land.material.vertexColors=true;
 const k=new Kit(world);for(const [px,py,height,width] of [[1250,850,180,280],[-450,-1350,145,360],[-1640,980,220,310],[450,1650,190,330]]){
  for(let n=0;n<160;n++){const a=n*2.39996,r=width*Math.sqrt((n+.5)/160),x=px+Math.cos(a)*r,y=py+Math.sin(a)*r,sz=2.5+(n%9)*1.3;
   k.add('ball',M.concrete,sph(x,y,sz*.22).toArray(),[sz,sz*.7,sz*.55],quatAt(x,y,a),0x676b68);
  }
 }k.finish();
}
function mediumHomes(){
 const kit=new Kit(world);
 for(let i=0;i<houseShells.length;i++){
  const {base,q}=houseShells[i],[w,h,d]=DIM[G.houses.type[i]],floors=Math.round((h-.45)/3.4);
  const put=(mat,p,scale,rot=null)=>kit.add('box',mat,base.clone().add(new THREE.Vector3(...p).applyQuaternion(q)).toArray(),scale,rot?q.clone().multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(...rot))):q,null,i);
  put(M.concrete,[0,-.4,0],[w+.8,.8,d+.8]);put(M.panel,[0,h/2,0],[w,h,d]);
  put(M.roof,[0,h+.05,0],[w+.3,.2,d+.3]);
  for(const z of [-d/2,d/2]){
   put(M.trim,[0,h+.38,z],[w+.5,.7,.16]);
   for(let f=0;f<floors;f++){
    const fy=f*3.4;put(M.steel,[0,fy+.12,z*1.012],[w,.24,.26]);
    for(let x=-w/2+1.8;x<w/2-1;x+=3.2){
     put(M.steel,[x,fy+2,z*1.015],[2.52,1.95,.16]);put(M.glass,[x,fy+2,z*1.026],[2.3,1.7,.065]);
     put(M.glow,[x,fy+2,z*1.02],[2.18,1.58,.03]);put(M.trim,[x,fy+2,z*1.033],[.08,1.75,.06]);
    }
   }
   for(let x=-w/2;x<=w/2;x+=3.2)put(M.steel,[x,h/2,z*1.034],[.13,h,.19]);
  }
  for(const x of [-w/2,w/2]){
   put(M.trim,[x,h+.38,0],[.16,.7,d+.5]);
   for(let f=0;f<floors;f++)for(let z=-d/2+2;z<d/2-1;z+=3.2){
    put(M.steel,[x*1.013,f*3.4+2,z],[.13,1.9,2.5]);put(M.glow,[x*1.022,f*3.4+2,z],[.035,1.65,2.15]);put(M.glass,[x*1.032,f*3.4+2,z],[.055,1.7,2.3]);
   }
   put(M.trim,[x*1.024,h/2,-d/2+.5],[.12,h,.12]);
  }
  put(M.steel,[0,1.35,d/2+.32],[1.6,2.7,.25]);put(M.glass,[0,1.75,d/2+.47],[1.16,1.45,.06]);
  put(M.steel,[0,2.95,d/2+1.1],[3.2,.16,2.8]);
  for(let step=0;step<7;step++)put(M.concrete,[0,-.9-step*.2,d/2+.65+step*.35],[2.6,.2,.38]);
  put(M.trim,[w*.25,h+.85,-d*.15],[3.5,1.4,2.5]);
  for(let j=0;j<7;j++)put(M.dark,[w*.25-1.35+j*.45,h+1.58,-d*.15],[.21,.035,2.1]);
  for(const x of [-w*.28,w*.08]){put(M.steel,[x,h+1.05,-d*.27],[.5,2.1,.5]);put(M.trim,[x,h+2.1,-d*.27],[.8,.18,.8]);}
  put(M.amber,[w/2+.11,1.8,0],[.24,.8,.55]);
 }
 mediumBatches=kit.finish();for(const m of mediumBatches){m.userData.original=m.instanceMatrix.array.slice();}
}
function syncMedium(wanted){
 if(wanted.size===mediumHidden.size&&[...wanted].every(i=>mediumHidden.has(i)))return;
 for(const m of mediumBatches){const src=m.userData.original,dst=m.instanceMatrix.array;
  m.userData.tags.forEach((id,j)=>{if(wanted.has(id)){dst.fill(0,j*16,j*16+16);}else if(mediumHidden.has(id)){dst.set(src.subarray(j*16,j*16+16),j*16);}});m.instanceMatrix.needsUpdate=true;
 }mediumHidden=new Set(wanted);
}
function markedRoad(flat,width,h){
 ribbon(flat,width+2.2,h-.12,0x77756a);const road=ribbon(flat,width,h,0x454b4d,{roughness:.95,bumpMap:asphaltTexture,bumpScale:.03});road.userData.road=true;
 const pts=subdiv(flat,4),paint=new Kit(world);let distance=0;
 for(let i=1;i<pts.length;i++){
  const a=pts[i-1],b=pts[i],dx=b[0]-a[0],dy=b[1]-a[1],len=Math.hypot(dx,dy),yaw=-Math.atan2(dy,dx),x=(a[0]+b[0])/2,y=(a[1]+b[1])/2;
  if(!len)continue;const radial=Math.hypot(x,y),bearing=(Math.atan2(y,x)*180/Math.PI+360)%60,alignment=Math.abs((x*dx+y*dy)/(Math.max(1,radial)*len));
  const crossSpine=alignment<.5&&Math.min(bearing,60-bearing)*Math.PI/180*radial<8;
  const crossRow=alignment>.8&&[G.cfg.hub_radius,G.cfg.ring_road_radius,...Array.from({length:G.cfg.house_rows+1},(_,j)=>G.cfg.house_radius_min-30+j*G.cfg.house_ring_step)].some(r=>Math.abs(radial-r)<8);
  if(radial<G.cfg.wall_radius+5&&(crossSpine||crossRow)){distance+=len;continue;}
  const q=quatAt(x,y,yaw),normal=[-dy/len,dx/len];
  for(const side of [-1,1])paint.add('box',M.white,sph(x+normal[0]*side*(width/2-.35),y+normal[1]*side*(width/2-.35),h+.05).toArray(),[len+.03,.035,.17],q);
  if(Math.floor(distance/4)%3<2)paint.add('box',M.amber,sph(x,y,h+.065).toArray(),[len,.035,.2],q);
  if(i%4===0)for(const side of [-1,1])paint.add('box',M.glow,sph(x+normal[0]*side*(width/2-.7),y+normal[1]*side*(width/2-.7),h+.08).toArray(),[.2,.06,.13],q);
  distance+=len;
 }paint.finish();return road;
}
function makePotable(points,r,tag,kit){
 const pts=[];
 for(let j=1;j<points.length;j++){
  const a=points[j-1],b=points[j],steps=Math.max(1,Math.ceil(Math.hypot(b[0]-a[0],b[1]-a[1])/7));
  for(let k=0;k<steps;k++)pts.push(utilityPoint(a.map((v,c)=>v+(b[c]-v)*k/steps)));
 }pts.push(utilityPoint(points.at(-1)));
 const metal=material('pipe-steel',0xa1aaa6,{metalness:.75,roughness:.36}),glass=material('pipe-sightglass',0xb2d9db,{transparent:true,opacity:.18,depthWrite:false,metalness:.1,roughness:.08,side:THREE.DoubleSide});
 const fluid=material('water-core',0x3aa8c1,{transparent:true,opacity:.73,depthWrite:false,roughness:.16,metalness:.05});
 if(!UNIT.lowerPipe){UNIT.lowerPipe=new THREE.CylinderGeometry(1,1,1,10,1,true,Math.PI/2,Math.PI);UNIT.upperPipe=new THREE.CylinderGeometry(1,1,1,10,1,true,-Math.PI/2,Math.PI);}
 const radius=Math.max(.16,r+.08); // cutaway jacket includes insulation; hydraulic bore stays authoritative
 for(let j=1;j<pts.length;j++){
  const a=pts[j-1],b=pts[j],dir=b.clone().sub(a).normalize(),up=a.clone().normalize();up.addScaledVector(dir,-up.dot(dir)).normalize();
  if(up.length()<.1)up.set(0,0,1).addScaledVector(dir,-dir.z).normalize();
  const right=dir.clone().cross(up).normalize(),q=new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(right,dir,up));
  const middle=a.clone().add(b).multiplyScalar(.5),len=a.distanceTo(b);
  kit.add('lowerPipe',metal,middle.toArray(),[radius,len,radius],q,null,tag);
  kit.add('upperPipe',glass,middle.toArray(),[radius,len,radius],q,null,tag);
  kit.pipe(fluid,a.toArray(),b.toArray(),radius*.79,tag);kit.pipe(material('pipe-ice',0x98c8ec,{roughness:.24,metalness:.08}),a.toArray(),b.toArray(),radius*1.17,tag);
  kit.pipe(M.trim,a.clone().addScaledVector(dir,-.12).toArray(),a.clone().addScaledVector(dir,.12).toArray(),radius*1.25,tag);
  for(let bolt=0;bolt<6;bolt++){
   const an=bolt*Math.PI/3,off=right.clone().multiplyScalar(Math.cos(an)*radius*1.15).addScaledVector(up,Math.sin(an)*radius*1.15);
   kit.pipe(M.dark,a.clone().add(off).addScaledVector(dir,-.15).toArray(),a.clone().add(off).addScaledVector(dir,.15).toArray(),.027,tag);
  }
  if(j%2===1){const worldP=points[Math.min(points.length-1,Math.round(j/pts.length*(points.length-1)))];
   // Project support to the same spherical ground, directly below its saddle.
   const n=middle.clone().normalize(),ground=middle.clone().addScaledVector(n,-Math.max(1,worldP[2]-terrainH(worldP[0],worldP[1])-.2));
   kit.pipe(M.steel,ground.toArray(),middle.clone().addScaledVector(n,-radius).toArray(),.07);
   kit.add('box',M.concrete,ground.toArray(),[.7,.22,.7],new THREE.Quaternion().setFromUnitVectors(UP,n));
  }
 }
 for(const point of points){const p=utilityPoint(point);kit.add('ball',M.trim,p.toArray(),[radius*1.05,radius*1.05,radius*1.05],null,null,tag);}
 pts.cumulative=[0];for(let j=1;j<pts.length;j++)pts.cumulative.push(pts.cumulative[j-1]+pts[j].distanceTo(pts[j-1]));return pts;
}
let serviceWirePaths=[],serviceEntries=[],poleLoads=new Float32Array(0),polePickMesh=null,poleDisplays=[];
function serviceEntry(i){
 const {base,q}=houseShells[i],[w,h,d]=DIM[G.houses.type[i]],pole=G.houses.pole[i];
 const direction=sph(G.poles.x[pole],G.poles.y[pole],10.7).sub(base).applyQuaternion(q.clone().invert());
 const t=Math.min((w/2-.48)/Math.max(.001,Math.abs(direction.x)),(d/2-.48)/Math.max(.001,Math.abs(direction.z)));
 const x=direction.x*t,z=direction.z*t,side=Math.abs(x)/(w/2)>Math.abs(z)/(d/2)?'x':'z',height=h+2.25+(i%3)*.3;
 return {x,z,height,w,h,d,side,pole,base,q,world:new THREE.Vector3(x,height,z).applyQuaternion(q).add(base)};
}
function makeServiceDrops(kit,physical,anchor){
 for(let i=0;i<G.houses.x.length;i++){
  const e=serviceEntry(i);serviceEntries[i]=e;const {x,z,height,w,h,d,side,pole,base,q}=e;
  const point=p=>new THREE.Vector3(...p).applyQuaternion(q).add(base),end=e.world;
  kit.pipe(M.steel,point([x,h,z]).toArray(),end.toArray(),.085);
  kit.add('box',M.trim,point([x,height-.3,z]).toArray(),[1.3,.12,.13],q);
  kit.add('box',M.dark,point([x,h+.15,z]).toArray(),[.65,.3,.65],q);
  for(let phase=-1;phase<=1;phase++){
   const to=point([x+phase*.38,height,z]),from=anchor(pole,phase),line=catenary(from,to,.55);
   // Every cable segment within the building footprint must clear the parapet.
   for(const p of line){const v=p.clone().sub(base).applyQuaternion(q.clone().invert());if(Math.abs(v.x)<w/2+.1&&Math.abs(v.z)<d/2+.1&&v.y<h+.6)p.addScaledVector(p.clone().normalize(),h+.6-v.y);}
   physical.push(line);serviceWirePaths.push({house:i,kind:'phase',points:line});for(let j=1;j<line.length;j++)kit.pipe(M.dark,line[j-1].toArray(),line[j].toArray(),.025);
   for(let disc=0;disc<4;disc++)kit.add('cyl',M.white,point([x+phase*.38,height-.27+disc*.075,z]).toArray(),[.09,.038,.09],q);
   if(phase===0)phaseDrops.push(line);
  }
  const neutral=catenary(anchor(pole,0,9.9),point([x,height-.22,z]),.4);physical.push(neutral);serviceWirePaths.push({house:i,kind:'neutral',points:neutral});for(let j=1;j<neutral.length;j++)kit.pipe(M.dark,neutral[j-1].toArray(),neutral[j].toArray(),.022);
  const net=catenary(anchor(pole,0,8.7),point([x,height-.46,z]),.32);physical.push(net);serviceWirePaths.push({house:i,kind:'fiber',points:net});houseNetDrops[i]=net;
  const exterior=side==='x'?[Math.sign(x)*(w/2+.26),h+.3,z]:[x,h+.3,Math.sign(z)*(d/2+.26)];
  const meter=[exterior[0],1.9,exterior[2]],bend=[x,h+.3,z];
  for(const [a,b] of [[[x,height-.2,z],bend],[bend,exterior],[exterior,meter]])kit.pipe(M.rubber,point(a).toArray(),point(b).toArray(),.047);
  kit.add('box',M.trim,point(meter).toArray(),side==='x'?[.26,1,.66]:[.66,1,.26],q);
  const led=meter.slice();led[side==='x'?0:2]+=Math.sign(side==='x'?x:z)*.15;
  kit.add('box',M.screen,point([led[0],2.1,led[2]]).toArray(),side==='x'?[.035,.22,.4]:[.4,.22,.035],q);
 }
}
function buildPolePicking(){
 const count=G.poles.x.length;polePickMesh=new THREE.InstancedMesh(new THREE.BoxGeometry(1.2,11,1.2),new THREE.MeshBasicMaterial({transparent:true,opacity:0,depthWrite:false,colorWrite:false}),count);
 const m=new THREE.Matrix4();for(let i=0;i<count;i++)polePickMesh.setMatrixAt(i,m.compose(sph(G.poles.x[i],G.poles.y[i],5.5),quatAt(G.poles.x[i],G.poles.y[i]),new THREE.Vector3(1,1,1)));world.add(polePickMesh);
 cabinetMeters.forEach((m,i)=>{m.userData.pole=i;});
}

function detailedPower(){
 const kit=new Kit(world),physical=[],P=G.poles.x.length,phaseColors=[0xc5bfa7,0xbeb3a2,0xa9b8bf];
 const anchor=(i,phase,height=10.7)=>{const x=G.poles.x[i],y=G.poles.y[i],yaw=G.poles.kind[i]===0?-G.poles.angle[i]*Math.PI/180+Math.PI/2:-G.poles.angle[i]*Math.PI/180;
  return sph(x,y,height).add(new THREE.Vector3(phase*1.5,0,0).applyQuaternion(quatAt(x,y,yaw)));};
 for(let i=0;i<P;i++){
  const x=G.poles.x[i],y=G.poles.y[i],parent=G.poles.parent[i],q=quatAt(x,y,-G.poles.angle[i]*Math.PI/180);
  for(let phase=-1;phase<=1;phase++){
   const b=anchor(i,phase),a=parent>=0?anchor(parent,phase):spanCurves[i][0].clone().add(new THREE.Vector3(phase*1.4,0,0).applyQuaternion(quatAt(...polar(G.poles.sector[i]*60+1.6,G.cfg.hub_radius+20))));const line=catenary(a,b,Math.min(1.5,a.distanceTo(b)*.025));physical.push(line);
   for(let j=1;j<line.length;j++)kit.pipe(M.dark,line[j-1].toArray(),line[j].toArray(),.026);
   for(let ring=0;ring<4;ring++)kit.add('cyl',M.white,b.clone().addScaledVector(b.clone().normalize(),-.32+ring*.1).toArray(),[.13,.055,.13],quatAt(x,y));
  }
  const neutralEnd=anchor(i,0,9.9),neutralStart=parent>=0?anchor(parent,0,9.9):spanCurves[i][0].clone().addScaledVector(spanCurves[i][0].clone().normalize(),-.8),neutral=catenary(neutralStart,neutralEnd,Math.min(1.5,neutralStart.distanceTo(neutralEnd)*.025));physical.push(neutral);
  for(let j=1;j<neutral.length;j++)kit.pipe(M.dark,neutral[j-1].toArray(),neutral[j].toArray(),.03);
  kit.pipe(M.trim,sph(x+.25,y,.2).toArray(),sph(x+.25,y,9.9).toArray(),.018);
  const base=sph(x,y,1.2),put=(mat,p,sz)=>kit.add('box',mat,base.clone().add(new THREE.Vector3(...p).applyQuaternion(q)).toArray(),sz,q);
  put(M.trim,[.42,1.5,0],[.65,1.25,.33]);put(M.steel,[.42,1.5,.19],[.57,1.14,.05]);put(M.screen,[.42,1.74,.225],[.38,.24,.025]);
  for(let j=0;j<3;j++)put(M.amber,[.28+j*.14,1.43,.24],[.065,.12,.045]);
  put(M.dark,[.65,1.49,.25],[.045,.16,.05]);
  kit.pipe(M.dark,sph(x,y,2.8).toArray(),sph(x,y,8.7).toArray(),.044);
  const led=new THREE.Mesh(UNIT.box,M.glow.clone());led.scale.set(.38,.07,.035);led.position.copy(base.clone().add(new THREE.Vector3(.42,1.14,.23).applyQuaternion(q)));led.quaternion.copy(q);world.add(led);cabinetMeters.push(led);
  const canvas=document.createElement('canvas');canvas.width=192;canvas.height=96;const texture=new THREE.CanvasTexture(canvas),display=new THREE.Mesh(new THREE.PlaneGeometry(.38,.24),new THREE.MeshBasicMaterial({map:texture}));display.position.copy(base.clone().add(new THREE.Vector3(.42,1.74,.245).applyQuaternion(q)));display.quaternion.copy(q);world.add(display);poleDisplays.push({display,canvas,texture,last:''});
 }
 makeServiceDrops(kit,physical,anchor);
 kit.finish();new LineLayer(physical,0x8b9996);phaseDropFlow=new FlowLayer(phaseDrops,0xffd777,1.5,3,22);buildPolePicking();
}
function buildWaterTower(){
 const group=localGroup(-70,-45,0,0),k=new Kit(group),R=5.1,H=6.12;
 for(let i=0;i<4;i++){const a=i*Math.PI/2+Math.PI/4,x=Math.cos(a)*R,z=Math.sin(a)*R;k.pipe(M.steel,[x*1.3,0,z*1.3],[x,24,z],.22);k.box(M.concrete,x*1.3,.2,z*1.3,1.8,.4,1.8);
  const b=(i+1)*Math.PI/2+Math.PI/4,nx=Math.cos(b)*R,nz=Math.sin(b)*R;
  for(let y=4;y<23;y+=5){k.pipe(M.trim,[x,y,z],[nx,y+5,nz],.09);k.pipe(M.trim,[nx,y,nz],[x,y+5,z],.09);}
 }
 k.add('cyl',M.steel,[0,24,0],[R+.15,.35,R+.15]);k.add('cyl',M.trim,[0,30.3,0],[R+.35,.4,R+.35]);
 k.pipe(M.trim,[0,.4,0],[0,24,0],.26);
 for(let y=0;y<32;y+=.36)k.pipe(M.trim,[R+.4,y,-.32],[R+.4,y,.32],.034);
 for(const z of [-.36,.36])k.pipe(M.steel,[R+.4,0,z],[R+.4,32,z],.05);
 for(let i=0;i<36;i++){const a=i*Math.PI/18,x=Math.cos(a)*(R+.65),z=Math.sin(a)*(R+.65);k.pipe(M.trim,[x,30.5,z],[x,31.55,z],.025);}
 for(const y of [30.5,31.55])metalRing(k,M.trim,[0,y,0],R+.65,.035);
 for(let y=24;y<30;y+=.5)k.box(M.white,R+.18,y,0,.06,.04,.4);
 k.finish();const shell=new THREE.Mesh(new THREE.CylinderGeometry(R,R,H,40,1,true),M.glass);shell.position.y=24+H/2;group.add(shell);
 hub.tank=clickable(group,'tank','tank');hub.tankLevel=new THREE.Mesh(new THREE.CylinderGeometry(R-.12,R-.12,1,40),material('tankwater',0x3399b4,{transparent:true,opacity:.72,roughness:.1,metalness:.15}));hub.tankLevel.quaternion.copy(quatAt(-70,-45));world.add(hub.tankLevel);
}
function detailedVehicle(col,name){
 const g=new THREE.Group(),k=new Kit(g),paint=material('vehicle-'+name,col,{metalness:.55,roughness:.37}),wheels=[];
 k.box(M.steel,0,.7,0,7.4,.28,2.3);k.box(paint,-1.1,1.7,0,4.8,1.8,2.8);k.box(M.dark,2.3,1.45,0,2.1,1.3,2.6);
 k.box(paint,2.3,2.95,0,2.35,.16,2.85);k.box(M.glass,3.37,2.45,0,.06,.95,2.44);k.box(paint,3.38,1.64,0,.12,.48,2.7);
 for(const z of [-1.37,1.37]){
  k.box(M.glass,2.3,2.42,z,1.88,.95,.06);k.box(paint,2.3,1.65,z,2.1,.52,.09);
  for(const x of [1.25,3.33])k.box(paint,x,2.4,z,.11,1.05,.11);
  k.box(M.trim,1.7,1.95,z*1.012,.3,.045,.045);k.box(M.steel,2.25,.91,z*1.06,1.8,.12,.4);
  k.pipe(M.steel,[3,2.45,z],[3.12,2.45,z*1.28],.035);k.box(M.dark,3.12,2.5,z*1.3,.12,.38,.24);
  k.box(M.dark,-.6,.6,z*.8,1.15,.58,.58);k.add('cyl',M.trim,[-.6,.63,z*1.015],[.11,.06,.11],[Math.PI/2,0,0]);
  k.box(M.glow,3.48,1.55,z*.72,.09,.25,.4);k.box(material('brake',0x913827,{emissive:0x862414,emissiveIntensity:.6}),-3.55,1.1,z*.75,.08,.25,.3);
  k.box(M.fabric,2.2,1.75,z*.43,.7,.55,.6);k.box(M.fabric,1.95,2.08,z*.43,.18,.68,.6);
 }
 k.box(M.dark,3.1,2.06,0,.3,.18,2.3);k.add('ring',M.rubber,[2.87,2.15,.62],[.23,.23,.23],[0,Math.PI/2,0]);
 k.box(M.trim,3.6,.98,0,.18,.27,3);k.box(M.trim,-3.6,.88,0,.18,.27,3);
 for(let j=0;j<12;j++)k.box(M.trim,3.47,1.66,-.6+j*.11,.035,.33,.04);
 for(let x=-3.3;x<1;x+=.45)k.box(M.trim,x,1.5,1.42,.06,1.35,.04);
 if(name==='sludge'){k.add('cyl',M.trim,[-1.2,2.1,0],[1.15,4.25,1.15],[0,0,Math.PI/2]);k.pipe(M.dark,[-3.4,2.1,0],[-3.4,.9,1.4],.09);}
 k.box(M.amber,2.2,3.12,0,.8,.16,.24);k.finish();
 for(const x of [-2.45,-.6,2.65])for(const z of [-1.45,1.45]){
  const wheel=new THREE.Group();wheel.position.set(x,.67,z);const wk=new Kit(wheel);
  wk.add('cyl',M.rubber,[0,0,0],[.66,.38,.66],[Math.PI/2,0,0]);wk.add('cyl',M.trim,[0,0,Math.sign(z)*.21],[.37,.045,.37],[Math.PI/2,0,0]);
  for(let j=0;j<8;j++){const a=j*Math.PI/4;wk.add('cyl',M.dark,[Math.cos(a)*.26,Math.sin(a)*.26,Math.sign(z)*.245],[.045,.035,.045],[Math.PI/2,0,0]);}
  for(let j=0;j<20;j++){const a=j*Math.PI/10;wk.box(M.dark,Math.cos(a)*.65,Math.sin(a)*.65,0,.13,.045,.4,[0,0,a-Math.PI/2]);}
  wk.finish();g.add(wheel);wheels.push(wheel);
 }
 g.userData.wheels=wheels;return g;
}
function industrialDetails(){
 const k=new Kit(world),c=G.cfg;
 // Corridors are the same roads the outside route planner follows.
 const spine=c.reactor_pos[0]+70;
 road([[spine,-c.wall_radius],[spine,c.mine_pos[1]+45]],10,.98,0x454b4d);
 for(const key of ['reactor_pos','water_plant_pos','mine_pos','solar_pos','radwaste_pos']){
  const [x,y]=c[key],stand=key==='reactor_pos'?55:key==='solar_pos'?75:key==='radwaste_pos'?42:36;road([[spine,y],[x+stand,y]],8,1,0x454b4d);
 }
 road([c.tower_junction,[c.tower_junction[0],c.tower_pos[1]],[c.tower_pos[0],c.tower_pos[1]]],8,1,0x454b4d);
 for(let x=-c.wall_radius-30;x>spine;x-=32){
  const y=-10,q=quatAt(x,y),base=sph(x,y,0);const put=(mat,p,sz)=>k.add('box',mat,base.clone().add(new THREE.Vector3(...p).applyQuaternion(q)).toArray(),sz,q);
  put(M.steel,[0,4.5,0],[.16,9,.16]);put(M.steel,[0,8.8,1.3],[.14,.14,2.6]);put(M.glow,[0,8.7,2.6],[.65,.08,.4]);
  if(x-32>spine){const line=catenary(sph(x,y,8.5),sph(x-32,y,8.5),.8);for(let j=1;j<line.length;j++)k.pipe(M.dark,line[j-1].toArray(),line[j].toArray(),.035);}
 }
 // Substation: cooling fins, conservators, porcelain discs, bus bars and secure yard.
 const g=localGroup(0,-70,.95,0),yard=new Kit(g);yard.box(M.concrete,0,-.12,0,72,.24,46);
 for(let i=0;i<3;i++){
  const x=-22+i*22;for(const z of [-5.2,5.2])for(let j=0;j<14;j++)yard.box(M.trim,x-5.4+j*.8,4.5,z,.12,6,1.8);
  yard.add('cyl',M.trim,[x,11.1,-2],[1.05,7.5,1.05],[0,0,Math.PI/2]);
  for(let phase=-1;phase<=1;phase++){for(let ring=0;ring<7;ring++)yard.add('cyl',M.white,[x+phase*3,11.7+ring*.47,0],[.72,.16,.72]);yard.pipe(M.trim,[x+phase*3,15,0],[x+phase*3,17,phase*2],.09);}
 }
 for(const z of [-23,23])for(let x=-36;x<=36;x+=3){yard.pipe(M.steel,[x,0,z],[x,3.2,z],.055);for(let h=.4;h<3;h+=.4)yard.pipe(M.trim,[x,h,z],[Math.min(x+3,36),h,z],.018);}
 for(const x of [-36,36])for(let z=-23;z<23;z+=3){yard.pipe(M.steel,[x,0,z],[x,3.3,z],.055);for(let h=.4;h<3;h+=.4)yard.pipe(M.trim,[x,h,z],[x,h,Math.min(23,z+3)],.018);}
 for(const z of [-23,23])for(let x=-36;x<36;x+=.9){yard.add('ring',M.steel,[x,3.4,z],[.32,.32,.32],[0,Math.PI/2,0]);}
 yard.finish();
 k.finish();
}

function updatePhysicalState(s){
 const loads=new Float32Array(G.poles.x.length);
 for(let i=0;i<G.houses.x.length;i++){loads[G.houses.pole[i]]+=s.houses.draw[i];if(phaseDropFlow)phaseDropFlow.active[i]=!!s.houses.power[i];}
 for(let i=loads.length-1;i>=0;i--){const p=G.poles.parent[i];if(p>=0)loads[p]+=loads[i];}
 for(const m of mediumBatches){if(m.material!==M.glow)continue;const original=m.userData.original;m.userData.tags.forEach((id,j)=>{if(!s.houses.power[id]||houseDetails.has(id))m.instanceMatrix.array.fill(0,j*16,j*16+16);else m.instanceMatrix.array.set(original.subarray(j*16,j*16+16),j*16);});m.instanceMatrix.needsUpdate=true;}
 poleDisplays.forEach((v,i)=>{const value=s.poles.span[i]?(loads[i]/1000).toFixed(1):'OFF';if(v.last===value)return;v.last=value;const x=v.canvas.getContext('2d');x.fillStyle='#12231f';x.fillRect(0,0,192,96);x.fillStyle='#b7e6ba';x.font='bold 18px monospace';x.fillText('L1 L2 L3 / '+String(i+1).padStart(3,'0'),7,22);x.font='bold 35px monospace';x.fillText(value+' kW',7,65);x.font='13px monospace';x.fillText('WY / COLONY METER',7,88);v.texture.needsUpdate=true;});
 poleLoads=loads;cabinetMeters.forEach((m,i)=>{const on=s.poles.span[i];m.material.emissiveIntensity=on?.3+Math.min(1.5,loads[i]/12000):0;m.material.color.setHex(on?(loads[i]>18000?0xff834a:0x9bce84):0x30393a);});
 for(const mesh of potableBatches){
  if(mesh.material!==MAT['water-core']&&mesh.material!==MAT['pipe-sightglass']&&mesh.material!==MAT['pipe-ice'])continue;
  mesh.userData.tags.forEach((tag,j)=>{const e=tag?.id>=0?G.utilities.links[tag.id]:null,house=e?G.utilities.nodes[e.b].house:-1;
   const frozen=house>=0&&!s.houses.pipes[house],burst=house>=0&&s.houses.burst[house];if(mesh.material===MAT['pipe-ice']){if(frozen)mesh.instanceMatrix.array.set(mesh.userData.iceOriginal.subarray(j*16,j*16+16),j*16);else mesh.instanceMatrix.array.fill(0,j*16,j*16+16);mesh.instanceMatrix.needsUpdate=true;}mesh.setColorAt(j,new THREE.Color(frozen?0xb6dfff:burst?0x817c6c:0xffffff));
  });if(mesh.instanceColor)mesh.instanceColor.needsUpdate=true;
 }
 for(const {offset,signals} of roadSignals){const phase=(s.t+offset)%12;signals.forEach(({lights,approach})=>{const green=approach%2===0?phase<5:phase>=6&&phase<11,amber=approach%2===0?phase===5:phase===11;lights[0].material.color.setHex(!green&&!amber?0xff392b:0x241e1b);lights[1].material.color.setHex(amber?0xffbc43:0x242119);lights[2].material.color.setHex(green?0x9be2b2:0x17251e);});}
}

function plantDetails(){
 const c=G.cfg;
 for(const [key,w,h,d] of [['water_plant_pos',60,24,40],['mine_pos',60,20,44],['waste_station_pos',40,14,30],['radwaste_pos',70,12,50]]){
  const [x,y]=c[key],yaw=-Math.atan2(y,x),q=quatAt(x,y,yaw),g=localGroup(x,y,0,yaw),k=new Kit(g);
  k.box(M.concrete,0,.26,0,w+22,.5,d+24);
  for(const side of [-1,1]){
   const z=side*(d/2+.08);
   for(let j=-w/2+2;j<w/2;j+=4){k.box(M.steel,j,h/2,z,.23,h,.25);for(let level=5;level<h-2;level+=5){k.box(M.steel,j+1.1,level,z+side*.18,2.35,1.55,.2);k.box(M.glass,j+1.1,level,z+side*.3,2.16,1.32,.04);}}
   k.pipe(M.trim,[-w/2-1.2,1,z],[w/2+1.2,1,z],.17);k.pipe(M.trim,[-w/2-1.2,1,z],[-w/2-1.2,h,z],.17);
   for(let xx=-w/2+1;xx<w/2;xx+=8){k.box(M.steel,xx,3.8,z+side,.12,1,.12);k.box(M.glow,xx,4.3,z+side,1.1,.14,.45);}
  }
  for(let j=0;j<4;j++){
   const xx=-w/2+8+j*(w-16)/3;k.box(M.trim,xx,h+1.1,0,4.4,2.2,3.6);for(let blade=0;blade<10;blade++)k.box(M.dark,xx-1.8+blade*.4,h+2.24,0,.23,.06,3.1);
   k.pipe(M.steel,[xx,h+1,-2],[xx,h+1,-d*.35],.45);
  }
  k.box(M.dark,w/2+.12,3.6,0,.2,6,5.2);for(let j=0;j<14;j++)k.box(M.trim,w/2+.24,.7+j*.42,0,.12,.08,5.2);
  for(let y0=.8;y0<h+1.5;y0+=.35)k.pipe(M.trim,[w/2+.9,y0,d/2-3],[w/2+.9,y0,d/2-2.3],.035);
  for(const zz of [d/2-3.05,d/2-2.25])k.pipe(M.steel,[w/2+.9,.5,zz],[w/2+.9,h+2,zz],.055);
  for(let y0=3;y0<h+1;y0+=1.2)k.add('ring',M.trim,[w/2+1.3,y0,d/2-2.65],[.65,.65,.65],[Math.PI/2,0,0]);
  // Protected compound perimeter, a vehicle opening and a separate pedestrian wicket.
  for(const z of [-d/2-10,d/2+10])for(let xx=-w/2-10;xx<w/2+10;xx+=4){
   k.pipe(M.steel,[xx,.5,z],[xx,3.8,z],.06);for(let yy=1;yy<3.8;yy+=.45)k.pipe(M.trim,[xx,yy,z],[Math.min(xx+4,w/2+10),yy,z],.014);
   for(let xx2=xx;xx2<xx+4;xx2+=.8)k.add('ring',M.steel,[xx2,4,z],[.27,.27,.27],[0,Math.PI/2,0]);
  }
  for(const xx of [-w/2-10,w/2+10])for(let z=-d/2-10;z<d/2+10;z+=4){if(xx>0&&Math.abs(z)<5)continue;k.pipe(M.steel,[xx,.5,z],[xx,3.8,z],.06);for(let yy=1;yy<3.8;yy+=.45)k.pipe(M.trim,[xx,yy,z],[xx,yy,Math.min(z+4,d/2+10)],.014);}
  k.box(M.amber,w/2+10,1.1,-5.6,.7,1.4,.7);for(let j=0;j<10;j++)k.box(j%2?M.white:M.amber,w/2+10,2,-5+j,.13,.13,1);
  for(let j=0;j<7;j++)k.box(M.white,w/2+5,.56,-3+j,.55,.035,.45);
  k.finish();
  const endpoint=sph(x,y).add(new THREE.Vector3(w/2+10,0,0).applyQuaternion(q));
  // Site access roads remain outside the footprint; buildings retain their own orientation.
  const ex=x+Math.cos(yaw)*(w/2+10),ey=y-Math.sin(yaw)*(w/2+10),spine=c.reactor_pos[0]+70;
  road([[spine,ey],[ex,ey],[ex,y]],7,1,0x454b4d);
 }
}

// Unified architectural kit: walls are assembled around openings, not decorated solid boxes.
let campusObjects=[],cargoYard=null,cargoCrane=null,cargoContainers=[],cargoPayload=null,externalFiber=[],spaceFiberPath=[];
function facility(name,x,y,w,h,d,opts={}){
 const g=localGroup(x,y,.65,opts.yaw||0),k=new Kit(g),wall=material('facade-'+name,opts.color||0x8c9387,{metalness:.28,roughness:.68}),floors=Math.max(1,Math.round(h/4)),fh=h/floors;
 g.material=wall;g.userData.facility=name;
 k.box(M.concrete,0,-.35,0,w+2.6,.7,d+2.6);
 for(let level=0;level<floors;level++){
  const yy=level*fh;k.box(M.concrete,0,yy,0,w,.22,d);
  for(let side=0;side<4;side++){
   const width=side%2?d:w,depth=side%2?w:d,bays=Math.max(2,Math.round(width/4.2)),bw=width/bays;
   const box=(mat,u,v,ww,hh,th=.2,off=0)=>k.box(mat,side===0?u:side===2?-u:(side===1?depth/2+off:-depth/2-off),v,side===0?depth/2+off:side===2?-depth/2-off:(side===1?-u:u),side%2?th:ww,hh,side%2?ww:th);
   for(let bay=0;bay<bays;bay++){
    const u=-width/2+(bay+.5)*bw,door=level===0&&side===(opts.front===-1?2:0)&&bay===Math.floor(bays/2);
    box(M.steel,u-bw/2,yy+fh/2,.18,fh,.32,.12);
    if(door){box(M.dark,u,1.55,bw-.25,3.1,.14);box(M.glass,u,1.7,bw-.55,2.35,.08,.13);box(M.trim,u,3.25,bw+.35,.18,.3,.24);box(M.trim,u,1.6,.08,2.8,.16,.22);}
    else{
     box(wall,u,yy+.65,bw-.16,1.3,.25);box(wall,u,yy+fh-.42,bw-.16,.84,.25);
     box(M.glass,u,yy+(fh+.45)/2,bw-.35,fh-2.12,.055,.02);
     box(M.trim,u,yy+1.32,bw-.1,.11,.35,.11);box(M.trim,u,yy+fh-.84,bw-.1,.09,.2,.12);
     box(M.trim,u,yy+(fh+.45)/2,.075,fh-2.12,.12,.1);
     if((bay+level)%3!==1)box(M.glow,u,yy+fh-.98,bw-.9,.08,.09,-.25);
    }
    for(const du of [-bw/2+.22,bw/2-.22])box(M.dark,u+du,yy+.4,.075,.075,.04,.17);
    if(level===0&&!door)for(let rib=0;rib<6;rib++)box(M.trim,u-bw*.35+rib*bw*.14,.67,.035,.8,.04,.15);
   }
   box(M.steel,0,yy+fh-.06,width+.45,.17,.3,.1);
  }
 }
 k.box(M.roof,0,h+.12,0,w+.8,.32,d+.8);
 for(const z of [-d/2,d/2])k.box(M.trim,0,h+.7,z,w+.9,1.1,.18);
 for(const x of [-w/2,w/2])k.box(M.trim,x,h+.7,0,.18,1.1,d);
 const units=Math.max(2,Math.round(w/12));for(let n=0;n<units;n++){
  const xx=(n-(units-1)/2)*8;k.box(M.trim,xx,h+1.35,-d*.18,5,2.1,3.4);k.box(M.steel,xx,h+.4,-d*.18,5.6,.25,4);
  for(let l=0;l<13;l++)k.box(M.dark,xx,h+.48+l*.14,-d*.18+1.73,4.55,.065,.045);
  for(const fx of [-1.2,1.2]){k.add('cyl',M.dark,[xx+fx,h+2.47,-d*.18],[.82,.1,.82]);for(let blade=0;blade<5;blade++)k.box(M.trim,xx+fx,h+2.56,-d*.18,1.45,.05,.12,[0,blade*Math.PI/5,0]);}
  industrialPipe(k,[[xx,h+.9,-d*.18-1.7],[xx,h+.9,-d*.4],[xx,h+3,-d*.4]],.35,M.trim);
 }
 for(const x of [-w/2-.28,w/2+.28]){k.pipe(M.steel,[x,h,-d/2],[x,h,d/2],.12);k.pipe(M.steel,[x,h,d/2],[x,-.25,d/2],.09);for(let yy=1;yy<h;yy+=2)k.box(M.trim,x,yy,d/2,.32,.055,.2);}
 const front=(opts.front===-1?-1:1)*d/2;k.box(M.steel,0,3.65,front+Math.sign(front)*1.5,9,.22,3.5);
 for(let j=0;j<4;j++)k.box(M.concrete,0,-.25-j*.12,front+Math.sign(front)*(1+j*.45),8,.18,.48);
 // Furnished ground floor / visible server hall, according to the facility's purpose.
 for(let row=0;row<2;row++)for(let col=0;col<Math.min(6,Math.floor(w/4));col++){
  const xx=-w/2+3+col*4,zz=-d*.25+row*d*.32;
  if(opts.type==='network'||opts.type==='power'){
   k.box(M.dark,xx,1.3,zz,1.4,2.6,1.1);for(let slot=0;slot<9;slot++){k.box(M.steel,xx,.3+slot*.25,zz+.57,1.3,.17,.04);k.box(M.screen,xx+.42,.3+slot*.25,zz+.61,.25,.05,.03);}
   k.pipe(M.blue,[xx,2.8,zz],[xx,h-1,zz],.06);
  }else{k.box(M.wood,xx,.95,zz,2.2,.14,1.2);k.box(M.fabric,xx,1,zz-.85,.72,.8,.65);k.box(M.screen,xx,1.42,zz+.1,.8,.5,.08);}
 }
 const gate=opts.type==='workshop';if(gate){for(let j=-1;j<=1;j++){const xx=j*w*.27;k.box(M.dark,xx,3.1,-d/2-.1,8,6.2,.1);for(let slat=0;slat<18;slat++)k.box(M.trim,xx,.25+slat*.32,-d/2-.18,7.7,.07,.07);k.box(M.amber,xx,6.45,-d/2-.26,8.5,.2,.18);}}
 k.finish();const label=textSprite(name,'#e0d8b1',32);label.position.set(0,3.2,front+Math.sign(front)*.3);label.scale.set(Math.min(w*.7,18),1.25,1);label.material.depthTest=true;g.add(label);campusObjects.push(g);return g;
}
function industrialPipe(kit,points,r,mat=M.trim){
 const path=[new THREE.Vector3(...points[0])];for(let i=1;i<points.length-1;i++){
  const a=new THREE.Vector3(...points[i-1]),b=new THREE.Vector3(...points[i]),c=new THREE.Vector3(...points[i+1]),bend=Math.min(r*3,a.distanceTo(b)*.3,b.distanceTo(c)*.3),entry=b.clone().addScaledVector(a.clone().sub(b).normalize(),bend),exit=b.clone().addScaledVector(c.clone().sub(b).normalize(),bend);
  path.push(entry);for(let step=1;step<=6;step++){const t=step/6;path.push(entry.clone().multiplyScalar((1-t)**2).addScaledVector(b,2*(1-t)*t).addScaledVector(exit,t*t));}
 }path.push(new THREE.Vector3(...points.at(-1)));
 for(let i=1;i<path.length;i++)kit.pipe(mat,path[i-1].toArray(),path[i].toArray(),r);
 for(let i=1;i<points.length;i++){const p=new THREE.Vector3(...points[i-1]),v=new THREE.Vector3(...points[i]).sub(p).normalize();kit.pipe(M.steel,p.clone().addScaledVector(v,.2).toArray(),p.clone().addScaledVector(v,.2+r*.45).toArray(),r*1.18);}
}
function civicFurniture(k,x,y,width=24,depth=12,yaw=0){
 const base=sph(x,y,1.12),q=quatAt(x,y,yaw),put=(mat,p,sz)=>k.add('box',mat,base.clone().add(new THREE.Vector3(...p).applyQuaternion(q)).toArray(),sz,q);
 for(let px=-width/2;px<width/2;px+=1.2)for(let pz=-depth/2;pz<depth/2;pz+=1.2)put(M.concrete,[px,.025,pz],[1.17,.08,1.17]);
 for(const xx of [-width/2+2,width/2-2]){
  for(let slat=0;slat<5;slat++)put(M.wood,[xx,.65,-2+slat*.19],[3,.1,.16]);put(M.wood,[xx,1.1,-2.2],[3,.85,.12]);
  for(const dx of [-1.1,1.1])put(M.steel,[xx+dx,.32,-1.6],[.12,.64,.85]);
  put(M.steel,[xx,3.4,depth/2],[.12,6.8,.12]);put(M.trim,[xx,6.72,depth/2],[.75,.18,.75]);put(M.glow,[xx,6.62,depth/2],[.6,.07,.6]);
  put(M.concrete,[xx,.45,2],[3.6,.9,2]);for(let twig=0;twig<8;twig++)put(M.fabric,[xx-1.4+twig*.4,1.15,2],[.13,.6+(twig%3)*.18,.13]);
 }
}
function parkingLot(x,y,w,d,yaw=0,count=6){
 const g=localGroup(x,y,.9,yaw),k=new Kit(g);k.box(M.dark,0,.04,0,w,.12,d);
 for(let j=0;j<=count;j++)k.box(M.white,-w/2+j*w/count,.12,0,.1,.025,d*.64);
 k.box(M.white,0,.12,d*.33,w,.025,.1);
 for(let j=0;j<count;j++){k.box(M.concrete,-w/2+(j+.5)*w/count,.25,-d*.27,w/count*.68,.24,.32);}
 for(const xx of [-w/2,w/2]){k.pipe(M.steel,[xx,.2,d/2],[xx,7,d/2],.07);k.box(M.glow,xx,6.95,d/2-1,.55,.1,2);}
 k.finish();return g;
}
function equipmentCabinet(x,y,w,h,d,color,yaw=0){
 const g=localGroup(x,y,.4,yaw),k=new Kit(g),paint=material('cabinet-'+color,color,{metalness:.5,roughness:.5});g.material=paint;
 k.box(M.concrete,0,0,0,w+.8,.5,d+.8);k.box(paint,0,h/2,0,w,h,d);k.box(M.trim,0,h+.15,0,w+.3,.25,d+.3);
 const n=Math.max(2,Math.round(w/2));for(let j=0;j<n;j++){const xx=-w/2+(j+.5)*w/n;k.box(M.steel,xx,h/2,d/2+.06,w/n-.15,h-.24,.08);k.box(M.trim,xx+w/n*.3,h*.45,d/2+.14,.08,.35,.09);for(let slot=0;slot<10;slot++)k.box(M.dark,xx,h*.2+slot*.11,d/2+.12,w/n*.75,.045,.045);k.box(M.screen,xx,h*.76,d/2+.15,.42,.26,.04);}
 for(const side of [-1,1]){for(let fin=0;fin<12;fin++)k.box(M.trim,side*(w/2+.2),h*.5,-d*.4+fin*d*.07,.4,h*.65,.08);industrialPipe(k,[[side*w*.3,0,-d/2-.3],[side*w*.3,h*.7,-d/2-.3],[side*w*.3,h*.7,-d/2]],.11,M.trim);}
 k.finish();return g;
}

function buildCampus(){
 const k=new Kit(world);road(arcPts(0,360,118,120),12,1.03,0x454b4d);road([[-118,0],[118,0]],12,1.03,0x454b4d);road([[0,0],[0,55]],10,1.03,0x454b4d);
 for(const x of [-53,53])road([[x,0],[x,-105]],9,1.03,0x454b4d);
 // Traffic and cargo use this complete inner distributor, outside the civic campus.
 road(arcPts(0,360,210,160),11,1.02,0x454b4d);
 for(const r of [109,127])ribbon(arcPts(0,360,r,120),3.4,1.15,0x9d9e8c,{map:pavingTexture});
 for(const path of [[[0,95],[0,109]],[[88,46],[88,69],[97,76]],[[-88,47],[-88,65],[-98,72]],[[-38,29],[-38,9]],[[43,47],[43,9]],[[-40,-31],[-40,-8]]])ribbon(path,3,1.16,0xa4a693,{map:pavingTexture});
 for(const [x,y,w,d] of [[0,53,44,16],[44,20,25,16],[-43,18,23,14],[-84,58,24,10],[88,57,22,10]])civicFurniture(k,x,y,w,d);
 parkingLot(-90,-12,28,12,0,7);parkingLot(90,-12,28,12,0,7);parkingLot(0,108,42,9,0,9);
 facility('COLONY ADMINISTRATION',-38,43,27,76,25,{color:0x81948d,type:'office',front:-1});
 facility('SCIENCE / HABITAT TOWER',43,60,25,92,24,{color:0x8d8f7e,type:'office',front:-1});
 // Tower roof crowns and external bracing create a recognisable skyline.
 for(const [x,y,h,w] of [[-38,43,76,27],[43,60,92,25]]){
  const g=localGroup(x,y,.65,0),kk=new Kit(g);
  for(const sx of [-1,1])for(const sz of [-1,1])kk.pipe(M.steel,[sx*(w/2+.3),0,sz*12.8],[sx*(w/2+.3),h+3,sz*12.8],.18);
  kk.pipe(M.trim,[0,h,0],[0,h+16,0],.15);kk.add('ball',M.glow,[0,h+16,0],[.24,.24,.24]);kk.finish();
 }
 // Heated paving strips share the power domain, with joints and inspection panels.
 for(let x=-110;x<=110;x+=8){const q=quatAt(x,9);k.add('box',M.amber,sph(x,9,1.25).toArray(),[5.8,.025,.045],q);}
 for(const [x,y] of [[-58,-45],[55,-40],[110,0],[-110,0]]){const q=quatAt(x,y);k.add('box',M.steel,sph(x,y,2).toArray(),[1.2,1.8,.7],q);k.add('box',M.screen,sph(x,y+.36,2.4).toArray(),[.65,.22,.025],q);}
 k.finish();
}
function containerModel(color=0x985139,code='WY-426',long=true){
 const g=new THREE.Group(),k=new Kit(g),length=long?12.2:6.1,paint=material('container-'+color,color,{metalness:.65,roughness:.56});
 k.box(M.steel,0,.12,0,length,.24,2.44);k.box(paint,0,1.5,0,length,2.65,2.4);k.box(paint,0,2.87,0,length,.12,2.44);
 for(const side of [-1,1]){
  for(let x=-length/2+.15;x<length/2;x+=.27)k.box(M.trim,x,1.48,side*1.22,.055,2.55,.045);
  for(const yy of [.2,2.78])k.box(M.steel,0,yy,side*1.25,length,.14,.12);
 }
 for(const x of [-length/2,length/2]){
  for(const z of [-1.16,1.16])k.box(M.trim,x,1.45,z,.16,2.9,.16);
  for(const z of [-.62,.62]){k.box(paint,x+Math.sign(x)*.08,1.5,z,.11,2.5,1.08);k.pipe(M.trim,[x+Math.sign(x)*.17,.3,z],[x+Math.sign(x)*.17,2.65,z],.035);for(const yy of [.65,1.9])k.box(M.steel,x+Math.sign(x)*.2,yy,z,.08,.09,.3);}
  for(const z of [-1.13,1.13])for(const yy of [.15,2.78])k.box(M.dark,x+Math.sign(x)*.11,yy,z,.07,.09,.11);
 }
 k.finish();const label=textSprite(code,'#e7d9b5',28);label.position.set(0,2,1.275);label.scale.set(3,.4,1);label.material.depthTest=true;g.add(label);return g;
}
function freightVehicle(){
 const g=detailedVehicle(0xb79053,'freight-cab'),k=new Kit(g);g.scale.set(.95,.95,.95);
 k.box(M.steel,-6,.82,0,14,.3,2.75);for(const x of [-10,-8.5,-7])for(const z of [-1.5,1.5]){
  k.add('cyl',M.rubber,[x,.68,z],[.66,.38,.66],[Math.PI/2,0,0]);k.add('cyl',M.trim,[x,.68,z*1.12],[.35,.04,.35],[Math.PI/2,0,0]);
 }
 k.finish();const load=containerModel(0x995636,'WY / CARGO',false);load.position.set(-7,1.04,0);load.visible=false;g.add(load);g.userData.cargo=load;return g;
}
function buildCargoDepot(){
 const [angle,radius]=G.cfg.cargo_depot,[x,y]=polar(angle,radius+22),yaw=-angle*Math.PI/180-Math.PI/2;cargoYard=localGroup(x,y,.9,yaw);const k=new Kit(cargoYard);
 k.box(M.concrete,0,.05,0,68,.1,41);for(let n=0;n<24;n++){
  const col=n%8,row=[2,0,1][Math.floor(n/8)],c=containerModel([0x975537,0xa56a39,0x737e75,0x47616b][n%4],'WY '+String(60400+n));c.position.set((col-3.5)*7.5,.14+Math.floor(row/2)*2.92,-8+(row%2)*3.1);if(n%2)c.rotation.y=Math.PI; c.scale.x=.5; cargoYard.add(c);cargoContainers.push(c);
 }
 for(const z of [-17,21]){k.box(M.steel,0,.21,z,68,.18,.18);for(let x=-33;x<34;x+=2)k.box(M.concrete,x,.08,z,1,.15,1.6);}
 for(let x=-31;x<32;x+=4){k.box(M.white,x,.13,15,2,.03,.14);k.box(M.amber,x,.13,22,1.2,.03,.14);}
 cargoCrane=new THREE.Group();const ck=new Kit(cargoCrane);
 for(const z of [-17,21])for(const xx of [-3,3]){
  ck.box(M.amber,xx,9.5,z,.7,19,.7);ck.pipe(M.steel,[xx,.5,z],[xx,12,z+(z<0?5:-5)],.2);ck.add('cyl',M.dark,[xx,.7,z],[.62,.5,.62],[Math.PI/2,0,0]);
 }
 for(const xx of [-3,3]){ck.box(M.amber,xx,19.5,2,.8,1.2,41);for(let z=-17;z<21;z+=3)ck.pipe(M.steel,[xx,19,z],[xx,20.1,z+3],.07);}
 for(let z=-17;z<=21;z+=3){ck.box(M.amber,0,20.1,z,7,.3,.25);ck.pipe(M.trim,[-3,20.3,z],[3,20.3,Math.min(z+3,21)],.09);}for(const xx of [-3.5,3.5])ck.box(M.steel,xx,21,2,.35,.15,42);
 ck.box(M.glass,3.5,18.6,15,3,2.1,3);ck.finish();cargoYard.add(cargoCrane);
 const trolley=new THREE.Group(),tk=new Kit(trolley);tk.box(M.steel,0,20.6,0,4.5,1,3);tk.add('cyl',M.trim,[0,20.4,0],[.55,3,.55],[0,0,Math.PI/2]);tk.finish();cargoCrane.add(trolley);cargoCrane.userData.trolley=trolley;
 const hook=new THREE.Group(),hk=new Kit(hook);hk.box(M.amber,0,0,0,6.4,.35,2.7);hk.pipe(M.trim,[0,.2,0],[0,1.1,0],.14);hk.finish();cargoCrane.add(hook);cargoCrane.userData.hook=hook;
 const cables=new THREE.Mesh(new THREE.CylinderGeometry(.035,.035,1,5),M.dark);cargoCrane.add(cables);cargoCrane.userData.cable=cables;
 cargoPayload=containerModel(0x975537,'WY / LIFT',false);cargoCrane.add(cargoPayload);cargoPayload.visible=false;
 k.finish();facility('FREIGHT / DISPATCH',...polar(angle+11,radius+20),18,9,14,{yaw,color:0x968369,type:'office'});
}
function updateCargo(s){
 if(!cargoCrane||!s.cargo)return;const c=s.cargo,on=c.phase!=='WAIT',t=c.progress,idx=c.loaded%cargoContainers.length,source=cargoContainers[idx],sx=source.position.x,sz=source.position.z,sy=source.position.y;
 cargoContainers.forEach((g,i)=>g.visible=i>=c.loaded&&!(on&&i===idx));cargoPayload.visible=on;
 const lifted=THREE.MathUtils.smoothstep(t,0,.25),travel=THREE.MathUtils.smoothstep(t,.25,.68),lower=THREE.MathUtils.smoothstep(t,.7,.98);
 const r=s.rovers.find(v=>v.name===('freight-'+(c.truck-(s.rovers.filter(v=>v.name.startsWith('transit')).length)+1))),target=new THREE.Vector3(7,1.1,24.2);if(r){const q=quatAt(r.x,r.y,-r.heading),p=sph(r.x-Math.sin(r.heading)*2.2,r.y+Math.cos(r.heading)*2.2,1.08).add(new THREE.Vector3(-7*.95,1.04*.95,0).applyQuaternion(q));cargoYard.updateMatrixWorld(true);target.copy(cargoYard.worldToLocal(p));}
 const xx=sx+(target.x-sx)*travel,zz=sz+(target.z-sz)*travel,yy=sy+(14-sy)*lifted-(14-target.y)*lower;
 cargoCrane.position.x=xx;cargoPayload.position.set(0,yy,zz);cargoCrane.userData.hook.position.set(0,yy+3.05,zz);cargoCrane.userData.trolley.position.z=zz;
 const cable=cargoCrane.userData.cable,hookY=yy+4.1;cable.position.set(0,(20.4+hookY)/2,zz);cable.scale.y=Math.max(.1,20.4-hookY);
}

function buildExternalGrid(){
 const c=G.cfg,kit=new Kit(world),nodes=new Map(),physical=[];
 function node(x,y,h=15.2,yaw=0){const key=[x.toFixed(4),y.toFixed(4),h.toFixed(3)].join('|');if(nodes.has(key))return nodes.get(key);const q=quatAt(x,y,yaw),p=sph(x,y,h),n={x,y,h,q,p};nodes.set(key,n);
  const base=sph(x,y,.2),local=(mat,pos,size)=>kit.add('box',mat,base.clone().add(new THREE.Vector3(...pos).applyQuaternion(q)).toArray(),size,q);
  kit.pipe(M.steel,base.toArray(),p.toArray(),.22);local(M.concrete,[0,.12,0],[.9,.24,.9]);local(M.trim,[0,h-.7,0],[3.6,.2,.25]);
  local(M.steel,[.4,2.1,0],[.68,1.25,.4]);local(M.screen,[.4,2.36,.22],[.4,.22,.035]);local(M.amber,[.4,1.85,.23],[.4,.07,.04]);
  for(let phase=-1;phase<=1;phase++)for(let disc=0;disc<5;disc++)kit.add('cyl',M.white,p.clone().add(new THREE.Vector3(phase*1.4,-.45+disc*.09,0).applyQuaternion(q)).toArray(),[.16,.055,.16],q);
  local(M.steel,[0,h-2,1],[.14,.14,2.3]);local(M.glow,[0,h-2.1,2.1],[.8,.12,.4]);kit.pipe(M.trim,base.clone().add(new THREE.Vector3(.24,0,0).applyQuaternion(q)).toArray(),p.clone().add(new THREE.Vector3(.24,-1,0).applyQuaternion(q)).toArray(),.018);
  return n;
 }
 const anchor=(n,phase,dh=0)=>n.p.clone().add(new THREE.Vector3(phase*1.4,dh,0).applyQuaternion(n.q));
 function circuit(flat){const samples=[];for(let i=1;i<flat.length;i++){
  const a=flat[i-1],b=flat[i],L=Math.hypot(b[0]-a[0],b[1]-a[1]),N=Math.max(1,Math.ceil(L/42)),yaw=-Math.atan2(b[1]-a[1],b[0]-a[0])+Math.PI/2;
  for(let j=0;j<N;j++){const t=j/N;samples.push(node(a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t,(a[2]??15.2)+((b[2]??15.2)-(a[2]??15.2))*t,yaw));}
 }const last=flat.at(-1);samples.push(node(last[0],last[1],last[2]??15.2));const center=[],fiber=[];
 for(let i=1;i<samples.length;i++){
  const a=samples[i-1],b=samples[i],sag=Math.min(1.8,a.p.distanceTo(b.p)*.035);
  for(let phase=-1;phase<=1;phase++){const curve=catenary(anchor(a,phase),anchor(b,phase),sag);physical.push(curve);for(let j=1;j<curve.length;j++)kit.pipe(M.dark,curve[j-1].toArray(),curve[j].toArray(),.045);if(!phase)center.push(curve);}
  const n=catenary(anchor(a,0,-.8),anchor(b,0,-.8),sag);physical.push(n);const f=catenary(anchor(a,0,-2),anchor(b,0,-2),sag);physical.push(f);fiber.push(f);
 }return {center,fiber};}
 const main=circuit([[c.reactor_pos[0]+60,-60,16.5],[c.reactor_pos[0]+86,-12,15.2],[-988,-12,15.2],[-c.wall_radius-40,-12,15.2],[-164,-12,14],[0,-70,16.5]]);
 trunkCurves=main.center;hub.trunkLayer=new LineLayer(trunkCurves,0xf2c14e);
 const mobile=circuit([[-988,-12,15.2],[-988,c.tower_pos[1]+40,15.2],[c.tower_pos[0]+12,c.tower_pos[1],12]]);
 const space=circuit([[-988,c.tower_pos[1]+40,15.2],[-988,c.dish_pos[1]+105,15.2],[c.dish_pos[0]+88,c.dish_pos[1]+105,15.2],[c.dish_pos[0]+88,c.dish_pos[1],15.2],[c.dish_pos[0]+44,c.dish_pos[1],12]]);
 towerCurves=[...mobile.center,...space.center];hub.towerLayer=new LineLayer(towerCurves,0xf2c14e);
 cableTowerCurves=[...main.fiber,...mobile.fiber,...space.fiber];hub.cableTowerLayer=new LineLayer(cableTowerCurves,0x4fd1c5);externalFiber=cableTowerCurves;
 const solar=circuit([[c.solar_pos[0]+70,c.solar_pos[1]+30,10],[c.reactor_pos[0]+86,-40,15.2],[c.reactor_pos[0]+60,-60,16.5]]);solarCurves=[solar.center.flat()];hub.solarLayer=new LineLayer(solarCurves,0xf2c14e);
 feederCurves=[];for(let sector=0;sector<c.sectors;sector++){
  const [x,y]=polar(sector*60+1.6,c.hub_radius+20);node(x,y,10.7,0);const way=circuit([[0,-70,16.5],...arcPts(270,sector*60+1.6+(sector<4?360:0),c.hub_radius+20,Math.max(2,sector*6+8)).map(p=>[...p,10.7]),[x,y,10.7]]);feederCurves.push(way.center.flat());
 }
 hub.feederLayer=new LineLayer(feederCurves,0xf2c14e);
 // The public fibre backbone leaves the network building through a roof termination.
 const comms=circuit([[88,34,20],[164,12,15.2],[-164,-12,14],[-c.wall_radius-40,-12,15.2],[-988,-12,15.2]]);
 spaceFiberPath=[...comms.fiber.flat(),...mobile.fiber.slice(0,Math.ceil(Math.abs(c.tower_pos[1]+52)/42)).flat(),...space.fiber.flat()];new LineLayer(comms.fiber,0x4fd1c5);
 for(let sector=0;sector<c.sectors;sector++){const rp=polar(sector*60+1.6,c.hub_radius+20),cab=polar(sector*60+4.5,c.hub_radius+20),fiber=[sph(88,34,18),sph(164,12,13.2),...arcPts(Math.atan2(12,164)*180/Math.PI,sector*60+4.5,164,Math.max(4,sector*16)).map(p=>sph(...p,8.7)),sph(...cab,8.7),sph(...rp,8.7)];new LineLayer([fiber],0x4fd1c5);for(let j=1;j<fiber.length;j++)kit.pipe(M.dark,fiber[j-1].toArray(),fiber[j].toArray(),.028);}
 kit.finish();new LineLayer(physical,0x88958d);
}
function secureCompound(x,y,w,d,entrance=1){
 const g=localGroup(x,y,.5,0),k=new Kit(g);k.box(M.concrete,0,.08,0,w,.16,d);
 for(const z of [-d/2,d/2])for(let xx=-w/2;xx<w/2;xx+=5){k.pipe(M.steel,[xx,0,z],[xx,3.1,z],.055);for(let yy=.4;yy<3;yy+=.42)k.pipe(M.trim,[xx,yy,z],[Math.min(w/2,xx+5),yy,z],.014);k.pipe(M.steel,[xx,3.1,z],[Math.min(w/2,xx+5),3.1,z],.025);}
 for(const xx of [-w/2,w/2])for(let z=-d/2;z<d/2;z+=5){if(xx>0&&Math.abs(z)<9)continue;k.pipe(M.steel,[xx,0,z],[xx,3.1,z],.055);for(let yy=.4;yy<3;yy+=.42)k.pipe(M.trim,[xx,yy,z],[xx,yy,Math.min(d/2,z+5)],.014);}
 for(let j=0;j<12;j++)k.box(j%2?M.white:M.amber,w/2,1.8,-6+j,.16,.16,1);
 for(const z of [-7,7]){k.box(M.amber,w/2,1,z,.65,1.5,.65);k.box(M.glow,w/2,2,z,.26,.22,.26);}
 k.finish();facility('SECURITY / ACCESS',x+w/2-5,y+13,7,4,6,{color:0x8d947f});parkingLot(x+w/2-21,y-18,26,13,0,6);
 return g;
}
function buildSpaceDish(){
 const [x,y]=G.cfg.dish_pos;secureCompound(x,y,160,128);const base=localGroup(x,y,0,0),k=new Kit(base);
 k.add('cyl',M.concrete,[0,1,0],[17,2,17]);k.add('cyl',M.steel,[0,3,0],[12,4,12]);
 for(let n=0;n<48;n++){const a=n*Math.PI/24;k.add('box',M.trim,[Math.cos(a)*12.2,3,Math.sin(a)*12.2],[.55,2.5,.55],[0,-a,0]);}
 const az=new THREE.Group();base.add(az);const yoke=new Kit(az);
 for(const side of [-1,1]){yoke.box(M.trim,side*12,18,0,4,30,8);yoke.pipe(M.steel,[side*12,5,-7],[side*12,31,0],.75);yoke.pipe(M.steel,[side*12,5,7],[side*12,31,0],.75);yoke.add('cyl',M.dark,[side*12,32,0],[2.8,4.5,2.8],[0,0,Math.PI/2]);}
 yoke.box(M.steel,0,10,0,28,2,12);yoke.finish();const dish=new THREE.Group();dish.position.y=34;dish.rotation.x=-.55;az.add(dish);
 const R=32,F=23.68,pos=[],idx=[],rings=20,segs=96;
 for(let ring=0;ring<=rings;ring++)for(let j=0;j<segs;j++){const r=R*ring/rings,a=j*Math.PI*2/segs;pos.push(r*Math.cos(a),r*r/(4*F),r*Math.sin(a));}
 for(let r=0;r<rings;r++)for(let j=0;j<segs;j++){const a=r*segs+j,b=r*segs+(j+1)%segs,c=(r+1)*segs+j,d=(r+1)*segs+(j+1)%segs;idx.push(a,b,c,b,d,c);}
 const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(pos,3));geo.setIndex(idx);geo.computeVertexNormals();dish.add(new THREE.Mesh(geo,new THREE.MeshStandardMaterial({color:0xc5ceca,metalness:.63,roughness:.33,side:THREE.DoubleSide})));
 const frame=new Kit(dish);for(let radial=0;radial<48;radial++){
  const a=radial*Math.PI/24;for(let j=1;j<=12;j++){const r0=R*(j-1)/12,r1=R*j/12;frame.pipe(M.steel,[r0*Math.cos(a),r0*r0/(4*F)-.65,r0*Math.sin(a)],[r1*Math.cos(a),r1*r1/(4*F)-.65,r1*Math.sin(a)],.1);}
 }
 for(let ring=1;ring<=8;ring++){const r=ring*4,height=r*r/(4*F);metalRing(frame,M.trim,[0,height-.3,0],r,.085);}
 for(let n=0;n<4;n++){const a=n*Math.PI/2+Math.PI/4;frame.pipe(M.trim,[Math.cos(a)*29,29*29/(4*F),Math.sin(a)*29],[Math.cos(a)*2.5,F-2,Math.sin(a)*2.5],.19);}
 frame.add('cyl',M.steel,[0,F-1,0],[3,.55,3]);frame.add('cyl',M.trim,[0,F-2,0],[1.2,2,1.2]);frame.box(M.dark,0,-2,0,8,3.5,7);frame.finish();
 for(let h=4;h<31;h+=.4)k.pipe(M.trim,[14,h,-.5],[14,h,.5],.035);for(const z of [-.55,.55])k.pipe(M.steel,[14,3,z],[14,32,z],.055);
 k.finish();complex.dishGroup=clickable(base,'dish','dish');complex.dishAzimuth=az;facility('DEEP SPACE / TRACKING',x+48,y+30,26,10,18,{type:'network',color:0x85938e});
 addLabel('DEEP-SPACE ARRAY / 64 m',x,y,82,'#b5cec5','mid');
 const c=G.cfg;road([[c.tower_pos[0]+30,c.tower_pos[1]+40],[c.tower_pos[0]+30,y+105],[x+88,y+105],[x+88,y],[x+68,y]],12,1.05,0x454b4d);
}
function reactorIndustry(){
 const c=G.cfg,[rx,ry]=c.reactor_pos,g=localGroup(rx,ry,0,0),k=new Kit(g);
 // Pressurised containment seams, access galleries and cable ladders.
 for(const h of [4,18,34,49])metalRing(k,M.trim,[0,h,0],46.35,.16);
 for(let n=0;n<24;n++){const a=n*Math.PI/12,x=Math.cos(a)*46.3,z=Math.sin(a)*46.3;k.pipe(M.trim,[x,0,z],[x,49,z],.13);if(n%3===0){k.box(M.steel,x,18,z,4,.25,3,[0,-a,0]);}}
 for(let yy=5;yy<50;yy+=.36)k.pipe(M.trim,[47,yy,-.4],[47,yy,.4],.04);
 for(const z of [-.45,.45])k.pipe(M.steel,[47,1,z],[47,52,z],.07);
 for(const side of [-1,1]){
  industrialPipe(k,[[-87,8,side*60],[-67,8,side*60],[-67,8,side*26],[-41,8,side*26]],1.7,M.trim);
  industrialPipe(k,[[-84,13,side*60],[-60,13,side*60],[-60,13,side*18],[-41,13,side*18]],1.25,M.steel);
  for(let x=-84;x<=-47;x+=9){k.box(M.concrete,x,2,side*30,3,4,3);k.box(M.steel,x,5,side*30,3.6,.6,5);}
 }
 industrialPipe(k,[[18,18,40],[18,18,63],[18,12,70]],1.4,M.trim);industrialPipe(k,[[26,14,38],[26,14,58],[26,7,70]],1,M.steel);
 for(const xx of [45,60,75]){
  k.box(M.concrete,xx,.4,-65,14,.8,12);k.box(M.steel,xx,4.8,-65,10,8,7);
  for(const z of [-70,-60])for(let fin=0;fin<18;fin++)k.box(M.trim,xx-4.5+fin*.5,4.4,z,.11,6.5,2);
  k.add('cyl',M.trim,[xx,9.7,-65],[1.3,8,1.3],[0,0,Math.PI/2]);
  for(let phase=-1;phase<=1;phase++)for(let disc=0;disc<9;disc++)k.add('cyl',M.white,[xx+phase*3,10.5+disc*.45,-65],[.75,.16,.75]);
  industrialPipe(k,[[xx,14.8,-65],[xx,16.5,-60],[60,16.5,-60]],.18,M.trim);
 }
 k.finish();complex.tw1.visible=false;complex.tw2.visible=false;
 for(const z of [-60,60]){
  const points=[];for(let i=0;i<=24;i++){const h=i/24*90,r=13+10*((h-55)/55)**2;points.push(new THREE.Vector2(r,h));}
  const tower=new THREE.Mesh(new THREE.LatheGeometry(points,40),new THREE.MeshStandardMaterial({color:0x999b91,roughness:.93,side:THREE.DoubleSide}));tower.position.copy(sph(rx-90,ry+z));tower.quaternion.copy(quatAt(rx-90,ry+z));world.add(tower);
  const tk=new Kit(world),q=quatAt(rx-90,ry+z);for(let n=0;n<20;n++){const a=n*Math.PI/10;tk.pipe(M.concrete,sph(rx-90+Math.cos(a)*23,ry+z+Math.sin(a)*23,0).toArray(),sph(rx-90+Math.cos(a)*21,ry+z+Math.sin(a)*21,8).toArray(),.6);}tk.finish();
 }
 const hall=facility('TURBINE / GENERATOR HALL',rx+10,ry+80,70,22,34,{type:'power',color:0x8d9389});complex.turbine.visible=false;
 facility('HEAT RECOVERY / EXCHANGERS',rx+12,ry-120,52,15,27,{type:'power',color:0x7b8c86});
 facility('REACTOR MAINTENANCE',rx+140,ry+70,58,17,38,{type:'workshop',color:0x9a9581});
 road([[rx+70,-155],[rx+70,145]],18,1.07,0x454b4d);road([[rx-155,-120],[rx+70,-120],[rx+155,-120],[rx+155,145]],14,1.07,0x454b4d);
 parkingLot(rx+140,-42,47,22,0,9);secureCompound(rx+48,-60,105,44);const furniture=new Kit(world);civicFurniture(furniture,rx+95,20,12,8);furniture.finish();
}
function streetSignals(){
 // Geometry and vehicle logic consume the same junction list and phase offset.
 for(const old of roadSignals)for(const s of old.signals){if(s.group)world.remove(s.group);}roadSignals=[];
 const batch=new Kit(world),lampData=[];
 for(const j of G.junctions){const a=j.angle*Math.PI/180,q=quatAt(j.x,j.y,-a),base=sph(j.x,j.y,1.1),signals=[];
  for(let approach=0;approach<4;approach++){
   const angle=approach*Math.PI/2,sg=new THREE.Group(),k=new Kit(sg),normal=new THREE.Vector3(Math.cos(angle),0,Math.sin(angle)),side=new THREE.Vector3(-Math.sin(angle),0,Math.cos(angle));
   sg.position.copy(base.clone().add(normal.clone().multiplyScalar(11).addScaledVector(side,-5.9).applyQuaternion(q)));sg.quaternion.copy(q).multiply(new THREE.Quaternion().setFromAxisAngle(UP,Math.PI/2-angle));sg.updateMatrixWorld(true);
   k.pipe(M.steel,[0,0,0],[0,5.3,0],.075);k.box(M.dark,0,4.6,0,.55,1.55,.4);k.box(M.white,0,4.6,-.22,.66,1.68,.045);
   for(let i=0;i<3;i++){k.box(M.dark,0,5.12-i*.46,.2,.56,.055,.55);}
   const lights=[];for(let i=0;i<3;i++){const m=new THREE.Matrix4().makeTranslation(0,5.04-i*.46,.23).premultiply(sg.matrixWorld),record={m,color:0x19221c,index:lampData.length};lampData.push(record);lights.push({material:{color:{setHex:value=>{record.color=value;if(record.mesh){record.mesh.setColorAt(record.index,new THREE.Color(value));record.mesh.instanceColor.needsUpdate=true;}}}}});}
   for(const [key,bucket] of k.buckets){if(!batch.buckets.has(key))batch.buckets.set(key,{shape:bucket.shape,mat:bucket.mat,items:[]});for(const item of bucket.items){item.matrix.premultiply(sg.matrixWorld);batch.buckets.get(key).items.push(item);}}signals.push({lights,approach});
   const stop=base.clone().add(normal.clone().multiplyScalar(12).applyQuaternion(q));batch.add('box',M.white,stop.toArray(),[.28,.045,4.2],q.clone().multiply(new THREE.Quaternion().setFromAxisAngle(UP,-angle)));
  }roadSignals.push({...j,signals});
 }

 batch.finish();const lamps=new THREE.InstancedMesh(new THREE.CircleGeometry(.18,12),new THREE.MeshBasicMaterial({color:0xffffff,side:THREE.DoubleSide}),lampData.length);lampData.forEach(r=>{r.mesh=lamps;lamps.setMatrixAt(r.index,r.m);lamps.setColorAt(r.index,new THREE.Color(r.color));});lamps.instanceMatrix.needsUpdate=true;world.add(lamps);
}

let oceanFlow=null,intakePool=null,intakeHeaters=[],thermalFlow=null;
function coastHeight(x,y,height){
 if(Math.hypot(x,y)<900)return height;
 const az=Math.atan2((y-550)/1150,(x+2350)/900),q=Math.hypot((x+2350)/900,(y-550)/1150)/(1+.08*Math.sin(3*az)+.05*Math.sin(7*az)+.025*Math.sin(11*az)),coast=sstep(0,1,Math.max(0,Math.min(1,(1.10-q)/.16)));height+=( -26-22*Math.max(0,1-q*q)-height)*coast;
 const river=[[500,1550,46],[50,1490,34],[-410,1250,23],[-900,1060,12],[-1450,840,1],[-2050,740,-8]];
 for(let i=1;i<river.length;i++){const a=river[i-1],b=river[i],dx=b[0]-a[0],dy=b[1]-a[1],t=THREE.MathUtils.clamp(((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy),0,1),dist=Math.hypot(x-a[0]-dx*t,y-a[1]-dy*t),blend=sstep(0,1,THREE.MathUtils.clamp((95-dist)/70,0,1));height+=(a[2]+(b[2]-a[2])*t-2-height)*blend;}
 return height;
}
function seaPoint(x,y,level=-8){return sph(x,y,level-terrainH(x,y));}
function metalRing(k,mat,center,radius,thickness=.09){
 for(let i=0;i<64;i++){const a=i*Math.PI/32,b=(i+1)*Math.PI/32;k.pipe(mat,[center[0]+Math.cos(a)*radius,center[1],center[2]+Math.sin(a)*radius],[center[0]+Math.cos(b)*radius,center[1],center[2]+Math.sin(b)*radius],thickness);}
}
function buildOcean(){
 const c=G.cfg,[cx,cy]=c.ocean_center,[rx,ry]=c.ocean_radii,level=c.ocean_level_m,pos=[],idx=[],rings=50,segs=160;
 for(let r=0;r<=rings;r++)for(let j=0;j<segs;j++){const a=j*Math.PI*2/segs,x=cx+rx*1.2*r/rings*Math.cos(a),y=cy+ry*1.2*r/rings*Math.sin(a),p=seaPoint(x,y,level);pos.push(p.x,p.y,p.z);}
 for(let r=0;r<rings;r++)for(let j=0;j<segs;j++){const a=r*segs+j,b=r*segs+(j+1)%segs,cc=(r+1)*segs+j,d=(r+1)*segs+(j+1)%segs;idx.push(a,cc,b,b,cc,d);}
 const geom=new THREE.BufferGeometry();geom.setAttribute('position',new THREE.Float32BufferAttribute(pos,3));geom.setIndex(idx);geom.computeVertexNormals();
 const ice=new THREE.Mesh(geom,new THREE.MeshStandardMaterial({color:0x7cabb4,metalness:.18,roughness:.32,side:THREE.DoubleSide,envMapIntensity:.75}));world.add(ice);complex.ocean=ice;
 // Pressure ridges and branching fractures in the frozen sea, grounded at sea level.
 const cracks=[],k=new Kit(world);for(let n=0;n<110;n++){
  const a=n*2.39996,r=Math.sqrt((n+.5)/110)*.92,x=cx+Math.cos(a)*rx*r,y=cy+Math.sin(a)*ry*r;
  const path=[];for(let j=0;j<7;j++)path.push(seaPoint(x+j*13,y+Math.sin(n+j*1.7)*12,level+.11));cracks.push(path);
  if(n%3===0)k.add('ball',M.white,seaPoint(x,y,level+.3).toArray(),[12,1.4,4],quatAt(x,y,a),0xb5ced0);
 }new LineLayer(cracks,0x335f70);
 // Frozen river follows an explicit descending hydraulic profile, from highlands to sea.
 const points=G.river||[[500,1550,46],[50,1490,34],[-410,1250,23],[-900,1060,12],[-1450,840,1],[-2050,740,-8]],riverPos=[],riverIdx=[];
 for(let segment=1;segment<points.length;segment++){
  const a=points[segment-1],b=points[segment],dx=b[0]-a[0],dy=b[1]-a[1],L=Math.hypot(dx,dy),N=Math.ceil(L/14);
  for(let j=0;j<=N;j++){const t=j/N,x=a[0]+dx*t,y=a[1]+dy*t,h=a[2]+(b[2]-a[2])*t+.08,width=12+segment*1.5,base=riverPos.length/3;
   for(const sign of [-1,1]){const p=seaPoint(x-dy/L*width*sign,y+dx/L*width*sign,h);riverPos.push(p.x,p.y,p.z);}
   if(j<N)riverIdx.push(base,base+2,base+1,base+1,base+2,base+3);
  }
 }
 const rg=new THREE.BufferGeometry();rg.setAttribute('position',new THREE.Float32BufferAttribute(riverPos,3));rg.setIndex(riverIdx);rg.computeVertexNormals();world.add(new THREE.Mesh(rg,new THREE.MeshStandardMaterial({color:0x97c0c5,metalness:.22,roughness:.28,side:THREE.DoubleSide})));
 // Sparse, frost-encrusted columnar organisms and low tundra; no temperate grass at -50 C.
 for(let n=0;n<760;n++){
  const a=n*2.39996,r=950+((n*137)%2200),x=Math.cos(a)*r,y=Math.sin(a)*r,h=terrainH(x,y);if(h<2||h>125||x< -750&&Math.abs(y)<700)continue;
  const q=quatAt(x,y,a),base=sph(x,y),height=1.2+(n%7)*.4,tip=base.clone().add(new THREE.Vector3(0,height,0).applyQuaternion(q));
  k.pipe(M.fabric,base.toArray(),tip.toArray(),.17);for(let branch=0;branch<3;branch++){const p=base.clone().add(new THREE.Vector3(Math.sin(branch*2.1)*.6,height*.7,Math.cos(branch*2.1)*.6).applyQuaternion(q));k.pipe(M.white,tip.toArray(),p.toArray(),.08);}
  k.add('ball',M.fabric,base.toArray(),[1.8,.15,1.1],q,0x6e7969);
 }k.finish();
 buildIntake();
}
function buildIntake(){
 const c=G.cfg,[ix,iy]=c.ocean_intake_pos,[wx,wy]=c.water_plant_pos,[rx,ry]=c.reactor_pos,level=c.ocean_level_m;
 const head=localGroup(ix,iy,level-terrainH(ix,iy)+.7,0),k=new Kit(head);
 k.box(M.steel,0,1.8,0,22,.55,18);for(const x of [-9,9])for(const z of [-7,7])k.pipe(M.concrete,[x,-14,z],[x,1.5,z],.65);
 for(let x=-10;x<=10;x+=2)for(const z of [-8,8]){k.pipe(M.trim,[x,2,z],[x,3.3,z],.045);if(x<10)k.pipe(M.trim,[x,3.3,z],[x+2,3.3,z],.035);}
 for(let n=-1;n<=1;n++){k.add('cyl',M.trim,[n*5,3.5,0],[1.2,3.1,1.2]);industrialPipe(k,[[n*5,3.5,0],[n*5,-4,0]],.45,M.blue);k.box(M.dark,n*5,-3.3,0,2.2,2.2,2.2);for(let grille=0;grille<10;grille++)k.box(M.trim,n*5-1+grille*.22,-3.3,1.13,.07,2.3,.08);}
 for(const z of [-6,6]){industrialPipe(k,[[-11,-.1,z],[11,-.1,z]],.18,M.amber);for(let n=-4;n<=4;n++){const heater=new THREE.Mesh(new THREE.BoxGeometry(1.3,.12,.2),new THREE.MeshStandardMaterial({color:0xb77232,emissive:0xe25913,emissiveIntensity:.3}));heater.position.set(n*2.3,-.1,z);head.add(heater);intakeHeaters.push(heater);}}
 k.finish();const pg=new THREE.CircleGeometry(21,64);intakePool=new THREE.Mesh(pg,new THREE.MeshPhysicalMaterial({color:0x245465,metalness:.35,roughness:.15,transparent:true,opacity:.96,side:THREE.DoubleSide}));intakePool.position.copy(seaPoint(ix,iy,level+.2));intakePool.quaternion.copy(quatAt(ix,iy));intakePool.rotateX(-Math.PI/2);world.add(intakePool);
 // A piled service causeway terminates at the intake deck, not on the frozen water.
 const pierPts=subdiv([[wx-40,wy+42],[ix+18,iy+42],[ix+18,iy]],12),pierKit=new Kit(world),flow=[];
 for(let i=1;i<pierPts.length;i++){
  const a=pierPts[i-1],b=pierPts[i],levelAt=p=>Math.max(level+2.6,terrainH(p[0],p[1])+1.1),pa=seaPoint(...a,levelAt(a)),pb=seaPoint(...b,levelAt(b)),mid=pa.clone().add(pb).multiplyScalar(.5),q=new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(1,0,0),pb.clone().sub(pa).normalize());
  pierKit.add('box',M.steel,mid.toArray(),[pa.distanceTo(pb)+.1,.28,4.5],q);
  const [x,y]=b,deck=levelAt(b)-terrainH(x,y);for(const side of [-1,1])pierKit.pipe(M.concrete,sph(x,y+side*1.8,-1).toArray(),sph(x,y+side*1.8,deck).toArray(),.25);
 }
 pierKit.finish();
 const source=seaPoint(ix,iy,level+4.1),plant=sph(wx-30,wy,3.8),line=[source,...subdiv([[ix+18,iy],[ix+18,iy+35],[wx-40,wy+35],[wx-40,wy],[wx-30,wy]],12).map(([x,y])=>seaPoint(x,y,Math.max(level+4.1,terrainH(x,y)+3.8))),plant];
 const pipeKit=new Kit(world);for(let i=1;i<line.length;i++){pipeKit.pipe(M.blue,line[i-1].toArray(),line[i].toArray(),.75);if(i%3===0){const p=line[i],up=p.clone().normalize();pipeKit.pipe(M.steel,p.clone().addScaledVector(up,-4).toArray(),p.toArray(),.15);}}
 for(let i=1;i<line.length;i++){const offset=new THREE.Vector3(0,0,1.7);pipeKit.pipe(M.steel,line[i-1].clone().add(offset).toArray(),line[i].clone().add(offset).toArray(),.32);}pipeKit.finish();oceanFlow=new FlowLayer([line],0x9bdeed,.8,20,8);
 const hotPath=flat3([[rx+12,ry-120],[rx+95,ry-120],[rx+95,wy-32],[wx+15,wy-32],[wx+15,wy]],7.5),hotKit=new Kit(world);
 for(let i=1;i<hotPath.length;i++){hotKit.pipe(M.trim,hotPath[i-1].toArray(),hotPath[i].toArray(),.7);const up=hotPath[i].clone().normalize();hotKit.pipe(M.steel,hotPath[i-1].clone().addScaledVector(up,-1.7).toArray(),hotPath[i].clone().addScaledVector(up,-1.7).toArray(),.62);if(i%3===0)hotKit.pipe(M.steel,hotPath[i].clone().addScaledVector(up,-7.5).toArray(),hotPath[i].toArray(),.16);}
 hotKit.finish();thermalFlow=new FlowLayer([hotPath],0xeac47e,1,12,9);
 // Membrane filters, pressure vessels and a real delivery main into the elevated city tank.
 const plantKit=new Kit(world),plantG=localGroup(wx,wy,0,0),pk=new Kit(plantG);
 for(let n=0;n<5;n++){const xx=-21+n*10;pk.add('cyl',M.trim,[xx,27,-6],[1.7,7,1.7],[Math.PI/2,0,0]);industrialPipe(pk,[[xx,27,-9.5],[xx,27,-15],[25,27,-15],[25,5,-15]],.2,M.blue);}
 pk.finish();parkingLot(wx+8,wy+52,48,17,0,8);
 const delivery=G.utilities.plant_feed.map(utilityPoint);complex.deliveryFlow=new FlowLayer([delivery],0x8dd4eb,.75,28,10);
 addLabel('OCEAN INTAKE / HEATED ICE WELL',ix,iy,level-terrainH(ix,iy)+14,'#afd5da','mid');clickable(head,'intake','intake');
}
function updateOcean(s){
 if(!oceanFlow)return;const on=s.water.plant&&s.water.raw_m3_h>0;oceanFlow.active[0]=on;thermalFlow.active[0]=s.water.heat_kw>0;complex.deliveryFlow.active[0]=on;
 intakeHeaters.forEach(m=>m.material.emissiveIntensity=on?1.7:.05);intakePool.material.color.setHex(on?0x245465:0x88b5c3);intakePool.material.roughness=on?.15:.5;
}

function build(){
  const c=G.cfg, R=c.ring_road_radius, WR=c.wall_radius, ns=c.sectors, HR=c.hub_radius, rx=c.reactor_pos[0], ry=c.reactor_pos[1];
  // ground plate of the city, lighter than the terrain
  buildLandscape();cityPlate=cap(WR+6, 0.25, 0x827f73, 110, 256, 0.06);
  // ---- roads ----
  for(let s=0;s<ns;s++){ roadMeshes.ring.push(road(arcPts(s*60,(s+1)*60,R,30), 14, 1.0, 0x30343d));  }
  for(let s=0;s<ns;s++){ road([polar(s*60,HR-22), polar(s*60,WR+70)], 10, 1.0, 0x30343d);  }   // boundary streets through the gate and out
  road([[WR+70,0],[c.landing_pad_pos[0]-100,0]], 10, 1.0, 0x30343d);                              // east road to the landing pad
  for(const [k,v] of [['garage',c.garage],['medlab',c.medlab],['school',c.school]]){ const s=Math.floor(v[0]/60); ribbon(arcPts(s*60,v[0]+12,v[1],10), 6, 0.9, 0x3a3e48); }   // service lanes off the boundary streets
  for(let s=0;s<ns;s++) for(let k=0;k<=c.house_rows;k++){ const r=c.house_radius_min-30+k*c.house_ring_step; road(arcPts(s*60,(s+1)*60,r,40), 10, 1.0, 0x3a3e48); }
  for(let i=0;i<G.houses.x.length;i++){ const a=G.houses.angle[i], r=G.houses.radius[i]; ribbon([polar(a,r-8), polar(a,r-24)], 2.4, 1.16, 0xb8b2a4); }   // footpath from every house to its street
  road([[-WR-70,0],[rx+70,0]], 14, 1.0, 0x30343d);    // trunk road
  road([[rx+70,-40],[rx+70,c.mine_pos[1]+40]], 10, 0.9, 0x30343d);      // service road along the complex
  road([[rx+70,-40],[c.solar_pos[0]+60,c.solar_pos[1]+40]], 8, 0.9, 0x30343d);
  road([c.tower_junction,[c.tower_pos[0],c.tower_pos[1]+40]], 8, 0.9, 0x30343d);
  road([[c.waste_station_pos[0]+40,0],[c.waste_station_pos[0]+40,c.waste_station_pos[1]-20]], 8, 0.9, 0x30343d);
  // hub plaza
  {const plaza=cap(HR,.9,0x8a8d7e,26,128),v=plaza.geometry.attributes.position,uv=[];for(let i=0;i<v.count;i++)uv.push(v.getX(i)/7,v.getZ(i)/7);plaza.geometry.setAttribute('uv',new THREE.Float32BufferAttribute(uv,2));plaza.material.map=pavingTexture;}  { const steps=new THREE.Mesh(new THREE.TorusGeometry(HR+2,1.6,4,64), new THREE.MeshStandardMaterial({color:0x9a9fa8})); steps.position.copy(sph(0,0,0.2)); steps.quaternion.copy(quatAt(0,0)); steps.rotateX(Math.PI/2); world.add(steps); }
  for(let s=0;s<ns;s++) for(let k=1;k<=c.house_rows;k++){ const r=c.house_radius_min-30+k*c.house_ring_step-6; ribbon(arcPts(s*60+2.5,s*60+57.5,r,20), 1.2, -0.4, 0x6f6a62); }   // terrace edges
  // ---- wall: panels between posts, top rail, footing; gates: towers, floodlights, striped arm, booth ----
  { const segs=[]; const gap=Math.atan2(21,WR)*180/Math.PI; for(let s=0;s<ns;s++){ const a0=s*60+gap, a1=(s+1)*60-gap, n=22; for(let i=0;i<n;i++){ segs.push([a0+(a1-a0)*(i+0.5)/n, a0+(a1-a0)*i/n]); } }
    const segLen=WR*2*Math.PI*(60-2*gap)/360/22; const m4=new THREE.Matrix4();
    const panels=new THREE.InstancedMesh(new THREE.BoxGeometry(segLen+0.6, 13, 2.2), new THREE.MeshStandardMaterial({color:0x8d877b, roughness:.85}), segs.length);
    const posts=new THREE.InstancedMesh(new THREE.BoxGeometry(3.6,16,3.6), new THREE.MeshStandardMaterial({color:0x5f5a52, roughness:.8}), segs.length+ns);
    const rails=new THREE.InstancedMesh(new THREE.BoxGeometry(segLen+0.6, 0.9, 3.6), new THREE.MeshStandardMaterial({color:0x6a655c}), segs.length);
    const foot=new THREE.InstancedMesh(new THREE.BoxGeometry(segLen+0.6, 1.4, 5), new THREE.MeshStandardMaterial({color:0x4d4942}), segs.length);
    segs.forEach(([a,ap],i)=>{ const [x,y]=polar(a,WR); const q=quatAt(x,y,-a*Math.PI/180-Math.PI/2); m4.compose(sph(x,y,6.5), q, new THREE.Vector3(1,1,1)); panels.setMatrixAt(i,m4); m4.compose(sph(x,y,13.4), q, new THREE.Vector3(1,1,1)); rails.setMatrixAt(i,m4); m4.compose(sph(x,y,0.7), q, new THREE.Vector3(1,1,1)); foot.setMatrixAt(i,m4);
      const [px,py]=polar(ap,WR); m4.compose(sph(px,py,8), quatAt(px,py,-ap*Math.PI/180-Math.PI/2), new THREE.Vector3(1,1,1)); posts.setMatrixAt(i,m4); });
    for(let s=0;s<ns;s++){ const ap=(s+1)*60-gap; const [px,py]=polar(ap,WR); m4.compose(sph(px,py,8), quatAt(px,py,-ap*Math.PI/180-Math.PI/2), new THREE.Vector3(1,1,1)); posts.setMatrixAt(segs.length+s,m4); }
    for(const m of [panels,posts,rails,foot]){ m.castShadow=true; m.receiveShadow=true; world.add(m); } wallMesh=panels; wallPanels=panels; wallSegs=segs;
    for(let g=0;g<ns;g++){ const a=g*60; const [gx,gy]=polar(a,WR); const grp=localGroup(gx,gy,0,-a*Math.PI/180); const tw=new THREE.MeshStandardMaterial({color:0x7c766e, roughness:.8}); const win=new THREE.MeshBasicMaterial({color:0xffd27a});
      for(const z of [-16,16]){ const t=new THREE.Mesh(new THREE.BoxGeometry(11,28,11), tw); t.position.set(0,14,z); t.castShadow=true; grp.add(t); const w1=new THREE.Mesh(new THREE.BoxGeometry(6,3,0.6), win); w1.position.set(0,22,z+(z<0?5.6:-5.6)); grp.add(w1); const cap2=new THREE.Mesh(new THREE.BoxGeometry(13,1.2,13), new THREE.MeshStandardMaterial({color:0x4d4942})); cap2.position.set(0,28.6,z); grp.add(cap2);
        const fl=new THREE.Sprite(new THREE.SpriteMaterial({map:TEX.glow, transparent:true, depthWrite:false, blending:THREE.AdditiveBlending})); fl.scale.set(40,40,1); fl.position.set(-6,27,z*0.55); grp.add(fl); }
      const booth=new THREE.Mesh(new THREE.BoxGeometry(7,8,7), new THREE.MeshStandardMaterial({color:0x8a8478})); booth.position.set(9,4,-10); booth.castShadow=true; grp.add(booth); const bw=new THREE.Mesh(new THREE.BoxGeometry(0.4,3,5), win); bw.position.set(5.4,5,-10); grp.add(bw);
      const armG=new THREE.Group(); armG.position.set(0,7,-10); for(let k=0;k<6;k++){ const seg=new THREE.Mesh(new THREE.BoxGeometry(1.8,1.8,3.4), new THREE.MeshStandardMaterial({color:k%2?0xffffff:0xe2574d})); seg.position.set(0,0,1.7+k*3.4); armG.add(seg); } grp.add(armG);
      const lamp=new THREE.Mesh(new THREE.SphereGeometry(1.4,8,8), new THREE.MeshBasicMaterial({color:0x5ec07a})); lamp.position.set(0,10,-10); grp.add(lamp);
      const beacons=[-16,16].map(z=>{ const b=new THREE.Sprite(new THREE.SpriteMaterial({map:TEX.red, transparent:true, depthTest:false, blending:THREE.AdditiveBlending})); b.scale.set(26,26,1); b.position.set(0,31,z); b.visible=false; grp.add(b); return b; });
      clickable(grp, 'gate'+g, 'gate', g); gates.push({g:grp, arm:armG, lamp, beacons});
      addLabel(g===3?"HADLEY'S HOPE  pop. 158  Weyland-Yutani": `gate ${g+1}`, gx, gy, 40, g===3?'#f2c14e':'#c9cfdb', g===3?'mid':'near'); }
  }
  // ---- lockdown overlays: a translucent wedge over each sector, shown while it is locked ----
  lockWedges=[]; for(let s=0;s<ns;s++){ const pos=[], idx=[]; const n=24; for(let k=0;k<=n;k++){ const a=s*60+k*60/n; const p0=sph(...polar(a,HR+30),2.5), p1=sph(...polar(a,WR-6),2.5); pos.push(p0.x,p0.y,p0.z,p1.x,p1.y,p1.z); if(k<n){ const b=k*2; idx.push(b,b+1,b+2, b+1,b+3,b+2); } }
    const g=new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos,3)); g.setIndex(idx); g.computeVertexNormals(); const m=new THREE.Mesh(g, new THREE.MeshBasicMaterial({color:0xe2574d, transparent:true, opacity:0.0, depthWrite:false, side:THREE.DoubleSide})); m.visible=false; world.add(m); lockWedges.push(m); }
  buildNeighborhood(); buildStreetLife(); buildUtilities();
  const m4=new THREE.Matrix4();
  // ---- poles, arms, lamps, cables ----
  const P=G.poles.x.length;
  polesMesh=new THREE.InstancedMesh(new THREE.CylinderGeometry(.19,.27,11,10), new THREE.MeshStandardMaterial({color:0x9a9a9a}), P);
  armsMesh=new THREE.InstancedMesh(new THREE.BoxGeometry(3.5,.18,.18), new THREE.MeshStandardMaterial({color:0x777}), P);
  lampsMesh=new THREE.InstancedMesh(new THREE.SphereGeometry(.22,8,8), new THREE.MeshBasicMaterial({color:0xffe9a8}), P);
  markers.lampGlow=pointsLayer(P, TEX.glow, 0xffe08a, 3, true);
  for(let i=0;i<P;i++){ const x=G.poles.x[i], y=G.poles.y[i]; const yaw=G.poles.kind[i]===0? -G.poles.angle[i]*Math.PI/180+Math.PI/2 : -G.poles.angle[i]*Math.PI/180;
    m4.compose(sph(x,y,5.5), quatAt(x,y,yaw), new THREE.Vector3(1,1,1)); polesMesh.setMatrixAt(i,m4); m4.compose(sph(x,y,10.3), quatAt(x,y,yaw), new THREE.Vector3(1,1,1)); armsMesh.setMatrixAt(i,m4); m4.compose(sph(x,y,9), quatAt(x,y,yaw), new THREE.Vector3(1,1,1)); lampsMesh.setMatrixAt(i,m4); }
  world.add(polesMesh); world.add(armsMesh); world.add(lampsMesh);
  spanCurves=[]; const netCurves=[];
  for(let i=0;i<P;i++){ const p=G.poles.parent[i]; const b=sph(G.poles.x[i],G.poles.y[i],10.7); let a; if(p<0){ const s=G.poles.sector[i]; const [qx,qy]=polar(s*60+1.6, HR+20); a=sph(qx,qy,10.7); } else a=sph(G.poles.x[p],G.poles.y[p],10.7);
    const L=a.distanceTo(b); spanCurves.push(catenary(a,b,Math.min(1.5,L*.025))); const a2=a.clone().addScaledVector(a.clone().normalize(),-2), b2=b.clone().addScaledVector(b.clone().normalize(),-2); netCurves.push(catenary(a2,b2,Math.min(1.5,L*.025))); }
  netSpanPaths=netCurves;spanLines=new LineLayer(spanCurves, 0xf2c14e); netLines=new LineLayer(netCurves, 0x4fd1c5);detailedPower();
  // rp cabinets and internet cabinets at the start of each boundary street
  for(let s=0;s<ns;s++){ const [qx,qy]=polar(s*60+1.6, HR+20); const rp=equipmentCabinet(qx,qy,6,4,6,0x899382,-(s*60)*Math.PI/180); clickable(rp,'rp'+s,'rp',s); rpBoxes.push(rp);
    const [cx,cy]=polar(s*60+4.5, HR+20); const cab=equipmentCabinet(cx,cy,3,3.2,2.8,0x708c88,-(s*60)*Math.PI/180); clickable(cab,'cab'+s,'cabinet',s); cabBoxes.push(cab);
    const [ux,uy]=polar(s*60+8.5, HR+22); const ups=equipmentCabinet(ux,uy,12,4,8,0x708c88,-(s*60)*Math.PI/180); clickable(ups,'ups'+s,'ups',s); hub['ups'+s]=ups; addLabel(`S${s+1} distribution, UPS, cabinet`, qx, qy, 24, '#9aa3b5', 'near'); }
  buildExternalGrid();
  // Pipe rendering comes exclusively from /geometry utilities.
  waterMainPts=[]; waterSectorPts=[];
  // ---- hub: substation with transformers and a fenced yard, ups, comms, ops, pump station and tank ----
  { const yard=localGroup(0,-70,0,0); const fence=new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(70,6,44)), new THREE.LineBasicMaterial({color:0x9aa3b5})); fence.position.y=3; yard.add(fence);
    for(let i=0;i<3;i++){ const tr=new THREE.Mesh(new THREE.BoxGeometry(12,10,9), new THREE.MeshStandardMaterial({color:0x6a6d78})); tr.position.set(-22+i*22,5,0); yard.add(tr); for(let j=0;j<3;j++){ const b=new THREE.Mesh(new THREE.CylinderGeometry(0.6,0.6,6,6), new THREE.MeshStandardMaterial({color:0xdddddd})); b.position.set(-22+i*22-3+j*3,13,0); yard.add(b); } }
    const bus=new THREE.Mesh(new THREE.BoxGeometry(60,0.6,0.6), new THREE.MeshStandardMaterial({color:0xf2c14e})); bus.position.set(0,16.5,0); yard.add(bus); hub.yard=yard; clickable(yard,'substation','substation'); addLabel('substation 6 kV', 0, -70, 26, '#f2c14e', 'near', true).userData.role='sub';
    hub.ups=clickable(facility('UPS / BATTERY HALL',-88,36,26,12,20,{type:'power',color:0x829087}),'upsc','upsc'); addLabel('UPS center', -88, 10, 24, '#4fd1c5', 'near', true).userData.role='ups';
    hub.comms=clickable(facility('NETWORK / DATA CENTRE',88,34,26,16,22,{type:'network',color:0x7d9293}),'comms','comms'); addLabel('network / data centre',88,34,28,'#4fd1c5','near',true).userData.role='comms';
    hub.ops=clickable(facility('COLONY OPERATIONS',0,80,36,16,24,{color:0x93988b}),'ops','ops'); addLabel('operations center', 0, 80, 26, '#c9cfdb', 'near');
    hub.pump=clickable(facility('PUMP / PRESSURE CONTROL',-40,-40,18,9,14,{type:'power',color:0x7b9694}),'pump','pump'); buildWaterTower(); addLabel('pump station', -40, -40, 20, '#5aa9ff', 'near', true).userData.role='pump'; addLabel('water tank', -70, -45, 38, '#5aa9ff', 'near', true).userData.role='tank';

    // water level inside the tank
 }
  // ---- reactor complex ----
  complex.contain=clickable(cyl(rx,ry,46,50,0x555a66),'reactor','reactor'); complex.dome=new THREE.Mesh(new THREE.SphereGeometry(46,32,16,0,Math.PI*2,0,Math.PI/2), new THREE.MeshStandardMaterial({color:0x6a6f7a, roughness:.6})); complex.dome.position.copy(sph(rx,ry,50)); complex.dome.quaternion.copy(quatAt(rx,ry)); world.add(complex.dome); clickable(complex.dome,'reactor','reactor');
  complex.turbine=clickable(box(rx+10,ry+80,70,22,34,0x5c6070,0x9aa3b5),'reactor','reactor'); addLabel('turbine hall', rx+10, ry+80, 34, '#9aa3b5','near');
  complex.tw1=cyl(rx-90,ry-60,22,90,0x8a8f9a); complex.tw2=cyl(rx-90,ry+60,22,90,0x8a8f9a); complex.steam=pointsLayer(24, TEX.steam, 0xffffff, 60, false); clickable(complex.tw1,'reactor','reactor'); clickable(complex.tw2,'reactor','reactor');
  complex.core=new THREE.Mesh(new THREE.SphereGeometry(8,12,12), new THREE.MeshBasicMaterial({color:0x5ec07a})); complex.core.position.copy(sph(rx,ry,98)); world.add(complex.core);
  { const sw=localGroup(rx+50,-60,0,0); for(let i=0;i<2;i++){ const tr=new THREE.Mesh(new THREE.BoxGeometry(12,10,9), new THREE.MeshStandardMaterial({color:0x6a6d78})); tr.position.set(i*18,5,0); sw.add(tr); } const fence=new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(44,6,30)), new THREE.LineBasicMaterial({color:0x9aa3b5})); fence.position.set(9,3,0); sw.add(fence); addLabel('switchyard', rx+50, -60, 20, '#f2c14e','near'); }
  addLabel('REACTOR, atmosphere processor', rx, ry, 120, '#5ec07a', 'mid', true).userData.role='reactor';
  complex.panels=[]; for(let i=0;i<8;i++) for(let j=0;j<5;j++){ const px=c.solar_pos[0]-60+i*17, py=c.solar_pos[1]-40+j*20; const p=new THREE.Mesh(new THREE.BoxGeometry(14,0.8,10), new THREE.MeshStandardMaterial({color:0x1c2f5a, roughness:.3, metalness:.4, emissive:0x102040, emissiveIntensity:0.2})); p.position.copy(sph(px,py,4)); p.quaternion.copy(quatAt(px,py)); p.rotateX(-0.5); world.add(p); complex.panels.push(p); clickable(p,'solar','solar'); }
  addLabel('solar field', c.solar_pos[0], c.solar_pos[1], 26, '#e0b04a', 'mid', true).userData.role='solar';
  complex.water=clickable(facility('OCEAN WATER / MELT · FILTER · DESALINATE',c.water_plant_pos[0],c.water_plant_pos[1],60,24,40,{type:'power',color:0x809698}),'wplant','wplant');complex.waterTank=clickable(cyl(c.water_plant_pos[0]+52,c.water_plant_pos[1]-10,14,30,0x879ba0),'wplant','wplant');addLabel('ocean water treatment',...c.water_plant_pos,38,'#5aa9ff','mid',true).userData.role='wplant';
  complex.rad=clickable(facility('SHIELDED WASTE / TRANSFER',c.radwaste_pos[0],c.radwaste_pos[1],70,12,50,{type:'workshop',color:0x989276}),'rad','rad'); { const s=new THREE.Sprite(new THREE.SpriteMaterial({map:TEX.rad, transparent:true})); s.scale.set(16,16,1); s.position.copy(sph(c.radwaste_pos[0],c.radwaste_pos[1],20)); world.add(s); const f=localGroup(c.radwaste_pos[0],c.radwaste_pos[1],0,0); const fence=new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(100,5,80)), new THREE.LineBasicMaterial({color:0xe8d34a})); fence.position.y=2.5; f.add(fence); } addLabel('radioactive waste storage', c.radwaste_pos[0], c.radwaste_pos[1], 30, '#e8d34a', 'mid');
  complex.mine=clickable(facility('MINING / ORE PROCESSING',c.mine_pos[0],c.mine_pos[1],60,20,44,{type:'workshop',color:0x8d8978}),'mine','mine'); { const hf=localGroup(c.mine_pos[0]+50,c.mine_pos[1],0,0); const legs=new THREE.Mesh(new THREE.BoxGeometry(3,60,3), new THREE.MeshStandardMaterial({color:0x8a7a5a})); legs.position.set(-8,30,0); hf.add(legs); const legs2=legs.clone(); legs2.position.set(8,30,0); hf.add(legs2); const wheel=new THREE.Mesh(new THREE.TorusGeometry(8,1.2,8,24), new THREE.MeshStandardMaterial({color:0xaaaaaa})); wheel.position.set(0,62,0); hf.add(wheel); complex.wheel=wheel; } addLabel('mine', c.mine_pos[0], c.mine_pos[1], 34, '#a08a2a', 'mid', true).userData.role='mine';
  complex.waste=clickable(facility('RESOURCE RECOVERY',c.waste_station_pos[0],c.waste_station_pos[1],40,14,30,{type:'workshop',color:0x879078}),'wproc','wproc'); addLabel('waste processing', c.waste_station_pos[0], c.waste_station_pos[1], 24, '#9bd36a', 'near', true).userData.role='wproc';
  // ---- radio tower: converging lattice mast with an omni antenna and a beacon; next to it a deep-space dish on a pedestal ----
  { const tx=c.tower_pos[0], ty=c.tower_pos[1]; const g=localGroup(tx,ty,0,0); const H=130; const legMat=new THREE.MeshStandardMaterial({color:0xc44a3a}); const whiteMat=new THREE.MeshStandardMaterial({color:0xe8e8e8});
    const wAt=l=>10-8.5*(l/12); const brace=[];
    for(let l=0;l<12;l++){ const y0=l*H/12, y1=(l+1)*H/12, w0=wAt(l), w1=wAt(l+1); for(let k=0;k<4;k++){ const a1=k*Math.PI/2+Math.PI/4, a2=(k+1)*Math.PI/2+Math.PI/4;
        const p0=new THREE.Vector3(Math.cos(a1)*w0/2,y0,Math.sin(a1)*w0/2), p1=new THREE.Vector3(Math.cos(a1)*w1/2,y1,Math.sin(a1)*w1/2); const seg=new THREE.Mesh(new THREE.CylinderGeometry(0.45,0.5,p0.distanceTo(p1),6), l%2?whiteMat:legMat); seg.position.copy(p0).lerp(p1,0.5); seg.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0), p1.clone().sub(p0).normalize()); g.add(seg);
        brace.push(Math.cos(a1)*w0/2,y0,Math.sin(a1)*w0/2, Math.cos(a2)*w0/2,y0,Math.sin(a2)*w0/2); brace.push(Math.cos(a1)*w0/2,y0,Math.sin(a1)*w0/2, Math.cos(a2)*w1/2,y1,Math.sin(a2)*w1/2); } }
    const bg=new THREE.BufferGeometry(); bg.setAttribute('position', new THREE.Float32BufferAttribute(brace,3)); g.add(new THREE.LineSegments(bg, new THREE.LineBasicMaterial({color:0xd8d8d8})));
    for(let k=0;k<3;k++){ const a=k*2.094+0.5; const wire=new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0,H*0.7,0), new THREE.Vector3(Math.cos(a)*70,0,Math.sin(a)*70)]); g.add(new THREE.Line(wire, new THREE.LineBasicMaterial({color:0x888888}))); const anchor=new THREE.Mesh(new THREE.BoxGeometry(3,2,3), new THREE.MeshStandardMaterial({color:0x666})); anchor.position.set(Math.cos(a)*70,1,Math.sin(a)*70); g.add(anchor); }
    const omni=new THREE.Mesh(new THREE.CylinderGeometry(0.4,0.4,16,6), whiteMat); omni.position.set(0,H+8,0); g.add(omni);
    complex.towerLight=new THREE.Sprite(new THREE.SpriteMaterial({map:TEX.red, transparent:true, depthTest:false})); complex.towerLight.scale.set(14,14,1); complex.towerLight.position.set(0,H+17,0); g.add(complex.towerLight);
    complex.rings=[]; for(let k=0;k<3;k++){ const r=new THREE.Mesh(new THREE.TorusGeometry(8+k*7,0.5,6,32), new THREE.MeshBasicMaterial({color:0x4fd1c5, transparent:true, opacity:0.5})); r.position.set(0,H+8,0); r.rotation.x=Math.PI/2; g.add(r); complex.rings.push(r); }
    clickable(g,'tower','tower'); complex.towerGroup=g; addLabel('CELLULAR / 5G COLONY COVERAGE', tx, ty, H+28, '#4fd1c5', 'mid');
    const ant=new Kit(g);for(let level=0;level<2;level++)for(let n=0;n<3;n++){const a=n*Math.PI*2/3,xx=Math.cos(a)*3,zz=Math.sin(a)*3;ant.box(M.white,xx,H-7-level*6,zz,.75,3.8,.3,[0,-a,0]);ant.pipe(M.dark,[xx,H-9-level*6,zz],[xx,0,zz],.055);}ant.finish();
    secureCompound(tx,ty,158,158);facility('CELLULAR / 5G BASEBAND',tx+30,ty+28,18,8,12,{type:'network'});road([[tx,ty+40],[tx+79,ty+40],[tx+79,ty],[tx+72,ty]],10,1.04,0x454b4d);
  }
  buildSpaceDish();
  // ---- flows, markers, rovers, sector labels ----
  flowPower=new FlowLayer([...spanCurves, ...feederCurves, ...trunkCurves, ...towerCurves, ...solarCurves], 0xfff2b0, 2, 3, 30);
  flowWater=new FlowLayer([], 0x9ad0ff, 7, 4, 30);
  packetsPts=pointsLayer(80, TEX.dot, 0x4fd1c5, 2, false); markers.packetsRed=pointsLayer(20, TEX.dot, 0xe2574d, 9, false);
  markers.issues=pointsLayer(60, TEX.bang, 0xffffff, 22, false); markers.nonet=pointsLayer(300, TEX.nonet, 0xffffff, 12, false); markers.heater=pointsLayer(300, TEX.flame, 0xffffff, 8, false);
  markers.people=pointsLayer(80, TEX.person, 0xffffff, 9, false); markers.xenos=pointsLayer(20, TEX.diamond, 0xffffff, 20, false); markers.marines=pointsLayer(8, TEX.marine, 0xffffff, 11, false); markers.ups=pointsLayer(8, TEX.bolt, 0xffffff, 20, false);
  const rc={garbage:[0x9bd36a,'garbage rover'], sludge:[0xb48ead,'sludge hauler'], engineer:[0xf2c14e,'engineering crew 1'], 'engineer-2':[0xf2c14e,'engineering crew 2'], plumber:[0x5aa9ff,'plumber']};
  for(const [name,[col,l]] of Object.entries(rc)){ const g=detailedVehicle(col,name);
    const lab=textSprite(l,'#fff',22); lab.position.y=5; lab.scale.multiplyScalar(0.22); g.add(lab); world.add(g); clickable(g,'rover:'+name,'rover',name); rovers[name]={g,lab,from:null,to:null,q:null,t0:0}; }
  for(let s=0;s<ns;s++){ const [x,y]=polar(s*60+30,R+70); addLabel(`Sector ${s+1}`,x,y,8,'#9aa3b5','mid'); }
  // ---- inner ring props: vehicle bay, med lab, school, containers, greenhouses, tanks ----
  { const [ga,gr]=c.garage; const [gx,gy]=polar(ga,gr); complex.garage=clickable(facility('VEHICLE SERVICE / DEPOT',gx,gy,44,14,30,{type:'workshop',yaw:-ga*Math.PI/180,color:0x929582}),'garage','garage'); addLabel('vehicle bay', gx, gy, 24, '#f2c14e','near');
    const [ma,mr]=c.medlab; const [mx,my]=polar(ma,mr); clickable(facility('MEDICAL / RESEARCH',mx,my,36,12,26,{yaw:-ma*Math.PI/180,color:0x929c90}),'medlab','medlab'); addLabel('med lab', mx, my, 22, '#e2574d','near');
    const [sa,sr]=c.school; const [sx,sy]=polar(sa,sr); clickable(facility('SCHOOL / COMMUNITY',sx,sy,40,10,26,{yaw:-sa*Math.PI/180,color:0x9c9b84}),'school','school'); addLabel('school', sx, sy, 20, '#5aa9ff','near');
    buildCargoDepot();
    for(let k=0;k<3;k++){ const a=246+k*10; const [x,y]=polar(a,205); const dome=new THREE.Mesh(new THREE.SphereGeometry(11,20,10,0,Math.PI*2,0,Math.PI/2), new THREE.MeshPhysicalMaterial({color:0x9ad0ff, transparent:true, opacity:.35, roughness:.1, metalness:0})); dome.position.copy(sph(x,y,0.8)); dome.quaternion.copy(quatAt(x,y)); world.add(dome); } addLabel('hydroponics', ...polar(256,205), 18, '#9bd36a','near');
    for(let k=0;k<4;k++){ const a=8+k*9; const [x,y]=polar(a,205); const tk=cyl(x,y,6,16,0xb8bcc4); tk.castShadow=true; } addLabel('oxygen and fuel tanks', ...polar(22,205), 24, '#c9cfdb','near');
    for(let k=0;k<2;k++){ const [x,y]=polar(ga-4+k*5, gr-18); const v=detailedVehicle(k?0x829379:0x738c96,'parked-'+k);v.position.copy(sph(x,y,1.08));v.quaternion.copy(quatAt(x,y,-ga*Math.PI/180));world.add(v); } }
  // ---- landing pad east of the city ----
  { const [lx,ly]=c.landing_pad_pos; cap(90,0.9,0x4a4f5a,6,48,0,lx,ly); const ring=new THREE.Mesh(new THREE.TorusGeometry(88,1.2,6,64), new THREE.MeshBasicMaterial({color:0xf2c14e})); ring.position.copy(sph(lx,ly,1.6)); ring.quaternion.copy(quatAt(lx,ly)); ring.rotateX(Math.PI/2); world.add(ring);
    complex.padLights=pointsLayer(12, TEX.glow, 0xffb060, 30, true); setPoints(complex.padLights, Array.from({length:12},(_,k)=>{ const [px,py]=polar(k*30,86); return [lx+px, ly+py]; }), 2);
    const beacon=cyl(lx+95,ly-95,1.5,50,0xc9cfdb); complex.beacon=new THREE.Sprite(new THREE.SpriteMaterial({map:TEX.red, transparent:true, depthTest:false})); complex.beacon.scale.set(16,16,1); complex.beacon.position.copy(sph(lx+95,ly-95,52)); world.add(complex.beacon);
    clickable(cap(90,1.0,0x4a4f5a,6,48,0,lx,ly),'pad','pad'); addLabel('landing field', lx, ly, 30, '#f2c14e','mid'); }
  // ---- rocks and drifts outside the wall ----
  { const rocks=new THREE.InstancedMesh(new THREE.DodecahedronGeometry(1,0), new THREE.MeshStandardMaterial({color:0x5a544c, roughness:1}), 500); let seed=7; const rnd=()=>{ seed=(seed*16807)%2147483647; return seed/2147483647; };
    for(let i=0;i<500;i++){ const a=rnd()*360, r=WR+40+rnd()*900; const [x,y]=polar(a,r); if(Math.abs(y)<40 && x<-WR) { continue; } const s=2+rnd()*9; m4.compose(sph(x,y,s*0.4), quatAt(x,y,rnd()*6.3), new THREE.Vector3(s,s*0.6,s)); rocks.setMatrixAt(i,m4); } rocks.instanceMatrix.needsUpdate=true; rocks.castShadow=true; world.add(rocks);
    const drifts=new THREE.InstancedMesh(new THREE.SphereGeometry(1,10,6), new THREE.MeshStandardMaterial({color:0xdde3ec, roughness:1}), 80); for(let i=0;i<80;i++){ const a=rnd()*360, r=WR+8+rnd()*30; const [x,y]=polar(a,r); const s=6+rnd()*14; m4.compose(sph(x,y,0.5), quatAt(x,y,-a*Math.PI/180), new THREE.Vector3(s,2.2,s*0.5)); drifts.setMatrixAt(i,m4); } drifts.instanceMatrix.needsUpdate=true; world.add(drifts); }
  // ---- xenomorphs: a pool of articulated figures; marines: a squad of four ----
  const xenoMat=new THREE.MeshStandardMaterial({color:0x101216, roughness:.35, metalness:.6});
  for(let k=0;k<12;k++){ const g=new THREE.Group(); const body=new THREE.Mesh(new THREE.CapsuleGeometry(2.2,7,4,8), xenoMat); body.rotation.x=Math.PI/2; body.position.y=4; g.add(body);
    const head=new THREE.Mesh(new THREE.CapsuleGeometry(1.4,6,4,8), xenoMat); head.rotation.x=Math.PI/2; head.position.set(0,6,5.5); g.add(head);
    const tail=new THREE.Mesh(new THREE.ConeGeometry(0.9,12,6), xenoMat); tail.rotation.x=-Math.PI/2-0.3; tail.position.set(0,4.5,-9); g.add(tail);
    for(const [sx,sz] of [[-2.4,2],[2.4,2],[-2.4,-2],[2.4,-2]]){ const leg=new THREE.Mesh(new THREE.CylinderGeometry(0.4,0.3,5,5), xenoMat); leg.position.set(sx,2.2,sz); leg.rotation.z=sx>0?-0.5:0.5; g.add(leg); }
    for(const sx of [-1.5,1.5]){ const arm=new THREE.Mesh(new THREE.CylinderGeometry(0.35,0.3,5,5), xenoMat); arm.position.set(sx,5,4); arm.rotation.z=sx>0?-0.9:0.9; arm.rotation.x=-0.6; g.add(arm); }
    const lab=textSprite('xenomorph','#e2574d',22); lab.position.y=14; lab.scale.multiplyScalar(0.5); g.add(lab); g.visible=false; world.add(g); clickable(g,'xeno:'+k,'xeno',k); xenoPool.push({g,lab,from:null,to:null,q:null,t0:0,id:null}); }
  squadGroup=new THREE.Group(); const mMat=new THREE.MeshStandardMaterial({color:0x5a6a3a, roughness:.8}); for(let k=0;k<4;k++){ const m=new THREE.Group(); const body=new THREE.Mesh(new THREE.CapsuleGeometry(1.2,3,4,8), mMat); body.position.y=3.6; m.add(body); const helm=new THREE.Mesh(new THREE.SphereGeometry(1.3,8,8), new THREE.MeshStandardMaterial({color:0x3a4a2a})); helm.position.y=6.6; m.add(helm); const rifle=new THREE.Mesh(new THREE.BoxGeometry(0.6,0.6,4), new THREE.MeshStandardMaterial({color:0x222})); rifle.position.set(1.4,4,1); m.add(rifle); m.position.set((k%2)*5-2.5, 0, Math.floor(k/2)*5-2.5); squadGroup.add(m); }
  { const lab=textSprite('marine squad','#8be05a',22); lab.position.y=12; lab.scale.multiplyScalar(0.5); squadGroup.add(lab); squadGroup.userData.lab=lab; } squadGroup.visible=false; world.add(squadGroup); clickable(squadGroup,'squad','squad');
  markers.ctrl=(()=>{ const n=300; const g=new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(n*3).fill(-99999),3)); g.setAttribute('color', new THREE.Float32BufferAttribute(new Float32Array(n*3),3)); const m=new THREE.Points(g, new THREE.PointsMaterial({map:TEX.dot, vertexColors:true, size:9, transparent:true, depthWrite:false, sizeAttenuation:true})); m.frustumCulled=false; world.add(m); return m; })();
  industrialDetails();buildCampus();reactorIndustry();buildOcean();streetSignals();applyLayers();
}
function applyLayers(){ M.roof.opacity=layers.cutaway?.62:.84;updateMapKey();if(!markers.issues) return;spanLines.mesh.visible=true;netLines.mesh.visible=true;for(const key of ["feederLayer","trunkLayer","towerLayer","solarLayer"])if(hub[key])hub[key].mesh.visible=true;if(hub.cableTowerLayer)hub.cableTowerLayer.mesh.visible=true;utilityGroup.visible=!!layers.underground;if(utilityDrops)utilityDrops.visible=layers.water;for(const v of houseDetails.values())v.roof.visible=true; markers.issues.visible=layers.issues; markers.nonet.visible=layers.nonet; markers.ups.visible=layers.ups; markers.heater.visible=layers.heater; flowPower.mesh.visible=layers.power;if(phaseDropFlow)phaseDropFlow.mesh.visible=layers.power; flowWater.mesh.visible=layers.water; packetsPts.visible=layers.packets; markers.packetsRed.visible=layers.packets; markers.people.visible=layers.people; markers.xenos.visible=layers.threats; markers.marines.visible=layers.threats; labelGroup.visible=layers.labels; if(markers.ctrl) markers.ctrl.visible=layers.ctrl; renderer.shadowMap.enabled=layers.shadows; sun.castShadow=layers.shadows; }

// ---------- per state update ----------
const tmpC=new THREE.Color();
function tempColor(t){ const u=Math.max(0,Math.min(1,(t+40)/65)); if(u<0.6){ const k=u/0.6; return tmpC.setRGB((60+150*k)/255,(110+120*k)/255,(230-20*k)/255); } const k=(u-0.6)/0.4; return tmpC.setRGB((210+45*k)/255,(230-90*k)/255,(210-150*k)/255); }
const packetsSeen=new Map();
function onState(s, first){
  if(!G) return; if(!housesMesh) build();
  const now=performance.now();updatePhysicalState(s);updateCargo(s);updateOcean(s);
  const c=G.cfg, ns=c.sectors, hs=s.houses, P=G.poles.x.length, m4=new THREE.Matrix4();
  for(let i=0;i<flatHouses.length;i++){ const col=new THREE.Color([0x898674,0x999786,0x7e8c85,0xb0a48a][G.houses.type[i]]);if(!hs.power[i])col.multiplyScalar(.65);housesMesh.setColorAt(i,col); }
  housesMesh.instanceColor.needsUpdate=true;
  { const pal=['#f2c14e','#5ec07a','#5aa9ff','#b48ead','#e2574d','#4fd1c5']; const names=[...new Set(s.control.programs.filter(Boolean))]; const a=markers.ctrl.geometry.attributes.position, cc=markers.ctrl.geometry.attributes.color; const counts={};
    for(let i=0;i<300;i++){ const p=s.control.programs[i]; if(p&&s.control.ext[i]){ const pt=sph(flatHouses[i][0],flatHouses[i][1],HSIZE_H(G.houses.type[i])+6); a.setXYZ(i,pt.x,pt.y,pt.z); const col=new THREE.Color(pal[names.indexOf(p)%pal.length]); cc.setXYZ(i,col.r,col.g,col.b); counts[p]=(counts[p]||0)+1; } else a.setXYZ(i,0,-99999,0); } a.needsUpdate=true; cc.needsUpdate=true;
    const mq=s.control.mqtt; document.getElementById('ctrl').innerHTML = mq.enabled ? `bus ${mq.connected?'<span class="ok">connected</span>':'<span class="bad">disconnected</span>'} ${mq.broker}, ${mq.controlled}/300 houses under external programs, ${mq.sent} sensor msgs, ${mq.received} actuator msgs<br>`+names.map((n,k)=>`<span style="color:${pal[k%pal.length]}">&#9679;</span> ${n} ${counts[n]||0}`).join(' &nbsp; ') : 'bus off: every house runs the built-in thermostat (start with --mqtt host:port and houses_runtime.py)'; }
  for(let i=0;i<P;i++){ spanLines.setColor(i, s.poles.span[i]?0xf2c14e:0x5a2a2a); netLines.setColor(i, s.poles.net[i]?0x4fd1c5:0x5a2a2a); flowPower.active[i]=!!s.poles.span[i]; }
  for(let i=0;i<ns;i++){ hub.feederLayer.setColor(i, s.power.feeder[i]&&s.sectors[i].online?0xf2c14e:0x5a2a2a); flowPower.active[P+i]=s.power.feeder[i]&&s.sectors[i].online; }
  const reactorUp=s.reactor.available_mw>0; const nT=trunkCurves.length, nTw=towerCurves.length;
  for(let i=0;i<nT;i++){ hub.trunkLayer.setColor(i, s.power.trunk?0xf2c14e:0x5a2a2a); flowPower.active[P+ns+i]=s.power.trunk&&reactorUp; }
  for(let i=0;i<nTw;i++){ hub.towerLayer.setColor(i, s.power.tower_line?0xf2c14e:0x5a2a2a); flowPower.active[P+ns+nT+i]=s.power.tower_line&&s.power.trunk&&reactorUp; }
  hub.solarLayer.setColor(0, s.power.solar_kw>0?0xf2c14e:0x6a5a3a); flowPower.active[P+ns+nT+nTw]=s.power.solar_kw>0;
  for(let i=0;i<cableTowerCurves.length;i++) hub.cableTowerLayer.setColor(i, s.net.uplink?0x4fd1c5:0x5a2a2a);
  const waterOn=s.water.tank_m3>0&&s.water.pump;
  // lamps and poles
  setPoints(markers.lampGlow, G.poles.x.map((x,i)=>s.poles.lamp[i]?[x,G.poles.y[i]]:null).filter(Boolean), 9);
  for(let i=0;i<P;i++){ const st=s.poles.state[i]; if(st===prevPole[i]) continue; prevPole[i]=st; const x=G.poles.x[i], y=G.poles.y[i]; const yaw=G.poles.kind[i]===0? -G.poles.angle[i]*Math.PI/180+Math.PI/2 : -G.poles.angle[i]*Math.PI/180; const q=quatAt(x,y,yaw); if(st===2) q.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1,0,0),1.45)); else if(st===1) q.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1,0,0),0.3));
    m4.compose(sph(x,y,st===2?1:5.5), q, new THREE.Vector3(1,1,1)); polesMesh.setMatrixAt(i,m4); m4.compose(sph(x,y,st===2?1:10.3), q, new THREE.Vector3(st===2?0.01:1,1,1)); armsMesh.setMatrixAt(i,m4); lampsMesh.setMatrixAt(i,m4); polesMesh.instanceMatrix.needsUpdate=true; armsMesh.instanceMatrix.needsUpdate=true; lampsMesh.instanceMatrix.needsUpdate=true; }
  lampsMesh.material.color.setHex(s.env.night||s.env.storm?0xffe9a8:0x777777);
  // markers
  setPoints(markers.issues, s.issues.map(i=>[i.x,i.y]), 34);
  setPoints(markers.nonet, flatHouses.filter((p,i)=>!hs.net[i]), 18);
  setPoints(markers.heater, flatHouses.filter((p,i)=>hs.heater[i]&&hs.power[i]), 15);
  setPoints(markers.people, s.people, 3);
  setPoints(markers.marines, s.marines, 6);
  setPoints(markers.ups, s.sectors.map((x,i)=>x.ups==='DISCHARGING'||x.ups==='CHARGING'?polar(i*60+8.5,c.hub_radius+22):null).filter(Boolean).concat(s.power.ups_center==='DISCHARGING'||s.power.ups_center==='CHARGING'?[[-88,10]]:[]), 30);
  // lockdown: wedge overlay, gate beacons, alert list
  const locked=s.sectors.map(x=>x.lockdown>0); for(let i=0;i<ns;i++){ lockWedges[i].visible=locked[i]; } for(let i=0;i<ns;i++){ const on=locked[i]||locked[(i+ns-1)%ns]; gates[i].beacons.forEach(b=>b.visible=on); }
  { const alerts=[]; s.sectors.forEach((x,i)=>{ if(x.lockdown>0) alerts.push(`LOCKDOWN sector ${i+1}: ${x.lockdown} min left`); }); if(s.xenos.length) alerts.push(`${s.xenos.length} xenomorphs on the ground (${[...new Set(s.xenos.map(x=>x.state))].join(', ')})`); if(s.squad.state!=='BASE') alerts.push(`marine squad ${s.squad.state.toLowerCase()} in sector ${s.squad.sector}`); if(s.wall_breach.some(a=>a!==null)) alerts.push('wall breached in sector '+s.wall_breach.map((a,i)=>a!==null?i+1:null).filter(Boolean).join(', ')); if(s.reactor.mode!=='ONLINE') alerts.push('reactor '+s.reactor.mode); document.getElementById('alerts').innerHTML=alerts.map(a=>`<div>${a}</div>`).join(''); document.getElementById('alerts').style.display=alerts.length?'block':'none'; }
  // wall breach: the broken panel lies flat
  if(wallPanels){ for(let i=0;i<wallSegs.length;i++){ const [a]=wallSegs[i]; const sec=Math.floor(a/60); const br=s.wall_breach[sec]; const broken=br!==null&&Math.abs(a-br)<1.3; if(broken!==wallSegs[i].broken){ wallSegs[i].broken=broken; const [x,y]=polar(a,c.wall_radius+(broken?6:0)); const q=quatAt(x,y,-a*Math.PI/180-Math.PI/2); if(broken) q.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1,0,0),1.45)); m4.compose(sph(x,y,broken?1.5:6.5), q, new THREE.Vector3(1,1,1)); wallPanels.setMatrixAt(i,m4); wallPanels.instanceMatrix.needsUpdate=true; } } }
  // xenomorphs and the squad
  { const seen=new Set(); s.xenos.forEach((x,k)=>{ if(k>=xenoPool.length) return; const p=xenoPool[k]; const to=sph(x.x,x.y,0.5); if(p.id!==x.id||!p.to){ p.g.position.copy(to); p.from=to; } else p.from=p.to; p.to=to; p.q=quatAt(x.x,x.y,-x.heading+Math.PI/2); p.t0=now; p.id=x.id; p.g.visible=layers.threats; p.state=x.state; retext(p.lab, `xenomorph: ${x.state}${x.state==='hunt'||x.state==='attack'?' house '+x.target:''}`, x.state==='dying'?'#888':'#e2574d'); seen.add(k); });
    xenoPool.forEach((p,k)=>{ if(!seen.has(k)){ p.g.visible=false; p.id=null; p.to=null; } });
    const q=s.squad; const vis=q.state!=='BASE'; squadGroup.visible=vis&&layers.threats; if(vis){ const to=sph(q.x,q.y,0.5); if(!squadGroup.userData.to) squadGroup.position.copy(to); squadGroup.userData.from=squadGroup.userData.to||to; squadGroup.userData.to=to; squadGroup.userData.q=quatAt(q.x,q.y,-q.heading+Math.PI/2); squadGroup.userData.t0=now; retext(squadGroup.userData.lab, `marine squad: ${q.state.toLowerCase()}`, '#8be05a'); } else squadGroup.userData.to=null; }
  // gates: arm rotates with gate_open
  for(let i=0;i<ns;i++){ const st=s.sectors[i].gate, g=gates[i]; g.armTarget=-Math.PI/2*s.sectors[i].gate_open; const col=st==='LOCKDOWN'?0xe2574d:(st==='OPEN'?0x5ec07a:0x8a93a6); g.lamp.material.color.setHex(col); }
  // hub and complex live state
  hub.yard.children[0].material.color.setHex(s.power.substation?0x9aa3b5:0xe2574d);
  hub.tankLevel.scale.set(1, Math.max(0.05, 6.12*s.water.tank_m3/s.water.tank_cap), 1); hub.tankLevel.position.copy(sph(-70,-45, 24+3.06*s.water.tank_m3/s.water.tank_cap));
  for(let i=0;i<ns;i++){ cabBoxes[i].material.color.setHex(s.sectors[i].cabinet?0x3f6a6a:0x6a3030); rpBoxes[i].material.color.setHex(s.sectors[i].rp_ok?0x6a6d78:0x6a3030); }
  const mc={ONLINE:0x5ec07a,RUNBACK:0xe0b04a,STARTING:0x5aa9ff}[s.reactor.mode]||0xe2574d; complex.core.material.color.setHex(mc);
  const sol=Math.min(1, s.power.solar_kw/60); complex.panels.forEach(p=>{ p.material.emissiveIntensity=0.1+sol*1.2; p.material.emissive.setHex(0x2a5aff); });
  complex.water.material.color.setHex(s.water.plant?0x2a4a6a:0x4a2a2a); complex.towerLight.material.color.setHex(s.net.mobile?0xff3b3b:0x553030); complex.rings.forEach(r=>r.visible=!!s.net.mobile);
  complex.mine.material.color.setHex(s.power.mine?0x4a3a2a:0x2a2a2a); complex.steamOn=s.reactor.mode==='ONLINE'||s.reactor.mode==='RUNBACK';
  for(let i=0;i<ns;i++){ const it=s.sectors[i].road; roadMeshes.ring[i].material.color.setHex(it<20?0x8a3a3a:(it<50?0x5a4a3a:0x30343d)); }
  // live labels
  for(const l of liveLabels){ const r=l.userData.role; if(r==='sub') retext(l, `substation ${s.power.available_kw} kW available, ${s.power.demand_kw} kW load${s.power.shedding?', shedding L'+s.power.shedding:''}`, s.power.substation?'#f2c14e':'#e2574d');
    else if(r==='ups') retext(l, `UPS center ${s.power.ups_center_kwh} kWh ${s.power.ups_center.toLowerCase()}`, '#4fd1c5'); else if(r==='comms') retext(l, `comms node ${s.net.houses_online}/300 online, ${s.net.packets_per_min} pkt/min, uplink ${s.net.uplink?'OK':'LOST'}`, s.net.uplink?'#4fd1c5':'#e2574d');
    else if(r==='pump') retext(l, `pump station ${s.water.flow_m3_h} m3/h to the city`, s.water.pump?'#5aa9ff':'#e2574d'); else if(r==='tank') retext(l, `water tank ${s.water.tank_m3} / ${s.water.tank_cap} m3`, s.water.tank_m3>100?'#5aa9ff':'#e2574d');
    else if(r==='reactor') retext(l, `REACTOR ${s.reactor.mode}: ${s.reactor.power_mw} MW el, ${s.reactor.thermal_mw} MW th, core ${s.reactor.core_temp} C`, {ONLINE:'#5ec07a',RUNBACK:'#e0b04a',STARTING:'#5aa9ff'}[s.reactor.mode]||'#e2574d');
    else if(r==='solar') retext(l, `solar field ${s.power.solar_kw} kW`, '#e0b04a'); else if(r==='wplant') retext(l, `water plant ${s.water.plant?s.water.plant_m3_h+' m3/h':'no heat'}`, s.water.plant?'#5aa9ff':'#e2574d');
    else if(r==='mine') retext(l, `mine ${s.power.infra.mine} kW${s.power.mine_frac<1?' (curtailed)':''}`, s.power.mine?'#a08a2a':'#777'); else if(r==='wproc') retext(l, `waste processing, ${s.finance.waste_station} loads received`, '#9bd36a');
    else if(r==='tower') retext(l, `space uplink ${s.net.uplink?'OK':'LOST'}, ${s.net.packets_per_min} pkt/min`, s.net.uplink?'#4fd1c5':'#e2574d'); }
  // rovers: interpolate between the last two samples
  for(const r of s.rovers){ if(!rovers[r.name]){const g=r.name.startsWith('freight')?freightVehicle():detailedVehicle([0x74918b,0xaaa38b,0x93664f,0x6e818c][Number(r.name.split('-').at(-1))%4],r.name);const lab=textSprite(r.name,'#ddd',22);lab.position.y=4;lab.scale.multiplyScalar(.18);g.add(lab);world.add(g);clickable(g,'rover:'+r.name,'rover',r.name);rovers[r.name]={g,lab,t0:0};} const rv=rovers[r.name];if(rv.g.userData.cargo)rv.g.userData.cargo.visible=!!r.load; const lane=r.state==='IDLE'?8.5:2.2,xx=r.x-Math.sin(r.heading)*lane,yy=r.y+Math.cos(r.heading)*lane;rv.from=rv.g.position.clone();rv.to=sph(xx,yy,1.08);rv.q=quatAt(xx,yy,-r.heading);const grade=Math.atan2(terrainH(r.x+Math.cos(r.heading)*3,r.y+Math.sin(r.heading)*3)-terrainH(r.x-Math.cos(r.heading)*3,r.y-Math.sin(r.heading)*3),6);rv.q.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,0,1),grade));rv.distanceFrom=rv.distance??r.distance_m;rv.distanceTo=r.distance_m; rv.t0=now; rv.state=r.state; if(first||!rv.initialized){rv.g.position.copy(rv.to);rv.g.quaternion.copy(rv.q);rv.initialized=true;}rv.lab.visible=!r.name.startsWith('transit')&&camera.position.distanceTo(rv.g.position)<140; retext(rv.lab, `${r.name} ${r.state.toLowerCase().replace(/_/g,' ')}`, '#fff'); }
  for(const p of s.net.packets){ const key=p.t+':'+p.from+':'+p.id; if(!packetsSeen.has(key)) packetsSeen.set(key,{t0:now,p}); }
  const e=s.env; document.getElementById('banner').innerHTML=`<b>${s.time}</b> &nbsp; ${e.t_out} C, wind ${e.wind} m/s${e.storm?' <span class="bad">STORM</span>':''}${e.precip==='snow'?' snow':''}${e.night?' night':' day'}${s.paused?' <span class="warn">PAUSED</span>':''} &nbsp; ${s.speed} min/s`;
  const fin=document.getElementById('finished'); if(s.finished){ fin.style.display='flex'; fin.textContent='COLONY LOST: '+s.finish_reason+'. A new colony is founded in two minutes.'; } else fin.style.display='none';
  const m=s.time.match(/(\d\d):(\d\d)$/); clock.hour=m?(+m[1]+(+m[2])/60):12; clock.speed=s.paused?0:s.speed; clock.at=now; clock.daylight=e.daylight; weather.wind=e.wind; weather.precip=e.precip; weather.storm=e.storm; weather.tornadoOn=e.storm&&e.wind>30;
  planetMat.uniforms.uCold.value=Math.min(1,Math.max(0,(-e.t_out-30)/35)); planetMat.uniforms.uStorm.value=e.storm?1:(e.precip==='snow'?0.4:0);
  if(first){ const focus=Number(new URLSearchParams(location.search).get('house'));if(Number.isInteger(focus)&&focus>=1&&focus<=G.houses.x.length){selected={kind:'house',id:focus-1};flyTo(G.houses.x[focus-1],G.houses.y[focus-1],42);renderInfo();}speedEl.value=speedToSlider(s.speed); speedV.textContent=s.speed+' min/s'; }
}
const prevPole=new Array(1000).fill(-1);
const HSIZE_H=t=>DIM[t][1]+2;
const clock={hour:12, speed:20, at:0, night:false, daylight:0.1}; const sunDir=new THREE.Vector3(1,0.3,0);

// ---------- packets ----------
function packetPath(pk){ const c=G.cfg, HR=c.hub_radius, WR=c.wall_radius; const path=[];
  if(pk.from==='house'){ let i=pk.id, p=G.houses.pole[i]; path.push(...(houseNetDrops[i]||[]).slice().reverse());let guard=0;while(p>=0&&guard++<40){path.push(...netSpanPaths[p].slice().reverse());p=G.poles.parent[p];} const s=G.houses.sector[i]; const [cx,cy]=polar(s*60+4.5,HR+20); path.push(sph(cx,cy,10)); path.push(sph(88,34,18)); }
  else path.push(sph(88,34,18));
  if(pk.kind==='reactor'||pk.kind==='lost'){ path.push(sph(-HR+10,8,21)); path.push(sph(-WR-40,8,25)); path.push(sph(c.reactor_pos[0]+70,8,25)); path.push(sph(c.reactor_pos[0],c.reactor_pos[1],30)); }
  else if(pk.uplink){path.push(...spaceFiberPath);path.push(sph(c.dish_pos[0]+44,c.dish_pos[1],12));}

  return path; }
function updatePackets(){ const now=performance.now(); const good=[], bad=[]; for(const [key,v] of packetsSeen){ const u=(now-v.t0)/2200; if(u>=1){ packetsSeen.delete(key); continue; } if(!v.path){const pts=packetPath(v.p),cum=[0];for(let i=1;i<pts.length;i++)cum.push(cum[i-1]+pts[i].distanceTo(pts[i-1]));v.path={pts,cum,len:cum.at(-1)};}const q=sample(v.path,u); (v.p.uplink||v.p.kind==='reactor'?good:bad).push(q); }
  const put=(layer,arr)=>{ const a=layer.geometry.attributes.position; for(let i=0;i<a.count;i++){ if(i<arr.length) a.setXYZ(i,arr[i].x,arr[i].y,arr[i].z); else a.setXYZ(i,0,-99999,0);} a.needsUpdate=true; }; put(packetsPts, good); put(markers.packetsRed, bad); }

// ---------- camera, picking, info panel ----------
let flyAnim=null;
function flyTo(x,y,dist){ const p=sph(x,y), n=p.clone().normalize(); const side=new THREE.Vector3().crossVectors(n, new THREE.Vector3(0,0,1)).normalize(); if(side.lengthSq()<1e-6) side.set(1,0,0); const back=new THREE.Vector3().crossVectors(side,n).normalize(); const pos=p.clone().add(n.multiplyScalar(dist*0.85)).add(back.multiplyScalar(dist*0.55)); flyAnim={from:camera.position.clone(), to:pos, tfrom:controls.target.clone(), tto:p, t0:performance.now()}; }
document.querySelectorAll('#fly button').forEach(b=>b.onclick=()=>{ const c=G.cfg; const f=b.dataset.f; if(f==='home'){const i=selected?.kind==='house'?selected.id:0;selected={kind:'house',id:i};flyTo(G.houses.x[i],G.houses.y[i],42);renderInfo();} else if(f==='street') flyTo(...polar(17,270),90); else if(f==='hub') flyTo(0,0,420); else if(f==='gate') flyTo(-c.wall_radius,0,300); else if(f==='reactor') flyTo(c.reactor_pos[0],c.reactor_pos[1],420); else if(f==='solar') flyTo(c.solar_pos[0],c.solar_pos[1],320); else if(f==='dish') flyTo(...c.dish_pos,210);else if(f==='intake') flyTo(...c.ocean_intake_pos,240);else if(f==='cargo')flyTo(...polar(...c.cargo_depot),140);else if(f==='tower') flyTo(c.tower_pos[0],c.tower_pos[1],320); else if(f==='mine') flyTo(c.mine_pos[0],c.mine_pos[1],320); else if(f==='city') flyTo(0,0,1500); else flyAnim={from:camera.position.clone(), to:new THREE.Vector3(1200,RP+4200,3800), tfrom:controls.target.clone(), tto:new THREE.Vector3(0,RP,0), t0:performance.now()}; });
const ray=new THREE.Raycaster(); const mouse=new THREE.Vector2(); ray.params.Points.threshold=8; 
let downAt=null;
renderer.domElement.addEventListener('pointerdown', ev=>{ downAt=[ev.clientX,ev.clientY]; });
renderer.domElement.addEventListener('pointerup', ev=>{ if(!downAt) return; const moved=Math.hypot(ev.clientX-downAt[0], ev.clientY-downAt[1]); downAt=null; if(moved>4) return; pick(ev, true); });
renderer.domElement.addEventListener('dblclick',ev=>{pick(ev,true);if(selected)focusSelection();else{setMouse(ev);ray.setFromCamera(mouse,camera);const hit=ray.intersectObject(planetMesh,false)[0];if(hit)focusPoint(hit.point,Math.min(150,camera.position.distanceTo(hit.point)*.5));}});
let lastHover=0;renderer.domElement.addEventListener('mousemove', ev=>{const now=performance.now();if(downAt||now-lastHover<200)return;lastHover=now;pick(ev,false);});
function setMouse(ev){ const r=renderer.domElement.getBoundingClientRect(); mouse.set(((ev.clientX-r.left)/r.width)*2-1, -((ev.clientY-r.top)/r.height)*2+1); return [ev.clientX-r.left, ev.clientY-r.top]; }
let selected=null;
function pick(ev,click){
 const [mx,my]=setMouse(ev),tip=document.getElementById('tip');if(!housesMesh||!S)return;ray.setFromCamera(mouse,camera);const candidates=[];
 const add=(hits,decode)=>{if(hits.length){const item=decode(hits[0]);if(item)candidates.push({...item,hit:hits[0]});}};
 add(ray.intersectObjects([polePickMesh,...cabinetMeters].filter(Boolean),false),h=>({kind:'pole',id:h.object===polePickMesh?h.instanceId:h.object.userData.pole}));
 add(ray.intersectObjects([...houseDetails.values()].map(v=>v.g),true),h=>({kind:'house',id:h.object.userData.house}));
 add(ray.intersectObject(housesMesh,false),h=>({kind:'house',id:h.instanceId}));
 add(ray.intersectObjects(clickables,true),h=>h.object.userData.click||h.object.parent?.userData.click);
 if(click||document.querySelector('[data-view="water"]').getAttribute('aria-pressed')==='true'){
  const meshes=potableBatches.filter(m=>m.material===MAT['pipe-steel']);if(layers.underground)meshes.push(...utilityBatches);
  add(ray.intersectObjects(meshes,false),h=>{const tag=h.object.userData.tags[h.instanceId];return tag&&tag.id>=0?{kind:'pipe',id:tag.id,extra:tag.system}:null;});
 }
 candidates.sort((a,b)=>a.hit.distance-b.hit.distance);const result=candidates[0];if(!result){tip.style.display='none';return;}
 if(click){selected={kind:result.kind,id:result.id,extra:result.extra};renderInfo();}
 const html=result.kind==='house'?houseInfo(result.id,true):result.kind==='pole'?`<b>POLE ${String(result.id+1).padStart(3,'0')} · L1 / L2 / L3 / N</b><br>${((poleLoads[result.id]||0)/1000).toFixed(1)} kW · ${S.poles.span[result.id]?'energized':'isolated'}<br>F / double-click: inspect meter`:`<b>${result.kind} ${result.id}</b><br>F / double-click: focus`;
 tipHtml(tip,mx,my,html);
}
function tipHtml(tip,mx,my,html){ tip.innerHTML=html; tip.style.display='block'; tip.style.left=(mx+14)+'px'; tip.style.top=(my+14)+'px'; }
function houseInfo(i, short){ const h=S.houses, ctl=S.control; const prog=ctl.ext[i]?`${ctl.programs[i]}: ${ctl.reasons[i]} (target ${ctl.targets[i]} C)`:`built-in thermostat, target ${ctl.targets[i]} C`; return `<b>House ${i+1}</b> (Sector ${G.houses.sector[i]+1}, ${G.types[G.houses.type[i]]}, ${G.houses.residents[i]} residents)<br>indoor ${h.t[i]} C, heater ${h.heater[i]?'on':'off'}, draw ${h.draw[i]} W${h.limit[i]?' (limit '+h.limit[i]+' W)':''}<br>power ${h.power[i]?(h.ups[i]?'sector UPS':'grid'):'<span class="bad">none</span>'}, water ${h.water[i]?'ok':'<span class="bad">no</span>'}${h.burst[i]?', <span class="bad">pipes burst</span>':''}<br>pressure ${S.hydraulics.pressure_kpa[i]} kPa · delivered ${S.hydraulics.delivered_l[i]} L/tick · leak ${S.hydraulics.leak_l[i]} L/tick<br>internet ${h.net[i]?'online':'<span class="warn">offline</span>'}, aeration sludge ${Math.round(h.sludge[i]*100)}%<br><span class="dim">program:</span> ${prog}`+(short?'':`<br>pole ${G.houses.pole[i]}`); }
function personInfo(per){ const st=['at home','walking to the hub','at the hub','walking home'][per[2]]; return `<b>Colonist</b> from house ${per[3]+1}, ${st}`; }
function rows(pairs){ return '<table>'+pairs.map(([k,v])=>`<tr><td class="dim">${k}</td><td><b>${v}</b></td></tr>`).join('')+'</table>'; }
function renderInfo(){ const box=document.getElementById('info'); if(!selected||!S){ box.style.display='none'; return; } const s=S, c=G.cfg; let title='', body='';
  const k=selected.kind, x=selected.extra;
  if(k==='house'){ title=`House ${selected.id+1}`; body=houseInfo(selected.id,false)+`<div style="margin-top:6px"><a href="/house?id=${selected.id+1}" target="_blank" style="color:#5aa9ff">open the house page: gauges, history, log</a></div>`; }
  else if(k==='pole'){title=`Pole ${Number(selected.id)+1} · distribution board`;body=rows([['circuit','L1 / L2 / L3 + neutral'],['load',((poleLoads[selected.id]||0)/1000).toFixed(2)+' kW'],['grid',s.poles.span[selected.id]?'energized':'isolated'],['fibre',s.poles.net[selected.id]?'online':'offline'],['inspect','F / double-click to focus the meter']]);}
  else if(k==='pipe'){const e=x==='water'?G.utilities.links[selected.id]:G.utilities.drainage.find(d=>d.name===x)?.links[selected.id];title=`${x} / pipe ${selected.id+1}`;if(e){body=rows([['material',e.material],['internal diameter',Math.round(e.diameter_m*1000)+' mm'],['length',e.length_m.toFixed(2)+' m'],...(x==='water'?[['flow',s.hydraulics.flow_l_s[selected.id]+' L/s'],['velocity',s.hydraulics.velocity_m_s[selected.id]+' m/s'],['head loss',s.hydraulics.headloss_m[selected.id]+' m'],['insulation',e.insulation_mm+' mm / heat traced']]:[['inflow',(s.hydraulics.drainage_l_s[x==='sanitary'?0:1][selected.id])+' L/s'],['grade',(e.slope*100).toFixed(1)+' %'],['full-bore capacity',(e.capacity_m3_s*1000).toFixed(2)+' L/s']])]);}}
  else if(k==='person'){ const per=s.people[selected.id]; title='Colonist'; body=per?personInfo(per):'went home'; }
  else if(k==='substation'){ title='Main substation'; body=rows([['available',s.power.available_kw+' kW'],['load',s.power.demand_kw+' kW'],['deficit',s.power.deficit_kw+' kW'],['shedding level',s.power.shedding],['trunk line',s.power.trunk?'ok':'CUT'],['feeders online',s.power.feeder.filter(Boolean).length+'/6'],['solar in',s.power.solar_kw+' kW'],['mine',s.power.infra.mine+' kW'],['road heating',s.power.infra.road_heating+' kW'],['lamps',s.power.infra.lamps+' kW'],['ups charging',s.power.infra.ups_charge+' kW']]); }
  else if(k==='upsc'){ title='UPS center'; body=rows([['state',s.power.ups_center],['charge',s.power.ups_center_kwh+' / 800 kWh'],['feeds','ops center, comms node, pump station']]); }
  else if(k==='ups'){ const sec=s.sectors[x]; title=`Sector ${x+1} UPS`; body=rows([['state',sec.ups],['charge',sec.ups_kwh+' / 400 kWh'],['sector load',sec.demand_kw+' kW'],['houses on power',sec.power_ok+'/50']]); }
  else if(k==='rp'){ const sec=s.sectors[x]; title=`Sector ${x+1} distribution point`; body=rows([['feeder',sec.feeder_ok?'ok':'BROKEN'],['distribution point',sec.rp_ok?'ok':'DAMAGED'],['sector fed',sec.online?'yes':'no (shed or cut)'],['load',sec.demand_kw+' kW'],['lamps on',sec.lamps_on]]); }
  else if(k==='cabinet'){ const sec=s.sectors[x]; title=`Sector ${x+1} internet cabinet`; body=rows([['online',sec.cabinet?'yes':'no'],['cabinet ups',sec.cabinet_ups_h+' h'],['houses online',sec.net_ok+'/50']]); }
  else if(k==='comms'){ title='Comms node'; body=rows([['houses online',s.net.houses_online+'/300'],['traffic',s.net.packets_per_min+' packets/min'],['uplink',s.net.uplink?'OK':'LOST'],['reactor link',s.net.reactor_link?'ok':'lost'],['tower line power',s.power.tower_line?'ok':'cut']]); }
  else if(k==='ops'){ title='Operations center'; body=rows([['time',s.time],['open issues',s.issues_total],['colony budget',s.finance.colony+' cr'],['month income',s.finance.month_income+' cr'],['month expense',s.finance.month_expense+' cr']]); }
  else if(k==='pump'||k==='tank'){ title=k==='pump'?'Pump station':'Water tank'; body=rows([['tank',s.water.tank_m3+' / '+s.water.tank_cap+' m3'],['hydraulic solve',s.hydraulics.converged?'converged':'residual '+s.hydraulics.residual_m.toFixed(3)+' m'],['sewage held',s.hydraulics.sewer_storage_m3+' m3'],['storm water held',s.hydraulics.storm_storage_m3+' m3'],['overflow total',s.hydraulics.overflow_m3+' m3'],['flow to houses',s.water.flow_m3_h+' m3/h'],['from the plant',s.water.plant_m3_h+' m3/h'],['pump power',s.water.pump?'ok':'NONE'],['houses with water',s.water.houses_ok+'/300'],['frozen / burst',s.water.frozen+' / '+s.water.burst]].concat(s.water.sector_m3_h.map((v,i)=>['sector '+(i+1), v+' m3/h']))); }
  else if(k==='reactor'){ const r=s.reactor; title='Reactor, atmosphere processor'; body=rows([['mode',r.mode],['electric',r.power_mw+' MW (setpoint '+r.setpoint_mw+')'],['thermal',r.thermal_mw+' MW'],['to grid',r.available_mw+' MW'],['core',r.core_temp+' C'],['coolant',r.coolant_temp+' C, flow '+Math.round(r.flow*100)+'%'],['decay heat',r.decay_mw+' MW'],['pumps A / B',r.pump_a+' / '+r.pump_b],['heat exchanger',r.hx],['pump batteries',r.battery_h+' h'],['control link',r.link?'ok':'LOST'],['faults',r.faults.join(', ')||'none'],['marines',r.marines?'in the sublevels':'no']]); }
  else if(k==='solar'){ title='Solar field'; body=rows([['output',s.power.solar_kw+' kW'],['daylight',Math.round(s.env.daylight/0.3*100)+'% of a clear day'],['dust',Math.round(s.env.dust*100)+'%']]); }
  else if(k==='wplant'||k==='intake'){ title=k==='intake'?'Ocean intake / heated well':'Ocean water treatment'; body=rows([['source','frozen saline ocean'],['state',s.water.plant?'melting / filtering / desalinating':'stopped'],['raw intake',s.water.raw_m3_h+' m³/h'],['treated water',s.water.plant_m3_h+' m³/h'],['brine return',s.water.brine_m3_h+' m³/h'],['heat used / available',s.water.heat_kw+' / '+s.water.heat_available_kw+' kW'],['recovery','85%'],['tank in the city',s.water.tank_m3+' m³']]); }
  else if(k==='rad'){ title='Radioactive waste storage'; body=rows([['load',s.power.infra.waste_storage+' kW'],['state','sealed'],['upkeep','3000 cr/month, colony']]); }
  else if(k==='mine'){ title='Mine'; body=rows([['load',s.power.infra.mine+' kW'],['state',s.power.mine?(s.power.mine_frac<1?'curtailed to '+Math.round(s.power.mine_frac*100)+'%':'working'):'stopped'],['income','3 cr/min to the colony while powered']]); }
  else if(k==='wproc'){ title='Waste processing'; body=rows([['loads received',s.finance.waste_station],['sector bins',s.sectors.map(x=>Math.round(x.waste*100)+'%').join(' ')]]); }
  else if(k==='tower'){title='Cellular / 5G base station';body=rows([['role','local mobile communications'],['coverage',s.net.mobile?'online':'offline'],['line power',s.power.tower_line?'ok':'cut']]);}
  else if(k==='dish'){title='Deep-space tracking complex';body=rows([['reflector','64 m / parabolic'],['role','Weyland-Yutani space uplink'],['uplink',s.net.uplink?'OK':'LOST'],['traffic',s.net.packets_per_min+' packets/min']]);}
  else if(k==='garage'){ title='Vehicle bay'; body=rows(s.rovers.map(r=>[r.name, r.state.toLowerCase().replace(/_/g,' ')+(r.job?' ('+r.job+')':'')])); }
  else if(k==='medlab'){ title='Med lab'; body=rows([['load','part of ops center'],['cold houses',s.sectors.reduce((a,x)=>a+(x.min_t<10?1:0),0)+' sectors with houses below 10 C']]); }
  else if(k==='school'){ title='School'; body=rows([['residents walking now',s.people.length],['storm',s.env.storm?'closed':'open']]); }
  else if(k==='pad'){ title='Landing field'; body=rows([['next dropship','end of month'],['uplink',s.net.uplink?'OK':'LOST']]); }
  else if(k==='xeno'){ const x=s.xenos[selected.extra]; title='Xenomorph'; body=x?rows([['state',x.state],['sector',x.sector],['target house',x.target>0?x.target:'none']]):'gone'; }
  else if(k==='squad'){ const q=s.squad; title='Marine squad'; body=rows([['state',q.state.toLowerCase()],['sector',q.sector>0?q.sector:'base'],['position',q.x+', '+q.y]]); }
  else if(k==='gate'){ const sec=s.sectors[x]; title=`Gate ${x+1}`; body=rows([['state',sec.gate],['open',Math.round(sec.gate_open*100)+'%'],['hardware',sec.gate_ok?'ok':'DAMAGED'],['lockdown left',sec.lockdown?sec.lockdown+' min':'none']]); }
  else if(k==='rover'){ const r=s.rovers.find(r=>r.name===x); title=x; body=r?rows([['state',r.state.toLowerCase().replace(/_/g,' ')],['load',Math.round(r.load*100)+'%'],['job',r.job||'none'],['fuel',r.fuel_l+' L'],['distance',(r.distance_m/1000).toFixed(2)+' km'],['position',r.x+', '+r.y]]):''; }
  document.getElementById('infotitle').textContent=title; document.getElementById('infobody').innerHTML=body; box.style.display='block'; }
document.getElementById('infoclose').onclick=()=>{ selected=null; renderInfo(); };
window.addEventListener('keydown', e=>{ if(e.key==='Escape'){ selected=null; renderInfo(); } });

// ---------- render loop ----------
function resize(){ const w=mapEl.clientWidth, h=mapEl.clientHeight; renderer.setSize(w,h,false); composer.setSize(w,h); renderer.domElement.style.width=w+'px'; renderer.domElement.style.height=h+'px'; camera.aspect=w/h; camera.updateProjectionMatrix(); }
window.addEventListener('resize', resize); resize();
let t0=performance.now();
function frame(){ const now=performance.now(); const t=(now-t0)/1000;
  if(flyAnim){ const u=Math.min(1,(now-flyAnim.t0)/1200); const k=u*u*(3-2*u); camera.position.lerpVectors(flyAnim.from, flyAnim.to, k); controls.target.lerpVectors(flyAnim.tfrom, flyAnim.tto, k); if(u>=1) flyAnim=null; }
  updateCameraMotion(now);controls.update(); updateDetail(); updateUtilityFlow(t);
  { const hour=(clock.hour + clock.speed*(now-clock.at)/1000/60)%24; const a=(hour-6)/24*Math.PI*2; sunDir.set(Math.cos(a)*12000, 3200, Math.sin(a)*12000).normalize(); sun.position.copy(sunDir).multiplyScalar(12000); sunSprite.position.copy(sunDir).multiplyScalar(48000);
    const dl=Math.max(0, Math.sin(Math.PI*(hour-6)/12))*(weather.storm?0.2:1); sun.intensity=0.8+1.6*dl; sun.color.setHSL(0.08, 0.6, 0.55+0.25*dl); planetMat.uniforms.uSun.value.copy(sun.position).normalize(); planetMat.uniforms.uTime.value=t;
    const wantFog = weather.storm ? 0.00055 : (weather.precip==='snow' ? 0.00018 : 0.0); scene.fog.density += (wantFog-scene.fog.density)*0.05; scene.fog.color.setHex(weather.storm?0x3a3e48:0x2a2e38);
    const snowOn = weather.precip==='snow' || weather.storm; const mat=weather.snow.material; const dist=camera.position.distanceTo(controls.target); const near=1-Math.min(1,Math.max(0,(dist-700)/1400)); mat.opacity += ((snowOn?(weather.storm?0.85:0.55)*near:0)-mat.opacity)*0.05; mat.size=3+3*near;
    if(mat.opacity>0.02){ const p=weather.snow.geometry.attributes.position; const c=controls.target; const n=c.clone().normalize(); const side=new THREE.Vector3().crossVectors(n,new THREE.Vector3(0,0,1)).normalize(); const fwd=new THREE.Vector3().crossVectors(side,n); const w=weather.wind*(weather.storm?0.9:0.3); const dt=1/60;
      for(let i=0;i<p.count;i++){ let x=p.getX(i), y=p.getY(i), z=p.getZ(i); y-=(weather.storm?60:25)*dt*4; x+=w*dt*4; z+=Math.sin(t*3+i)*0.5; if(y<0){ y=500; x=(Math.random()-0.5)*1600; z=(Math.random()-0.5)*1600; } if(x>800) x=-800; p.setXYZ(i,x,y,z); }
      p.needsUpdate=true; weather.snow.position.copy(c); weather.snow.quaternion.copy(new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0,1,0), n)); }
    if(weather.tornadoOn){ const tor=weather.tornado; tor.visible=true; tor.material.opacity+= (0.35-tor.material.opacity)*0.02; const ang=t*0.05; const [tx,ty]=[Math.cos(ang)*1100+300, Math.sin(ang)*900]; tor.position.copy(sph(tx,ty,130)); tor.quaternion.copy(quatAt(tx,ty)); tor.rotateY(t*6); } else if(weather.tornado.visible){ const tor=weather.tornado; tor.material.opacity*=0.97; if(tor.material.opacity<0.01) tor.visible=false; } }
  if(housesMesh){ flowPower.update(t);if(phaseDropFlow)phaseDropFlow.update(t); flowWater.update(t);if(oceanFlow){oceanFlow.update(t);thermalFlow.update(t);complex.deliveryFlow.update(t);} updatePackets();
    for(const g of gates){ if(g.armTarget!==undefined) g.arm.rotation.x+=(g.armTarget-g.arm.rotation.x)*0.15; g.beacons.forEach((b,i)=>{ b.material.opacity=0.3+0.7*Math.max(0,Math.sin(t*8+i*Math.PI)); }); }
    for(const w of lockWedges){ if(w.visible) w.material.opacity=0.10+0.08*Math.sin(t*3); }
    for(const p of xenoPool){ if(p.to){ const u=Math.min(1,(now-p.t0)/Math.max(200,pollGap)); p.g.position.lerpVectors(p.from,p.to,u); p.g.quaternion.slerp(p.q,0.2); const moving=p.state==='hunt'||p.state==='approach'||p.state==='retreat'; p.g.children[0].position.y=4+(moving?Math.abs(Math.sin(t*14))*1.2:0); if(p.state==='attack') p.g.children[1].position.z=5.5+Math.sin(t*20)*1.5; if(p.state==='dying') p.g.rotation.z=Math.min(1.4,p.g.rotation.z+0.1); else p.g.rotation.z=0; } }
    if(squadGroup.userData.to){ const d=squadGroup.userData; const u=Math.min(1,(now-d.t0)/Math.max(200,pollGap)); squadGroup.position.lerpVectors(d.from,d.to,u); squadGroup.quaternion.slerp(d.q,0.2); }
    for(const rv of Object.values(rovers)){ if(rv.to){ const u=Math.min(1,(now-rv.t0)/Math.max(200,pollGap)); rv.g.position.lerpVectors(rv.from, rv.to, u); rv.g.quaternion.slerp(rv.q, 0.2);rv.distance=rv.distanceFrom+(rv.distanceTo-rv.distanceFrom)*u;for(const wheel of rv.g.userData.wheels||[])wheel.rotation.z=-rv.distance/.66; } }
    const d=camera.position.distanceTo(controls.target); lod.near.forEach(s=>s.visible=layers.labels&&d<900); lod.mid.forEach(s=>s.visible=layers.labels&&d<5000);
    complex.rings.forEach((r,k)=>{ const u=((t*0.8)+k/3)%1; r.scale.setScalar(0.5+u*1.5); r.material.opacity=0.6*(1-u); });
    complex.towerLight.material.opacity=0.5+0.5*Math.sin(t*4); if(complex.wheel) complex.wheel.rotation.z+= (S&&S.power.mine)?0.05:0;
    if(complex.steamOn!==undefined){ const c=G.cfg; const pts=[]; for(let k=0;k<12;k++){ const u=((t*0.25)+k/12)%1; for(const [tx,ty] of [[c.reactor_pos[0]-90,c.reactor_pos[1]-60],[c.reactor_pos[0]-90,c.reactor_pos[1]+60]]) pts.push(sph(tx+Math.sin(k*3+t)*6*u, ty+Math.cos(k*2)*6*u, 95+u*60)); } const a=complex.steam.geometry.attributes.position; for(let i=0;i<a.count;i++){ if(complex.steamOn&&i<pts.length) a.setXYZ(i,pts[i].x,pts[i].y,pts[i].z); else a.setXYZ(i,0,-99999,0);} a.needsUpdate=true; } }
  if(housesMesh){ for(const m of pipeMats){ if(m.userData.rate>0) m.userData.tex.offset.x-=m.userData.rate*0.02; } if(complex.beacon) complex.beacon.material.opacity=0.4+0.6*Math.abs(Math.sin(t*2)); }
  sunTarget.position.copy(controls.target); const sd=camera.position.distanceTo(controls.target); const desiredNear=Math.max(.1,Math.min(20,sd*.002));if(Math.abs(camera.near-desiredNear)>.01){camera.near=desiredNear;camera.updateProjectionMatrix();}const ext=Math.min(2600, Math.max(90, sd*1.2)); sun.shadow.camera.left=-ext; sun.shadow.camera.right=ext; sun.shadow.camera.top=ext; sun.shadow.camera.bottom=-ext; sun.shadow.camera.updateProjectionMatrix(); sun.position.copy(controls.target).add(sunDir.clone().multiplyScalar(8000));
  if(layers.bloom) composer.render(); else renderer.render(scene,camera); requestAnimationFrame(frame); }

// ---------- side panel ----------
function cls(ok, warn){ return ok?'ok':(warn?'warn':'bad'); }
function renderSide(s){ if(G)sectorCards(s);
  document.getElementById('time').textContent=s.time; document.getElementById('pause').textContent=s.paused?'Resume':'Pause';
  if(document.activeElement!==speedEl){ speedEl.value=speedToSlider(s.speed); speedV.textContent=s.speed+' min/s'; }
  const p=s.power, r=s.reactor, w=s.water, f=s.finance;
  const kp=[
    ['Colony budget', f.colony.toLocaleString()+' cr', f.colony>20000?'ok':(f.colony>0?'warn':'bad')],
    ['Sector budgets', f.sectors.map(x=>Math.round(x/1000)+'k').join(' '), Math.min(...f.sectors)>2000?'ok':'warn'],
    ['Power available', p.available_kw+' kW', p.available_kw>p.demand_kw?'ok':'bad'],
    ['Power demand', p.demand_kw+' kW'+(p.shedding?` / shedding L${p.shedding}`:''), p.shedding?'warn':'ok'],
    ['Water tank', w.tank_m3+' m3, '+w.houses_ok+'/300 houses', w.tank_m3>100&&w.houses_ok>280?'ok':'warn'],
    ['Pipes', `${w.frozen} frozen, ${w.burst} burst`, w.burst===0?'ok':'bad'],
    ['Internet', `${s.net.houses_online}/300 online, uplink ${s.net.uplink?'OK':'LOST'}`, s.net.uplink&&s.net.houses_online>280?'ok':'warn'],
    ['Open issues', s.issues_total+(f.unpaid?` (unpaid ${f.unpaid} cr)`:''), s.issues_total<5?'ok':'warn'],
    ['Month income (colony)', f.month_income.toLocaleString()+' cr', 'dim'],
    ['Month expense (colony)', f.month_expense.toLocaleString()+' cr', 'dim'],
  ];
  document.getElementById('kpi').innerHTML=kp.map(([l,v,c])=>`<div class="card"><div class="v ${c}">${v}</div><div class="l">${l}</div></div>`).join('');
  const inf=p.infra;
  document.getElementById('reactor').innerHTML=`<div><b class="${r.mode==='ONLINE'?'ok':(r.mode==='RUNBACK'||r.mode==='STARTING'?'warn':'bad')}">${r.mode}</b> &nbsp; ${r.power_mw} MW el (setpoint ${r.setpoint_mw}), ${r.thermal_mw} MW th, ${r.available_mw} MW to grid, core ${r.core_temp} C, coolant ${r.coolant_temp} C${r.decay_mw?`, decay ${r.decay_mw} MW`:''}${r.marines?' <span class="bad">marines in the sublevels</span>':''}</div>
    <div class="dim">pumps A ${r.pump_a} B ${r.pump_b}, flow ${Math.round(r.flow*100)} %, heat exchanger ${r.hx}, batteries ${r.battery_h} h, link ${r.link?'ok':'<span class="bad">lost</span>'}${r.faults.length?', faults: '+r.faults.join(', '):''}</div>
    <div class="dim">solar ${p.solar_kw} kW (${Math.round(s.env.daylight*100/0.3)} % of a clear day); loads: mine ${inf.mine}, houses ${Math.round(p.demand_kw-Object.values(inf).reduce((a,b)=>a+b,0))}, water plant ${inf.water_plant}, radioactive waste storage ${inf.waste_storage}, road heating ${inf.road_heating}, lamps ${inf.lamps}, comms ${inf.comms}, ups charge ${inf.ups_charge} kW</div>
    <div class="dim">trunk ${p.trunk?'ok':'<span class="bad">CUT</span>'}, substation ${p.substation?'ok':'<span class="bad">DOWN</span>'}, UPS center ${p.ups_center} ${p.ups_center_kwh} kWh, water plant ${w.plant_m3_h} m3/h, city draws ${w.flow_m3_h} m3/h</div>`;
  document.querySelector('#sectors tbody').innerHTML=s.sectors.map((x,i)=>`<tr class="sec" data-s="${i}"><td>${x.id}${x.dark?' <span class="warn">dark</span>':''}</td><td>${x.budget}</td><td>${x.demand_kw}</td><td class="${x.avg_t>15?'ok':(x.avg_t>4?'warn':'bad')}">${x.avg_t}</td><td class="${x.min_t>4?'ok':'bad'}">${x.min_t}</td><td class="${cls(x.power_ok===50,x.power_ok>30)}">${x.power_ok}</td><td class="${cls(x.water_ok===50,x.water_ok>30)}">${x.water_ok}</td><td class="${cls(x.net_ok===50,x.net_ok>30)}">${x.net_ok}</td><td class="${x.ups==='DISCHARGING'?'warn':(x.ups==='DEPLETED'?'bad':'dim')}">${x.ups.slice(0,4)} ${x.ups_kwh}</td><td class="${x.waste>=1?'bad':(x.waste>=0.9?'warn':'dim')}">${Math.round(x.waste*100)}%</td><td class="${x.sanitary>70?'ok':'bad'}">${x.sanitary}</td><td class="${x.gate==='OPEN'?'ok':(x.gate==='LOCKDOWN'?'bad':'warn')}">${x.gate.slice(0,4)}</td><td class="${x.road>20?'dim':'bad'}">${x.road}%</td></tr>`).join('');
  document.querySelectorAll('#sectors tr.sec').forEach(tr=>tr.onclick=()=>{ const [x,y]=polar(+tr.dataset.s*60+30, 450); flyTo(x,y,520); });
  document.getElementById('nissues').textContent=`(${s.issues_total})`;
  document.getElementById('issues').innerHTML=s.issues.slice().reverse().map(i=>`<div><span class="${i.sev==='critical'?'bad':(i.sev==='warning'?'warn':'dim')}">${i.kind}</span> ${i.target} ${i.sector>0?'S'+i.sector:''} ${i.cause}, ${i.cost} cr (${i.payer}) <span class="dim">${i.status}, ${Math.round(i.age/60)} h</span></div>`).join('')||'<div>none</div>';
  document.getElementById('log').innerHTML=s.events.map(e=>`<div class="${e.level}">${String(e.t).padStart(6)} ${e.text}</div>`).join('');
  const mp=s.month_progress; if(mp && !s.report){ document.getElementById('report').textContent=`month ${s.finance.month} in progress, day ${mp.day} of ${mp.days} (the report closes on day ${mp.days})\nso far: ${mp.kwh} kWh, ${mp.water_m3} m3 water, repairs billed to owners ${mp.repairs} cr\nsector income ${mp.sector_income.join(' | ')}\nsector expense ${mp.sector_expense.join(' | ')}\ncolony income ${mp.colony_income}, expense ${mp.colony_expense}`; }
  const rp=s.report; if(rp){ document.getElementById('report').textContent=`Month ${rp.month}: owners paid ${Math.round(rp.houses_total)} cr (energy ${Math.round(rp.energy_total)}, water ${Math.round(rp.water_total)}, repairs ${Math.round(rp.repairs_total)}), ${Math.round(rp.kwh_total)} kWh\ncolony: income ${rp.colony_income}, expense ${rp.colony_expense}, budget ${rp.colony_budget}, unpaid ${rp.unpaid}\nsector income ${rp.sector_income.join(' | ')}\nsector expense ${rp.sector_expense.join(' | ')}\nexpense by cause: ${Object.entries(rp.by_cause).map(([k,v])=>k+' '+v).join(', ')}\ntop houses: ${rp.top_houses.map(h=>`#${h.house} (S${h.sector}) ${h.total}`).join(', ')}`; }
}
if(new URLSearchParams(location.search).has('inspect'))window.HH={camera,controls,scene,renderer,flyTo,houseDetails,utilityGroup,get geometry(){return G},get state(){return S}};
loadGeom().then(()=>{ poll(); frame(); });
</script></body></html>
"""

# ------------------------------------------------------------------------------------
# Bus page (served at /bus): what goes over MQTT, every house's controller, program comparison.
# ------------------------------------------------------------------------------------

HTMLBUS = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Hadley's Hope: bus</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { --bg:#0f1115; --panel:#171a21; --line:#2a2f3a; --text:#d9dde6; --dim:#8a93a6; --ok:#5ec07a; --warn:#e0b04a; --bad:#e2574d; --blue:#5aa9ff; --cyan:#4fd1c5; }
  * { box-sizing:border-box; } body { margin:0; background:var(--bg); color:var(--text); font:13px/1.35 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; padding:14px 18px; }
  h1 { font-size:16px; margin:0 0 8px; } h2 { font-size:12px; color:var(--dim); text-transform:uppercase; letter-spacing:.06em; margin:18px 0 8px; }
  a { color:var(--blue); } .row { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
  .grid { display:grid; grid-template-columns:2fr 1fr; gap:16px; } @media (max-width:1100px){ .grid { grid-template-columns:1fr; } }
  .card { background:#1a1f2a; border:1px solid var(--line); border-radius:8px; padding:8px 10px; }
  table { width:100%; border-collapse:collapse; font-size:11.5px; } th,td { padding:2px 5px; text-align:right; border-bottom:1px solid var(--line); white-space:nowrap; } th { color:var(--dim); font-weight:500; cursor:pointer; position:sticky; top:0; background:#1a1f2a; } td:first-child, th:first-child { text-align:left; } td.l, th.l { text-align:left; }
  .ok { color:var(--ok); } .warn { color:var(--warn); } .bad { color:var(--bad); } .dim { color:var(--dim); }
  #tail { font-family:ui-monospace,Menlo,Consolas,monospace; font-size:11px; max-height:420px; overflow-y:auto; background:#0b0e13; border:1px solid var(--line); border-radius:6px; padding:6px; }
  #tail div { padding:1px 0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; } .out { color:#f2c14e; } .in { color:#4fd1c5; }
  #houses { max-height:560px; overflow:auto; border:1px solid var(--line); border-radius:6px; }
  a.tab { color:var(--text); text-decoration:none; padding:4px 10px; border:1px solid var(--line); border-radius:6px; background:#1c212c; font-size:12px; } a.tab.on { border-color:var(--blue); color:var(--blue); } a.tab:hover { background:#2d3444; }
  select, input { background:#0b0e13; color:var(--text); border:1px solid var(--line); border-radius:6px; padding:3px 6px; font-size:12px; }
  .kpi { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:6px; } .kpi .v { font-size:16px; font-weight:600; } .kpi .l { color:var(--dim); font-size:11px; }
  .prog { display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:4px; }
</style></head>
<body>
<div class="row" style="margin-bottom:8px"><a href="/" class="tab">3D planet</a><a href="/flat" class="tab">flat map</a><a href="/bus" class="tab on">bus and programs</a><a href="/house" class="tab">house</a><a href="/graph" class="tab">systems</a><a href="/attractors" class="tab">Attractors</a></div>
<h1>Hadley's Hope: MQTT bus and house controllers &nbsp; <span id="time" class="dim" style="font-weight:400"></span></h1>
<div class="kpi" id="kpi"></div>
<h2>Program comparison, this month</h2>
<div class="card"><table id="progs"><thead><tr><th class="l">program</th><th>houses</th><th>avg indoor C</th><th>kWh per house per day</th><th>cost cr per house per day</th><th>time below 16 C</th></tr></thead><tbody></tbody></table>
<div class="dim" style="margin-top:6px">Each house reports its sensors to the bus, its program answers with actuators, the world applies them. Same weather, same grid, same houses, only the program differs. "thermostat" is the built-in fallback for houses without a live controller.</div></div>
<div class="grid">
  <div>
    <h2>Houses <span class="dim" style="text-transform:none;font-weight:400">(click a header to sort)</span></h2>
    <div class="row" style="margin-bottom:6px"><label>sector <select id="fsec"><option value="">all</option><option>1</option><option>2</option><option>3</option><option>4</option><option>5</option><option>6</option></select></label>
      <label>program <select id="fprog"><option value="">all</option></select></label><label>house # <input id="fid" size="5"></label><span id="count" class="dim"></span></div>
    <div id="houses"><table id="ht"><thead><tr><th>#</th><th>sec</th><th class="l">program</th><th class="l">last decision</th><th>target</th><th>indoor</th><th>heater</th><th>W</th><th>power</th><th>limit W</th><th>water</th><th>net</th><th>appl</th><th>valve</th><th>sensor age</th><th>decision age</th></tr></thead><tbody></tbody></table></div>
  </div>
  <div>
    <h2>Bus tail <span class="dim" style="text-transform:none;font-weight:400">(every 7th house sampled)</span></h2>
    <div id="tail"></div>
    <h2>Topics</h2>
    <div class="card dim" style="font-size:11.5px">
      <div><b class="out">hh/house/{id}/sensors</b> world to controller, retained, on change or every 10 min: t_in, power_ok, on_ups, limit_w, water_ok, pipes_ok, burst, net_online, sludge, draw_w, heater_on, residents</div>
      <div><b class="in">hh/house/{id}/actuators</b> controller to world: heater_on, target_c, valve_open, appliances_on, program, reason</div>
      <div><b class="out">hh/env/weather</b> t_out, wind, storm, precip, hour, night, daylight &nbsp; <b class="out">hh/env/power</b> available_kw, demand_kw, shedding, reactor_mode, tariff_kwh &nbsp; <b class="out">hh/tick</b> t, time</div>
      <div style="margin-top:6px">Shell: <code>mosquitto_sub -h localhost -t 'hh/#' -v</code></div>
    </div>
  </div>
</div>
<script>
let sortCol=0, sortDir=1, D=null; const COLS=16;
const pal=['#f2c14e','#5ec07a','#5aa9ff','#b48ead','#e2574d','#4fd1c5','#9aa3b5'];
document.querySelectorAll('#ht th').forEach((th,i)=>th.onclick=()=>{ if(sortCol===i) sortDir=-sortDir; else { sortCol=i; sortDir=1; } render(); });
['fsec','fprog','fid'].forEach(id=>document.getElementById(id).oninput=render);
async function poll(){ try{ D=await (await fetch('/bus.json')).json(); render(); } catch(e){ document.getElementById('time').textContent='update failed'; } setTimeout(poll,1000); }
function render(){ if(!D) return; document.getElementById('time').textContent=D.time+(D.env.storm?' STORM':'')+(D.env.shedding?' shedding L'+D.env.shedding:'');
  const m=D.mqtt; const names=[...new Set(D.houses.map(h=>h[2]))].sort(); const col=n=>pal[names.indexOf(n)%pal.length];
  document.getElementById('kpi').innerHTML=[['bus', m.enabled?(m.connected?'<span class="ok">connected</span> '+m.broker:'<span class="bad">disconnected</span>'):'<span class="warn">off</span>'],
    ['houses under programs', m.enabled?m.controlled+' / 300':'0 / 300'], ['sensor messages', m.enabled?m.sent.toLocaleString()+' ('+m.out_per_s.toFixed(0)+'/s)':'0'], ['actuator messages', m.enabled?m.received.toLocaleString()+' ('+m.in_per_s.toFixed(0)+'/s)':'0'], ['outdoor', D.env.t_out+' C']].map(([l,v])=>`<div class="card"><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');
  document.querySelector('#progs tbody').innerHTML=D.programs.map(p=>`<tr><td class="l"><span class="prog" style="background:${col(p.program)}"></span>${p.program}</td><td>${p.houses}</td><td class="${p.avg_t>19?'ok':(p.avg_t>15?'warn':'bad')}">${p.avg_t}</td><td>${p.kwh_per_house_day}</td><td>${p.cost_per_house_day}</td><td class="${p.cold_share<1?'ok':'warn'}">${p.cold_share} %</td></tr>`).join('');
  const sel=document.getElementById('fprog'); const cur=sel.value; if(sel.options.length!==names.length+1){ sel.innerHTML='<option value="">all</option>'+names.map(n=>`<option>${n}</option>`).join(''); sel.value=cur; }
  const fs=document.getElementById('fsec').value, fp=sel.value, fi=document.getElementById('fid').value.trim();
  let rows=D.houses.filter(h=>(!fs||String(h[1])===fs)&&(!fp||h[2]===fp)&&(!fi||String(h[0])===fi));
  rows.sort((a,b)=>{ const x=a[sortCol], y=b[sortCol]; return (typeof x==='number'? x-y : String(x).localeCompare(String(y)))*sortDir; });
  document.getElementById('count').textContent=rows.length+' houses';
  const flag=(v,good='ok',bad='bad')=>v?`<span class="${good}">yes</span>`:`<span class="${bad}">no</span>`;
  document.querySelector('#ht tbody').innerHTML=rows.slice(0,400).map(h=>`<tr><td><a href="/house?id=${h[0]}" target="_blank">${h[0]}</a></td><td>${h[1]}</td><td class="l"><span class="prog" style="background:${col(h[2])}"></span>${h[2]}</td><td class="l dim">${h[3]}</td><td>${h[4]}</td><td class="${h[5]>19?'ok':(h[5]>15?'warn':'bad')}">${h[5]}</td><td>${h[6]?'<span class="warn">on</span>':'off'}</td><td>${h[7]}</td><td>${h[8]?(h[9]?'<span class="warn">ups</span>':'<span class="ok">grid</span>'):'<span class="bad">none</span>'}</td><td>${h[10]||''}</td><td>${flag(h[11])}</td><td>${flag(h[12],'ok','warn')}</td><td>${h[15]?'on':'<span class="warn">off</span>'}</td><td>${h[16]?'open':'<span class="warn">closed</span>'}</td><td class="dim">${h[13]<0?'':h[13]+' min'}</td><td class="dim">${h[14]<0?'':h[14]+' min'}</td></tr>`).join('');
  document.getElementById('tail').innerHTML=D.tail.slice().reverse().map(x=>`<div class="${x.dir}">${x.dir==='out'?'&rarr;':'&larr;'} ${x.topic} <span class="dim">${x.body}</span></div>`).join('')||'<div class="dim">bus off or nothing yet</div>';
}
poll();
</script></body></html>
"""

# ------------------------------------------------------------------------------------
# Shared navigation strip, house page (/house?id=N) and the system graph (/graph)
# ------------------------------------------------------------------------------------

NAV_CSS = r"""
  nav.hh { overflow-x:auto;white-space:nowrap;min-height:52px;flex-shrink:0;display:flex; gap:6px; align-items:center; padding:6px 10px; background:#12151c; border-bottom:1px solid #262b36; font-size:12px; }
  nav.hh a { color:#d9dde6; text-decoration:none; padding:4px 10px; border:1px solid #262b36; border-radius:6px; background:#1c212c; }
  nav.hh a.on { border-color:#9fbca9; color:#d3e0c6; background:#20352e; } nav.hh a:hover { background:#2d3444; } nav.hh .t { margin-left:auto; color:#8a93a6; }
"""
NAV_HTML = r"""<nav class="hh"><a href="/" id="nav-3d">3D planet</a><a href="/flat" id="nav-flat">map</a><a href="/bus" id="nav-bus">controllers</a><a href="/house" id="nav-house">house</a><a href="/graph" id="nav-graph">systems</a><a href="/attractors" id="nav-attr">Attractors</a><span class="t" id="navtime"></span></nav>
<script>(function(){ const p=location.pathname.replace(/\/$/,'')||'/'; const id={'/':'nav-3d','/flat':'nav-flat','/bus':'nav-bus','/house':'nav-house','/graph':'nav-graph','/attractors':'nav-attr'}[p]; if(id) document.getElementById(id).classList.add('on'); })();</script>"""

HTMLHOUSE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Hadley's Hope: house</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { --bg:#0f1115; --panel:#171a21; --line:#2a2f3a; --text:#d9dde6; --dim:#8a93a6; --ok:#5ec07a; --warn:#e0b04a; --bad:#e2574d; --blue:#5aa9ff; --cyan:#4fd1c5; }
  * { box-sizing:border-box; } body { margin:0; background:var(--bg); color:var(--text); font:13px/1.35 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
  main { padding:14px 18px; } h1 { font-size:16px; margin:0 0 8px; } h2 { font-size:12px; color:var(--dim); text-transform:uppercase; letter-spacing:.06em; margin:16px 0 8px; }
  a { color:var(--blue); } .row { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
  .card { background:#1a1f2a; border:1px solid var(--line); border-radius:8px; padding:10px 12px; }
  .gauges { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:10px; } .gauge { text-align:center; } .gauge svg { width:100%; max-width:150px; height:150px; } .gauge .v { font-size:16px; font-weight:600; margin-top:4px; } .gauge .l { color:var(--dim); font-size:11px; }
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:14px; } @media (max-width:1000px){ .grid { grid-template-columns:1fr; } }
  .ok { color:var(--ok); } .warn { color:var(--warn); } .bad { color:var(--bad); } .dim { color:var(--dim); }
  #log { font-family:ui-monospace,Menlo,Consolas,monospace; font-size:11.5px; max-height:300px; overflow-y:auto; background:#0b0e13; border:1px solid var(--line); border-radius:6px; padding:6px; } #log div { padding:2px 0; }
  input, button { background:#0b0e13; color:var(--text); border:1px solid var(--line); border-radius:6px; padding:4px 8px; font-size:12px; } button { background:#232835; cursor:pointer; }
  table { width:100%; border-collapse:collapse; font-size:12px; } td { padding:3px 4px; border-bottom:1px solid var(--line); } td:first-child { color:var(--dim); width:45%; }
  canvas { display:block; }
  NAVCSS
</style></head>
<body>
NAVHTML
<main>
<div class="row"><h1 id="title">House</h1><button id="prev">&larr; prev</button><input id="hid" size="4"><button id="go">open</button><button id="next">next &rarr;</button><span id="sub" class="dim"></span></div>
<div class="gauges" id="gauges"></div>
<div class="grid">
  <div>
    <h2>Power draw right now</h2><div class="card row"><canvas id="pie" width="180" height="180"></canvas><div id="pielegend"></div></div>
    <h2>Last 24 hours</h2><div class="card"><div class="dim" style="font-size:11px">indoor temperature, C</div><canvas id="spark" width="600" height="110" style="width:100%"></canvas><div class="dim" style="font-size:11px;margin-top:6px">draw, W</div><canvas id="spark2" width="600" height="70" style="width:100%"></canvas></div>
    <h2>Facts</h2><div class="card"><table id="facts"></table></div>
  </div>
  <div>
    <h2>Controller</h2><div class="card" id="ctrl"></div>
    <h2>House log</h2><div id="log"></div>
  </div>
</div>
</main>
<script>
const q=new URLSearchParams(location.search); let id=Math.max(1,Math.min(300, +(q.get('id')||1)));
document.getElementById('hid').value=id; const setId=v=>{ id=Math.max(1,Math.min(300,v)); document.getElementById('hid').value=id; history.replaceState(null,'','/house?id='+id); poll(true); };
document.getElementById('prev').onclick=()=>setId(id-1); document.getElementById('next').onclick=()=>setId(id+1); document.getElementById('go').onclick=()=>setId(+document.getElementById('hid').value||1); document.getElementById('hid').onkeydown=e=>{ if(e.key==='Enter') setId(+e.target.value||1); };
let timer=null;
async function poll(now){ if(timer) clearTimeout(timer); try{ const d=await (await fetch('/house.json?id='+id)).json(); render(d); }catch(e){ document.getElementById('sub').textContent='update failed'; } timer=setTimeout(poll,1000); }
function thermo(t, target){ const u=Math.max(0,Math.min(1,(t+50)/80)); const y=120-90*u; const ty=120-90*Math.max(0,Math.min(1,(target+50)/80)); const col=t>19?'#5ec07a':(t>10?'#e0b04a':'#e2574d');
  return `<svg viewBox="0 0 80 150"><rect x="30" y="20" width="20" height="110" rx="10" fill="#0b0e13" stroke="#8a93a6"/><rect x="34" y="${y}" width="12" height="${130-y}" rx="6" fill="${col}"/><circle cx="40" cy="128" r="14" fill="${col}"/><line x1="22" y1="${ty}" x2="58" y2="${ty}" stroke="#5aa9ff" stroke-width="2"/><text x="62" y="${ty+4}" fill="#5aa9ff" font-size="9">${target}</text>${[-40,-20,0,20].map(v=>`<text x="10" y="${124-90*(v+50)/80}" fill="#8a93a6" font-size="8">${v}</text>`).join('')}</svg>`; }
function tank(frac, ok){ const h=90*Math.max(0,Math.min(1,frac)); const col=ok?'#5aa9ff':'#e2574d'; return `<svg viewBox="0 0 120 150"><rect x="20" y="25" width="80" height="100" rx="8" fill="#0b0e13" stroke="#8a93a6"/><rect x="24" y="${121-h}" width="72" height="${h}" rx="6" fill="${col}" opacity=".8"/><path d="M60 8 v14" stroke="${col}" stroke-width="6"/><rect x="40" y="128" width="40" height="8" fill="#5a6070"/>${ok?'':'<text x="60" y="80" fill="#fff" font-size="12" text-anchor="middle">NO WATER</text>'}</svg>`; }
function bolt(ok, ups, limit, upsFrac){ const col=!ok?'#e2574d':(ups?'#4fd1c5':'#f2c14e'); return `<svg viewBox="0 0 120 150"><circle cx="60" cy="70" r="46" fill="#0b0e13" stroke="${col}" stroke-width="3"/><path d="M68 28 L44 76 H62 L52 112 L82 60 H64 Z" fill="${col}"/>${ups?`<rect x="20" y="126" width="80" height="10" rx="3" fill="#0b0e13" stroke="#8a93a6"/><rect x="22" y="128" width="${76*upsFrac}" height="6" rx="2" fill="#4fd1c5"/>`:''}${limit?`<text x="60" y="145" fill="#e0b04a" font-size="10" text-anchor="middle">limit ${limit} W</text>`:''}</svg>`; }
function wifi(ok, cab){ const col=ok?'#4fd1c5':'#e2574d'; return `<svg viewBox="0 0 120 150">${[46,34,22].map((r,k)=>`<path d="M${60-r} 90 A${r} ${r} 0 0 1 ${60+r} 90" fill="none" stroke="${k<(ok?3:1)?col:'#2a2f3a'}" stroke-width="6" stroke-linecap="round"/>`).join('')}<circle cx="60" cy="100" r="6" fill="${col}"/>${ok?'':`<line x1="30" y1="40" x2="90" y2="115" stroke="#e2574d" stroke-width="5"/>`}<text x="60" y="140" fill="#8a93a6" font-size="10" text-anchor="middle">${cab?'cabinet up':'cabinet down'}</text></svg>`; }
function sludge(frac, ok){ const h=90*Math.max(0,Math.min(1,frac)); const col=frac>0.9?'#e2574d':(frac>0.7?'#e0b04a':'#9bd36a'); return `<svg viewBox="0 0 120 150"><rect x="30" y="25" width="60" height="100" rx="30" fill="#0b0e13" stroke="#8a93a6"/><rect x="34" y="${121-h}" width="52" height="${h}" rx="20" fill="${col}" opacity=".85"/><circle cx="60" cy="30" r="6" fill="${ok?'#5ec07a':'#e2574d'}"/><text x="60" y="145" fill="#8a93a6" font-size="10" text-anchor="middle">${ok?'aeration on':'aeration broken'}</text></svg>`; }
function render(d){ document.getElementById('title').textContent=`House ${d.id}, sector ${d.sector}, ${d.type}, ${d.residents} residents`; document.getElementById('sub').textContent=d.time+(d.shedding?' (grid shedding L'+d.shedding+')':''); document.getElementById('navtime').textContent=d.time;
  document.getElementById('gauges').innerHTML=[
    ['indoor', thermo(d.t_in, d.target), d.t_in+' C', 'outside '+d.t_out+' C, target '+d.target],
    ['power', bolt(d.power_ok, d.on_ups, d.limit_w, d.ups_kwh/d.ups_cap), d.power_ok?(d.on_ups?'sector UPS':'grid')+' '+d.draw_w+' W':'no power', d.on_ups?'UPS '+d.ups_kwh+' / '+d.ups_cap+' kWh':(d.limit_w?'limited by the grid':'heater '+(d.heater_on?'on':'off'))],
    ['water', tank(d.tank_m3/d.tank_cap, d.water_ok), d.water_ok?'flowing':'none', 'city tank '+d.tank_m3+' m3'+(d.burst?', pipes burst':(!d.pipes_ok?', pipes frozen':''))+(d.valve_open?'':', valve closed')],
    ['network', wifi(d.net_online, d.cabinet), d.net_online?'online':'offline', d.terminal_ok?'terminal ok':'terminal broken'],
    ['sewage', sludge(d.sludge, d.aeration_ok), Math.round(d.sludge*100)+'% sludge', d.sludge>0.9?'hauler requested':'ok'],
  ].map(([l,svg,v,s])=>`<div class="card gauge">${svg}<div class="v">${v}</div><div class="l">${l}: ${s}</div></div>`).join('');
  // pie of the draw
  const c=document.getElementById('pie').getContext('2d'); c.clearRect(0,0,180,180); const parts=[['heater',d.split.heater,'#ff7a30'],['appliances',d.split.appliances,'#f2c14e'],['aeration',d.split.aeration,'#9bd36a'],['fridge',d.split.fridge,'#5aa9ff']]; const tot=parts.reduce((a,p)=>a+p[1],0)||1; let a0=-Math.PI/2;
  for(const [n,v,col] of parts){ const a1=a0+2*Math.PI*v/tot; c.beginPath(); c.moveTo(90,90); c.arc(90,90,80,a0,a1); c.closePath(); c.fillStyle=col; c.fill(); a0=a1; } c.beginPath(); c.arc(90,90,48,0,7); c.fillStyle='#1a1f2a'; c.fill(); c.fillStyle='#d9dde6'; c.font='600 15px sans-serif'; c.textAlign='center'; c.fillText(d.draw_w+' W',90,95);
  document.getElementById('pielegend').innerHTML=parts.map(([n,v,col])=>`<div><span style="display:inline-block;width:10px;height:10px;background:${col};border-radius:2px;margin-right:6px"></span>${n} <b>${v} W</b> <span class="dim">${Math.round(v/tot*100)}%</span></div>`).join('')+`<div class="dim" style="margin-top:6px">this month ${d.kwh_month} kWh, bill so far ${d.bill_month} cr</div>`;
  spark('spark', d.hist_t, '#5ec07a', -50, 30, d.target); spark('spark2', d.hist_w, '#f2c14e', 0, Math.max(1000, Math.max(...d.hist_w)), null);
  document.getElementById('facts').innerHTML=[['program',d.program],['pole',d.pole+(d.pole_online?' (energised)':' (dead)')],['water this month',d.water_month_m3+' m3'],['energy total',d.kwh_total+' kWh'],['appliances',d.appliances_on?'on':'switched off by the program'],['open issues',d.issues.length?d.issues.map(i=>i.kind+' ('+i.status+', '+i.cost+' cr)').join(', '):'none']].map(([k,v])=>`<tr><td>${k}</td><td>${v}</td></tr>`).join('');
  document.getElementById('ctrl').innerHTML=`<div><b>${d.program}</b>${d.ctrl_age>=0?` <span class="dim">decided ${d.ctrl_age} min ago</span>`:''}</div><div>${d.reason}</div><div class="dim">target ${d.target} C, heater ${d.heater_on?'on':'off'} (${d.heater_w} W rated, ${d.heat_w} W delivered)</div>`;
  document.getElementById('log').innerHTML=[...d.log.map(e=>`<div><span class="dim">${e.t}</span> ${e.text}</div>`), ...d.events.map(e=>`<div><span class="dim">${e.t}</span> <span class="warn">${e.text}</span></div>`)].join('')||'<div class="dim">nothing yet</div>'; }
function spark(id, arr, col, lo, hi, ref){ const cv=document.getElementById(id), c=cv.getContext('2d'); const W=cv.width, H=cv.height; c.clearRect(0,0,W,H); c.strokeStyle='#2a2f3a'; c.beginPath(); for(let k=0;k<=4;k++){ const y=H-1-(H-2)*k/4; c.moveTo(0,y); c.lineTo(W,y); } c.stroke();
  if(ref!==null){ const y=H-1-(H-2)*(ref-lo)/(hi-lo); c.strokeStyle='#5aa9ff'; c.setLineDash([4,4]); c.beginPath(); c.moveTo(0,y); c.lineTo(W,y); c.stroke(); c.setLineDash([]); }
  c.strokeStyle=col; c.lineWidth=2; c.beginPath(); arr.forEach((v,i)=>{ const x=i/(arr.length-1)*W, y=H-1-(H-2)*Math.max(0,Math.min(1,(v-lo)/(hi-lo))); i?c.lineTo(x,y):c.moveTo(x,y); }); c.stroke();
  c.fillStyle='#8a93a6'; c.font='10px sans-serif'; c.fillText(lo,2,H-3); c.fillText(hi,2,10); }
poll();
</script></body></html>
""".replace("NAVCSS", NAV_CSS).replace("NAVHTML", NAV_HTML)

HTMLGRAPH = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Hadley's Hope: system graph</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { --bg:#0f1115; --panel:#171a21; --line:#2a2f3a; --text:#d9dde6; --dim:#8a93a6; }
  * { box-sizing:border-box; } body { margin:0; background:var(--bg); color:var(--text); font:13px/1.35 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; display:flex; flex-direction:column; height:100vh; overflow:hidden; }
  #wrap { flex:1; position:relative; } canvas { display:block; width:100%; height:100%; cursor:grab; }
  #legend { position:absolute; left:10px; top:10px; background:rgba(18,21,28,.9); border:1px solid var(--line); border-radius:8px; padding:8px 10px; font-size:11.5px; max-width:340px; }
  #legend label { display:inline-flex; gap:4px; align-items:center; margin-right:8px; } .sw { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:4px; }
  #tip { position:absolute; display:none; background:rgba(18,21,28,.95); border:1px solid var(--line); border-radius:6px; padding:6px 8px; font-size:11.5px; pointer-events:none; max-width:280px; }
  NAVCSS
</style></head>
<body>
NAVHTML
<div id="wrap"><canvas id="c"></canvas>
<div id="legend"><b>System graph</b> <span class="dim" id="stats"></span><br>
<span class="sw" style="background:#f2c14e"></span>power <span class="sw" style="background:#4fd1c5"></span>network <span class="sw" style="background:#5aa9ff"></span>water <span class="sw" style="background:#b48ead"></span>control (program)<br>
<label><input type="checkbox" id="lPoles" checked> poles</label><label><input type="checkbox" id="lCtrl" checked> program links</label><label><input type="checkbox" id="lWater" checked> water</label><label><input type="checkbox" id="lSim" checked> physics</label><br>
<span class="dim">drag nodes, wheel to zoom, drag background to pan, click a house to open it. Node colour: green fine, amber limited or on UPS, red dead, grey offline. Edge colour: lit when the link carries.</span></div>
<div id="tip"></div></div>
<script>
const cv=document.getElementById('c'), ctx=cv.getContext('2d'); const tip=document.getElementById('tip');
let G=null, S=null, nodes=[], edges=[], byId={}, view={x:0,y:0,k:1}, drag=null, hover=null, panning=null, simOn=true;
const opt={poles:true, ctrl:true, water:true};
['lPoles','lCtrl','lWater','lSim'].forEach(id=>document.getElementById(id).onchange=e=>{ const k=id.slice(1).toLowerCase(); if(k==='sim') simOn=e.target.checked; else { opt[k]=e.target.checked; } });
function node(id, type, label, x, y, r){ const n={id,type,label,x,y,vx:0,vy:0,r,fixed:false,state:'ok'}; nodes.push(n); byId[id]=n; return n; }
function edge(a,b,kind){ edges.push({a:byId[a], b:byId[b], kind, on:true}); }
async function init(){ G=await (await fetch('/geometry')).json(); const c=G.cfg; const sc=0.9; const P=v=>[v[0]*sc, v[1]*sc];
  node('reactor','plant','reactor', ...P([c.reactor_pos[0],c.reactor_pos[1]]), 16); node('solar','plant','solar field', ...P(c.solar_pos), 9); node('wplant','plant','water plant', ...P(c.water_plant_pos), 10);
  node('substation','hub','substation', 0, -60, 13); node('ups','hub','UPS center', -70, 10, 9); node('comms','hub','comms node', 70, 10, 10); node('tank','hub','water tank', -50, -40, 9); node('ops','hub','ops center', 0, 70, 9);
  node('tower','plant','radio mast', ...P(c.tower_pos), 10); node('dish','plant','deep-space dish', c.tower_pos[0]*sc+70, c.tower_pos[1]*sc+10, 10);
  edge('reactor','substation','power'); edge('solar','substation','power'); edge('wplant','tank','water'); edge('substation','tower','power'); edge('comms','tower','net'); edge('tower','dish','net'); edge('substation','ups','power'); edge('substation','ops','power'); edge('substation','comms','power'); edge('comms','reactor','net');
  for(let s=0;s<c.sectors;s++){ const a=(s*60+3)*Math.PI/180; const rp=node('rp'+s,'sector',`S${s+1} distribution`, Math.cos(a)*180, Math.sin(a)*180, 8); node('cab'+s,'sector',`S${s+1} cabinet`, Math.cos(a+0.08)*180, Math.sin(a+0.08)*180, 6); node('main'+s,'sector',`S${s+1} water main`, Math.cos(a-0.08)*180, Math.sin(a-0.08)*180, 5);
    edge('substation','rp'+s,'power'); edge('comms','cab'+s,'net'); edge('tank','main'+s,'water'); }
  for(let i=0;i<G.poles.x.length;i++){ node('p'+i,'pole','pole '+i, G.poles.x[i]*sc, G.poles.y[i]*sc, 2.5); }
  for(let i=0;i<G.poles.x.length;i++){ const p=G.poles.parent[i]; if(p<0) edge('rp'+G.poles.sector[i],'p'+i,'power'); else edge('p'+p,'p'+i,'power'); if(p<0) edge('cab'+G.poles.sector[i],'p'+i,'net'); else edge('p'+p,'p'+i,'net'); }
  for(let i=0;i<G.houses.x.length;i++){ node('h'+i,'house','house '+(i+1), G.houses.x[i]*sc, G.houses.y[i]*sc, 4); edge('p'+G.houses.pole[i],'h'+i,'power'); edge('p'+G.houses.pole[i],'h'+i,'net'); edge('main'+G.houses.sector[i],'h'+i,'water'); }
  const progs=['comfort','eco','night-setback','storm-ready','dumb','thermostat']; progs.forEach((p,k)=>{ const a=k/progs.length*Math.PI*2; node('prog:'+p,'prog',p, Math.cos(a)*820, Math.sin(a)*820, 12); });
  view.x=cv.clientWidth/2; view.y=cv.clientHeight/2; view.k=Math.min(cv.clientWidth/2400, cv.clientHeight/1500); poll(); loop(); }
let ctrlEdges=[];
async function poll(){ try{ S=await (await fetch('/state')).json(); apply(); }catch(e){} setTimeout(poll,1000); }
function apply(){ const hs=S.houses, pl=S.poles; document.getElementById('navtime').textContent=S.time;
  for(let i=0;i<hs.t.length;i++){ const n=byId['h'+i]; n.state=!hs.power[i]?'dead':(hs.ups[i]||hs.limit[i]?'warn':'ok'); n.net=!!hs.net[i]; n.info=`house ${i+1}: ${hs.t[i]} C, ${hs.power[i]?(hs.ups[i]?'UPS':'grid'):'no power'}, ${hs.water[i]?'water':'no water'}, ${hs.net[i]?'online':'offline'}, ${S.control.programs[i]||'thermostat'}`; }
  for(let i=0;i<pl.state.length;i++){ const n=byId['p'+i]; n.state=pl.state[i]===2?'dead':(pl.span[i]?'ok':'warn'); n.info=`pole ${i}: ${['standing','tilted','fallen'][pl.state[i]]}, span ${pl.span[i]?'live':'dead'}, cable ${pl.net[i]?'ok':'cut'}`; }
  for(let s=0;s<S.sectors.length;s++){ const x=S.sectors[s]; byId['rp'+s].state=x.online?'ok':'dead'; byId['rp'+s].info=`sector ${s+1}: ${x.demand_kw} kW, ${x.power_ok}/50 powered, UPS ${x.ups}`; byId['cab'+s].state=x.cabinet?'ok':'dead'; byId['cab'+s].info=`cabinet: ${x.net_ok}/50 online`; byId['main'+s].state=x.water_ok>0?'ok':'dead'; byId['main'+s].info=`water main: ${x.water_m3_h} m3/h`; }
  const r=S.reactor; byId.reactor.state=r.mode==='ONLINE'?'ok':(r.mode==='RUNBACK'?'warn':'dead'); byId.reactor.info=`reactor ${r.mode}, ${r.power_mw} MW, core ${r.core_temp} C`; byId.substation.state=S.power.substation&&S.power.trunk?'ok':'dead'; byId.substation.info=`substation ${S.power.available_kw} kW available, ${S.power.demand_kw} kW load, shedding L${S.power.shedding}`;
  byId.solar.info=`solar ${S.power.solar_kw} kW`; byId.solar.state=S.power.solar_kw>0?'ok':'warn'; byId.wplant.state=S.water.plant?'ok':'dead'; byId.wplant.info=`water plant ${S.water.plant_m3_h} m3/h`; byId.tank.info=`tank ${S.water.tank_m3} m3`; byId.tank.state=S.water.tank_m3>50?'ok':'warn'; byId.comms.state=S.net.comms?'ok':'dead'; byId.comms.info=`comms ${S.net.houses_online}/300 online, ${S.net.packets_per_min} pkt/min`; byId.tower.state=S.power.tower_line?'ok':'dead'; byId.dish.state=S.net.uplink?'ok':'dead'; byId.dish.info=`uplink ${S.net.uplink?'OK':'LOST'}`; byId.ups.info=`UPS center ${S.power.ups_center_kwh} kWh ${S.power.ups_center}`; byId.ops.info='operations center';
  for(const e of edges){ if(e.kind==='power'){ if(e.b.type==='pole'){ const i=+e.b.id.slice(1); e.on=!!pl.span[i]; } else if(e.b.type==='house'){ const i=+e.b.id.slice(1); e.on=!!hs.power[i]; } else if(e.b.type==='sector'){ e.on=e.b.state==='ok'; } else e.on=S.power.trunk; }
    else if(e.kind==='net'){ if(e.b.type==='pole'){ const i=+e.b.id.slice(1); e.on=!!pl.net[i]; } else if(e.b.type==='house'){ const i=+e.b.id.slice(1); e.on=!!hs.net[i]; } else if(e.b.type==='sector'){ e.on=e.b.state==='ok'; } else e.on=S.net.uplink; }
    else if(e.kind==='water'){ e.on=e.b.type==='house'?!!hs.water[+e.b.id.slice(1)]:e.b.state==='ok'; } }
  ctrlEdges=[]; for(let i=0;i<hs.t.length;i++){ const p=S.control.ext[i]?S.control.programs[i]:'thermostat'; const pn=byId['prog:'+p]; if(pn) ctrlEdges.push({a:pn, b:byId['h'+i], kind:'ctrl', on:true}); }
  const counts={}; ctrlEdges.forEach(e=>counts[e.a.label]=(counts[e.a.label]||0)+1); for(const n of nodes) if(n.type==='prog'){ n.info=`${n.label}: ${counts[n.label]||0} houses`; n.state=counts[n.label]?'ok':'off'; }
  document.getElementById('stats').textContent=`${nodes.length} nodes, ${edges.length+ctrlEdges.length} edges, ${S.time}`; }
function step(){ if(!simOn) return; const K=0.02; for(const n of nodes){ n.fx=0; n.fy=0; }
  // repulsion (grid-bucketed), springs along edges, gentle pull to the original layout
  const cell=60, grid=new Map(); for(const n of nodes){ const k=Math.floor(n.x/cell)+','+Math.floor(n.y/cell); (grid.get(k)||grid.set(k,[]).get(k)).push(n); }
  for(const n of nodes){ const gx=Math.floor(n.x/cell), gy=Math.floor(n.y/cell); for(let dx=-1;dx<=1;dx++) for(let dy=-1;dy<=1;dy++){ const b=grid.get((gx+dx)+','+(gy+dy)); if(!b) continue; for(const m of b){ if(m===n) continue; let ex=n.x-m.x, ey=n.y-m.y; let d2=ex*ex+ey*ey+1; if(d2>3600) continue; const f=120/d2; n.fx+=ex*f; n.fy+=ey*f; } } }
  const all=opt.ctrl?edges.concat(ctrlEdges):edges; for(const e of all){ if(!opt.poles&&(e.a.type==='pole'||e.b.type==='pole')) continue; if(!opt.water&&e.kind==='water') continue; const ex=e.b.x-e.a.x, ey=e.b.y-e.a.y, d=Math.hypot(ex,ey)||1; const want=e.kind==='ctrl'?600:(e.kind==='water'?40:28); const f=(d-want)*(e.kind==='ctrl'?0.002:0.02); e.a.fx+=ex/d*f; e.a.fy+=ey/d*f; e.b.fx-=ex/d*f; e.b.fy-=ey/d*f; }
  for(const n of nodes){ if(n.home===undefined){ n.home=[n.x,n.y]; } n.fx+=(n.home[0]-n.x)*0.004; n.fy+=(n.home[1]-n.y)*0.004; if(n.fixed) continue; n.vx=(n.vx+n.fx*K)*0.85; n.vy=(n.vy+n.fy*K)*0.85; n.x+=n.vx; n.y+=n.vy; } }
const colors={ok:'#5ec07a', warn:'#e0b04a', dead:'#e2574d', off:'#555'};
const kindCol={power:'#f2c14e', net:'#4fd1c5', water:'#5aa9ff', ctrl:'#b48ead'};
function draw(){ const W=cv.clientWidth, H=cv.clientHeight; if(cv.width!==W*devicePixelRatio){ cv.width=W*devicePixelRatio; cv.height=H*devicePixelRatio; } ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0); ctx.clearRect(0,0,W,H); ctx.save(); ctx.translate(view.x,view.y); ctx.scale(view.k,view.k);
  const all=opt.ctrl?edges.concat(ctrlEdges):edges; ctx.lineWidth=1/view.k; for(const e of all){ if(!opt.poles&&(e.a.type==='pole'||e.b.type==='pole')) continue; if(!opt.water&&e.kind==='water') continue; ctx.strokeStyle=e.on?kindCol[e.kind]:'#3a2a2a'; ctx.globalAlpha=e.kind==='ctrl'?0.18:(e.on?0.75:0.5); ctx.beginPath(); ctx.moveTo(e.a.x,e.a.y); ctx.lineTo(e.b.x,e.b.y); ctx.stroke(); } ctx.globalAlpha=1;
  for(const n of nodes){ if(!opt.poles&&n.type==='pole') continue; ctx.beginPath(); ctx.arc(n.x,n.y,n.r,0,7); ctx.fillStyle=n.type==='prog'?'#b48ead':(n.type==='house'&&n.net===false?'#6a5a7a':colors[n.state]||'#888'); ctx.fill(); if(n.type!=='pole'&&n.type!=='house'){ ctx.strokeStyle='#d9dde6'; ctx.lineWidth=1.2/view.k; ctx.stroke(); } if(n===hover){ ctx.strokeStyle='#fff'; ctx.lineWidth=2/view.k; ctx.stroke(); }
    if(n.type!=='pole'&&n.type!=='house'&&view.k>0.25){ ctx.fillStyle='#d9dde6'; ctx.font=`${12/view.k}px sans-serif`; ctx.textAlign='center'; ctx.fillText(n.label, n.x, n.y-n.r-4/view.k); } }
  ctx.restore(); }
function loop(){ step(); draw(); requestAnimationFrame(loop); }
function toWorld(ev){ const r=cv.getBoundingClientRect(); return [ (ev.clientX-r.left-view.x)/view.k, (ev.clientY-r.top-view.y)/view.k ]; }
function pick(x,y){ let best=null, bd=1e9; for(const n of nodes){ if(!opt.poles&&n.type==='pole') continue; const d=Math.hypot(n.x-x,n.y-y); if(d<Math.max(n.r+3/view.k, 6/view.k)&&d<bd){ bd=d; best=n; } } return best; }
cv.addEventListener('pointerdown', ev=>{ const [x,y]=toWorld(ev); const n=pick(x,y); if(n){ drag={n, moved:false}; n.fixed=true; } else panning={x:ev.clientX, y:ev.clientY, vx:view.x, vy:view.y}; cv.setPointerCapture(ev.pointerId); });
cv.addEventListener('pointermove', ev=>{ const [x,y]=toWorld(ev); if(drag){ drag.n.x=x; drag.n.y=y; drag.n.home=[x,y]; drag.moved=true; } else if(panning){ view.x=panning.vx+(ev.clientX-panning.x); view.y=panning.vy+(ev.clientY-panning.y); } else { hover=pick(x,y); if(hover){ const r=cv.getBoundingClientRect(); tip.style.display='block'; tip.style.left=(ev.clientX-r.left+14)+'px'; tip.style.top=(ev.clientY-r.top+14)+'px'; tip.textContent=hover.info||hover.label; } else tip.style.display='none'; } });
cv.addEventListener('pointerup', ev=>{ if(drag){ const n=drag.n; if(!drag.moved){ if(n.type==='house') window.open('/house?id='+(+n.id.slice(1)+1),'_blank'); } n.fixed=false; drag=null; } panning=null; });
cv.addEventListener('wheel', ev=>{ ev.preventDefault(); const r=cv.getBoundingClientRect(); const mx=ev.clientX-r.left, my=ev.clientY-r.top; const f=Math.exp(-ev.deltaY*0.0015); view.x=mx-(mx-view.x)*f; view.y=my-(my-view.y)*f; view.k*=f; }, {passive:false});
init();
</script></body></html>
""".replace("NAVCSS", NAV_CSS).replace("NAVHTML", NAV_HTML)

HTMLATTR = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Hadley's Hope: attractors</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { --bg:#0f1115; --panel:#171a21; --line:#2a2f3a; --text:#d9dde6; --dim:#8a93a6; --ok:#5ec07a; --warn:#e0b04a; --bad:#e2574d; }
  * { box-sizing:border-box; } body { margin:0; background:var(--bg); color:var(--text); font:13px/1.35 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; display:flex; flex-direction:column; height:100vh; overflow:hidden; }
  #body { flex:1; display:flex; min-height:0; }
  #wrap { flex:1; position:relative; min-width:0; } #wrap canvas { position:absolute; left:0; top:0; width:100%; height:100%; display:block; }
  #side { width:430px; flex:0 0 430px; border-left:1px solid var(--line); overflow-y:auto; padding:8px 10px; background:#12151c; }
  .pn { background:#161a22; border:1px solid var(--line); border-radius:8px; padding:8px 10px; margin-bottom:8px; }
  .pn h3 { margin:0 0 4px; font-size:12px; font-weight:600; display:flex; align-items:center; gap:8px; } .pn h3 .ax { margin-left:auto; color:var(--dim); font-weight:400; font-size:11px; }
  .pn canvas { width:100%; height:170px; display:block; } .pn .v { font-size:11.5px; margin-top:4px; }
  .pill { font-size:10.5px; padding:1px 7px; border-radius:9px; border:1px solid; } .pill.ok { color:var(--ok); border-color:var(--ok); } .pill.warn { color:var(--warn); border-color:var(--warn); } .pill.bad { color:var(--bad); border-color:var(--bad); }
  #legend { position:absolute; left:56px; bottom:46px; background:rgba(18,21,28,.9); border:1px solid var(--line); border-radius:8px; padding:8px 10px; font-size:11.5px; max-width:360px; z-index:3; }
  #legend label { display:inline-flex; gap:4px; align-items:center; margin-right:8px; } .sw { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:4px; vertical-align:-1px; }
  .dim { color:var(--dim); } .ok { color:var(--ok); } .warn { color:var(--warn); } .bad { color:var(--bad); }
  #tip { position:absolute; display:none; background:rgba(18,21,28,.95); border:1px solid var(--line); border-radius:6px; padding:6px 8px; font-size:11.5px; pointer-events:none; max-width:300px; z-index:4; }
  @media (max-width:1100px){ #body { flex-direction:column; } #side { width:auto; flex:0 0 auto; max-height:45vh; border-left:0; border-top:1px solid var(--line); } }
  #phase-toolbar{position:absolute;left:18px;right:18px;top:14px;z-index:5;display:flex;gap:10px;align-items:center;flex-wrap:wrap;pointer-events:none}
  #phase-toolbar button,#phase-toolbar select{pointer-events:auto;background:#162527;color:#bfcfc5;border:1px solid #3d5750;border-radius:4px;padding:8px 10px;font:11px sans-serif}
  #phase-toolbar button[aria-pressed=true]{background:#304739;color:#e3eccb;border-color:#98b18c}
  #phase-toolbar label{font-size:10px;color:#9caf9f;pointer-events:auto}#phase-help{position:absolute;left:18px;top:58px;color:#a3b6aa;font-size:10px;z-index:3;pointer-events:none}
  #connection{position:absolute;right:18px;bottom:15px;font-size:10px;z-index:4;color:#9eb7a8;background:#10191be6;padding:5px 8px;border-radius:3px}
  #legend{left:18px;bottom:20px;max-width:380px;background:#10191bee;border-color:#334840;border-radius:5px;line-height:1.55}
  #side{background:#11191c;border-color:#30443c;padding:12px}.pn{border-radius:5px;background:#152023;border-color:#2e4540;margin-bottom:12px;padding:12px}.pn h3{font-size:12px;color:#dce4d4}.pn .v{line-height:1.55;color:#b3c4b8}.pn .ax{font-size:9px!important}
  @media(max-width:650px){#phase-toolbar{gap:4px;left:10px;right:10px}#phase-toolbar button,#phase-toolbar select{font-size:10px;padding:6px}#phase-help{top:85px;font-size:9px;max-width:85%}#legend{font-size:9px;max-width:270px;bottom:10px}#connection{display:none}}
  NAVCSS
</style></head>
<body>
NAVHTML
<div id="body">
<div id="wrap"><canvas id="trail"></canvas><canvas id="bg"></canvas><canvas id="top"></canvas>
<div id="phase-toolbar"><div role="group" aria-label="Phase-space view"><button data-phase="thermal" aria-pressed="true">Thermal phase</button><button data-phase="coupled" aria-pressed="false">3D · water coupling</button></div><label>Colour <select id="phase-colour"><option value="basin">Thermal basin</option><option value="sector">District</option><option value="pressure">Water pressure</option></select></label></div>
<div id="phase-help">Thermal phase portrait · click a house to open its details</div><div id="connection" role="status">Connecting…</div>
<div id="legend"><b>Attractor observatory</b><br>
<span class="dim">Dots show measured house states. Thermal view: temperature × °C/h. Flow previews hold current weather and power fixed; basins are conditional equilibria, not guaranteed forecasts.</span><br>
<span id="phase-colour-key"><span class="sw" style="background:#5ec07a"></span>warm basin <span class="sw" style="background:#e0b04a"></span>cannot hold target <span class="sw" style="background:#e2574d"></span>will freeze <span class="sw" style="background:#8a7aa6"></span>pipes burst</span><br>
<span id="counts" class="dim"></span><br>
<label><input type="checkbox" id="oDust" checked> flow preview</label><label><input type="checkbox" id="oCurves" checked> curves</label><label><input type="checkbox" id="oHouses" checked> houses</label>
</div>
<div id="tip"></div></div>
<div id="side">
  <div class="pn"><h3>Water tank <span class="pill" id="pw"></span><span class="ax">x tank m3, y net m3/h</span></h3><canvas id="cw"></canvas><div class="v" id="vw"></div></div>
  <div class="pn"><h3>Power and UPS <span class="pill" id="pp"></span><span class="ax">x margin kW, y UPS %</span></h3><canvas id="cp"></canvas><div class="v" id="vp"></div></div>
  <div class="pn"><h3>Repairs queue <span class="pill" id="pr"></span><span class="ax">x open issues, y burst houses</span></h3><canvas id="cr"></canvas><div class="v" id="vr"></div></div>
  <div class="pn"><h3>Colony money <span class="pill" id="pm"></span><span class="ax">x budget k cr, y k cr/day</span></h3><canvas id="cm"></canvas><div class="v" id="vm"></div></div>
</div>
</div>
<script>
const $=id=>document.getElementById(id);
const BG=$('bg'), TR=$('trail'), TP=$('top'), bgc=BG.getContext('2d'), trc=TR.getContext('2d'), tpc=TP.getContext('2d'), tip=$('tip');
const COL=['#5ec07a','#e0b04a','#e2574d','#8a7aa6'], DUST=['rgba(79,209,197,','rgba(224,176,74,','rgba(226,87,77,','rgba(138,122,166,'];
const TMIN=-58, TMAX=35, RMIN=-3.2, RMAX=2.2, C0=21, SQ=1.5;
let A=null, H=null, W=0, Hh=0, dpr=1, pad={l:46,r:18,t:100,b:34}, pollN=0, dirty=true;
const opt={dust:true, curves:true, houses:true};
[['oDust','dust'],['oCurves','curves'],['oHouses','houses']].forEach(([id,k])=>$(id).onchange=e=>{ opt[k]=e.target.checked; dirty=true; if(k==='dust'){ trc.fillStyle='#0f1115'; trc.fillRect(0,0,W,Hh); } });
const asinh=Math.asinh, u0=asinh((TMIN-C0)/SQ), u1=asinh((TMAX-C0)/SQ);
const X=T=>pad.l+(asinh((Math.max(TMIN,Math.min(TMAX,T))-C0)/SQ)-u0)/(u1-u0)*(W-pad.l-pad.r);
const Y=r=>pad.t+(RMAX-Math.max(RMIN,Math.min(RMAX,r)))/(RMAX-RMIN)*(Hh-pad.t-pad.b);
function resize(){ const r=$('wrap').getBoundingClientRect(); dpr=devicePixelRatio||1; W=r.width; Hh=r.height; for(const c of [BG,TR,TP]){ c.width=W*dpr; c.height=Hh*dpr; c.getContext('2d').setTransform(dpr,0,0,dpr,0,0); } dirty=true; }
addEventListener('resize', resize);
function med(a){ const s=[...a].sort((x,y)=>x-y); return s[s.length>>1]; }
function drawBg(){ const c=bgc; c.clearRect(0,0,W,Hh); if(!A) return; const h=A.houses;
  c.font='10.5px sans-serif'; c.lineWidth=1;
  for(const T of [-50,-20,0,10,15,18,20,21,22,24,30]){ const x=X(T); c.strokeStyle=T===21?'#24402f':'#1a1f29'; c.beginPath(); c.moveTo(x,pad.t); c.lineTo(x,Hh-pad.b); c.stroke(); c.fillStyle='#5d6576'; c.textAlign='center'; c.fillText(T+'°',x,Hh-pad.b+14); }
  for(let r=-3;r<=2;r++){ const y=Y(r); c.strokeStyle=r===0?'#39414f':'#1a1f29'; c.beginPath(); c.moveTo(pad.l,y); c.lineTo(W-pad.r,y); c.stroke(); c.fillStyle='#5d6576'; c.textAlign='right'; c.fillText((r>0?'+':'')+r,pad.l-6,y+3); }
  c.fillStyle='#5d6576'; c.textAlign='left'; c.fillText('°C per hour',4,pad.t-4); c.textAlign='right'; c.fillText('indoor °C (stretched around the 21° target)',W-pad.r,Hh-6);
  c.strokeStyle='rgba(226,87,77,.45)'; c.setLineDash([4,5]); c.beginPath(); c.moveTo(X(0),pad.t); c.lineTo(X(0),Hh-pad.b); c.stroke(); c.setLineDash([]); c.fillStyle='rgba(226,87,77,.7)'; c.textAlign='left'; c.fillText('pipes freeze below 0°',X(0)+5,pad.t+12);
  if(opt.curves){ const eqOn=med(h.eq_on), eqOff=med(h.eq_off), tau=med(h.tau), t0=A.t_out;
    const curve=(eq,col,lab)=>{ c.strokeStyle=col; c.lineWidth=1.5; c.beginPath(); let first=true, lx=0, ly=0; for(let T=TMIN;T<=TMAX;T+=0.25){ const r=(eq-T)/tau; const x=X(T), y=Y(r); if(r>RMAX||r<RMIN){ first=true; continue; } first?c.moveTo(x,y):c.lineTo(x,y); first=false; lx=x; ly=y; } c.stroke(); c.lineWidth=1; };
    curve(eqOn,'rgba(255,122,48,.45)'); curve(eqOff,'rgba(79,209,197,.35)'); curve(t0+1,'rgba(226,87,77,.35)');
    c.font='11px sans-serif'; c.textAlign='left'; c.fillStyle='rgba(255,122,48,.8)'; c.fillText('heater on',X(-35),Y((eqOn+35)/tau)-6); c.fillStyle='rgba(79,209,197,.75)'; c.fillText('heater off',X(26),Y((eqOff-26)/tau)+14); c.fillStyle='rgba(226,87,77,.75)'; c.fillText('no power',X(-10),Y((t0+1+10)/tau)+14); }
  dirty=false; }
let dust=[];
function seedDust(n){ dust=[]; for(let i=0;i<n;i++) dust.push(spawn({})); }
function spawn(p){ p.j=(Math.random()*(A?.houses.t.length||300))|0; p.T=TMIN+Math.random()*(TMAX-TMIN); p.on=Math.random()<.5; p.age=0; p.life=200+Math.random()*500; p.x=null;
  if(A){ const h=A.houses, j=p.j; if(h.eq_on[j]<h.target[j]) p.on=true; p.r=((p.on?h.eq_on[j]:h.eq_off[j])-p.T)/h.tau[j]; } else p.r=0; return p; }
function stepDust(){ if(!A||A.paused) return; const h=A.houses, dt=0.07; const c=trc;
  c.globalCompositeOperation='source-over'; c.fillStyle='rgba(15,17,21,0.085)'; c.fillRect(0,0,W,Hh); c.globalCompositeOperation='lighter';
  if(!opt.dust){c.globalCompositeOperation='source-over';return;}
  for(const p of dust){ const j=p.j, tg=h.target[j], eqOn=h.eq_on[j], eqOff=h.eq_off[j], tau=h.tau[j];
    if(p.T<tg-0.5) p.on=true; else if(p.T>tg+0.5) p.on=false; if(eqOn<tg) p.on=true;
    const want=((p.on?eqOn:eqOff)-p.T)/tau; const eq=p.on?eqOn:eqOff;p.T=eq+(p.T-eq)*Math.exp(-dt/tau);p.r=(eq-p.T)/tau; p.age++;
    const x=X(p.T), y=Y(p.r); if(p.x!==null){ const a=Math.min(1,p.age/40)*Math.min(1,(p.life-p.age)/60)*0.55; c.strokeStyle=DUST[h.basin[j]]+a+')'; c.beginPath(); c.moveTo(p.x,p.y); c.lineTo(x,y); c.stroke(); }
    p.x=x; p.y=y; if(p.age>p.life) spawn(p); }
  c.globalCompositeOperation='source-over'; }
let hp=[], hover=-1, pulse=0;
function drawTop(){ const c=tpc; c.clearRect(0,0,W,Hh); if(!A) return; const h=A.houses; pulse+=0.03;
  const glow=(x,y,col,r0)=>{ for(let k=3;k>=1;k--){ c.beginPath(); c.arc(x,y,r0*k*(1+0.12*Math.sin(pulse*2)),0,7); c.fillStyle=col.replace('1)',(0.07*(4-k))+')'); c.fill(); } };
  const tg=med(h.target); glow(X(tg),Y(0),'rgba(94,192,122,1)',14); c.strokeStyle='#5ec07a'; c.lineWidth=1.5; c.beginPath(); c.arc(X(tg),Y(0),6,0,7); c.stroke();
  c.fillStyle='#5ec07a'; c.font='600 11.5px sans-serif'; c.textAlign='center'; c.textAlign='left'; c.fillText('comfort attractor '+tg+'°',X(tg)+62,Y(0)+4); c.textAlign='center';
  glow(X(A.t_out+1),Y(0),'rgba(226,87,77,1)',14); c.strokeStyle='#e2574d'; c.beginPath(); c.arc(X(A.t_out+1),Y(0),6,0,7); c.stroke(); c.fillStyle='#e2574d'; c.textAlign='left'; c.fillText('freeze attractor '+Math.round(A.t_out)+'°',Math.max(4,X(A.t_out+1)-20),Y(0)+30);
  c.lineWidth=1;
  if(!opt.houses) return;
  for(let i=0;i<h.t.length;i++){ const tx=X(h.t[i]), ty=Y(h.rate[i]); if(!hp[i]) hp[i]={x:tx,y:ty}; const q=hp[i]; q.x+=(tx-q.x)*0.12; q.y+=(ty-q.y)*0.12;
    const col=phaseColor(i); c.beginPath(); c.arc(q.x,q.y,i===hover?6:3.2,0,7); c.fillStyle=col; c.globalAlpha=0.95; c.fill(); c.globalAlpha=0.18; c.beginPath(); c.arc(q.x,q.y,8,0,7); c.fill(); c.globalAlpha=1; }
  if(hover>=0){ const q=hp[hover]; c.strokeStyle='#fff'; c.beginPath(); c.arc(q.x,q.y,7,0,7); c.stroke(); } }
const BASIN=['warm: settles at its target','target cannot be maintained at the current heat gains','freezing: no heat to hold it above 0°','pipes burst, waiting for the plumber'];
TP.addEventListener('pointermove', ev=>{ if(!A||!opt.houses||phaseDrag) return; const r=TP.getBoundingClientRect(), mx=ev.clientX-r.left, my=ev.clientY-r.top; let best=-1, bd=10;
  hp.forEach((q,i)=>{ const d=Math.hypot(q.x-mx,q.y-my); if(d<bd){ bd=d; best=i; } }); hover=best; TP.style.cursor=best>=0?'pointer':'default';
  if(best<0){ tip.style.display='none'; return; } const h=A.houses, i=best;
  tip.innerHTML=`<b>House ${i+1}</b>, sector ${h.sector[i]+1}<br>${h.t[i].toFixed(1)}° now, ${h.rate[i]>0?'+':''}${h.rate[i].toFixed(2)}°/h<br>water <b>${h.pressure_kpa[i]} kPa</b>, ${h.water_l_min[i]} L/min<br>conditional equilibrium <b>${h.att[i]}°</b> (heater on ${h.eq_on[i]}°, off ${h.eq_off[i]}°, time constant ${h.tau[i]} h)<br><span style="color:${COL[h.basin[i]]}">${BASIN[h.basin[i]]}</span>${h.ttf[i]>0?`<br>reaches 0° in <b>${h.ttf[i]} h</b>`:''}`;
  tip.style.display='block'; tip.style.left=Math.min(mx+14,W-310)+'px'; tip.style.top=(my+14)+'px'; });
TP.addEventListener('pointerleave',()=>{ hover=-1; tip.style.display='none'; });
TP.addEventListener('click',()=>{ if(!phaseMoved&&hover>=0) window.open('/house?id='+(hover+1),'_blank'); });
function panel(id){ const cv=$(id), r=cv.getBoundingClientRect(); const d=devicePixelRatio||1; if(cv.width!==Math.round(r.width*d)||cv.height!==Math.round(r.height*d)){ cv.width=Math.round(r.width*d); cv.height=Math.round(r.height*d); } const c=cv.getContext('2d'); c.setTransform(d,0,0,d,0,0); c.clearRect(0,0,r.width,r.height); return [c,r.width,r.height]; }
function frame(c,w,h,xr,yr,xl,yl){ const P={l:34,r:8,t:8,b:16}; const sx=v=>P.l+(v-xr[0])/(xr[1]-xr[0])*(w-P.l-P.r), sy=v=>P.t+(yr[1]-v)/(yr[1]-yr[0])*(h-P.t-P.b);
  c.strokeStyle='#222834'; c.lineWidth=1; c.strokeRect(P.l,P.t,w-P.l-P.r,h-P.t-P.b); c.fillStyle='#5d6576'; c.font='10px sans-serif'; c.textAlign='right';
  c.fillText(yl(yr[1]),P.l-4,P.t+8); c.fillText(yl(yr[0]),P.l-4,h-P.b); c.textAlign='left'; c.fillText(xl(xr[0]),P.l,h-3); c.textAlign='right'; c.fillText(xl(xr[1]),w-P.r,h-3);
  if(yr[0]<0&&yr[1]>0){ c.strokeStyle='#343b49'; c.beginPath(); c.moveTo(P.l,sy(0)); c.lineTo(w-P.r,sy(0)); c.stroke(); } return [sx,sy]; }
function comet(c,pts,sx,sy,col){ if(pts.length<2) return; for(let k=1;k<pts.length;k++){ const a=k/pts.length; c.strokeStyle=col.replace('A',(0.08+0.8*a*a).toFixed(3)); c.lineWidth=0.6+1.6*a; c.beginPath(); c.moveTo(sx(pts[k-1][0]),sy(pts[k-1][1])); c.lineTo(sx(pts[k][0]),sy(pts[k][1])); c.stroke(); }
  const [x,y]=pts[pts.length-1]; c.fillStyle=col.replace('A','0.25'); c.beginPath(); c.arc(sx(x),sy(y),7+2*Math.sin(pulse*3),0,7); c.fill(); c.fillStyle=col.replace('A','1'); c.beginPath(); c.arc(sx(x),sy(y),3,0,7); c.fill(); c.lineWidth=1; }
function ring(c,x,y,col,lab){ c.strokeStyle=col; c.lineWidth=1.5; c.beginPath(); c.arc(x,y,6,0,7); c.stroke(); c.lineWidth=1; if(lab){ c.fillStyle=col; c.font='10px sans-serif'; c.textAlign='center'; c.fillText(lab,x,y-10); } }
function zone(c,sx,sy,x0,x1,y0,y1,col){ c.fillStyle=col; c.fillRect(sx(x0),sy(y1),sx(x1)-sx(x0),sy(y0)-sy(y1)); }
function setPill(id,v){ const e=$(id); e.className='pill '+v[0]; e.textContent={ok:'attractor',warn:'drifting',bad:'collapse basin'}[v[0]]; }
function col(k){ return H && H.fast_keys ? H.fast_keys.indexOf(k) : -1; }
function drawPanels(){ if(!A) return; const F=(H&&H.fast)||[], S=(H&&H.slow)||[];
  { const [c,w,h]=panel('cw'); const wa=A.water, iT=col('tank'), iI=col('water_in'), iU=col('water_use'); const pts=F.map(r=>[r[iT], r[iI]-r[iU]]); const m=Math.max(3,...pts.map(p=>Math.abs(p[1])))*1.2;
    const xsw=pts.map(p=>p[0]).concat([wa.v_star, wa.tank]); const wx0=Math.max(0,Math.min(...xsw)-15), wx1=Math.min(wa.cap,Math.max(...xsw)+8);
    const [sx,sy]=frame(c,w,h,[wx0,wx1],[-m,m],v=>Math.round(v)+'',v=>v.toFixed(0));
    c.strokeStyle='rgba(90,169,255,.35)'; c.beginPath(); for(let v=wx0;v<=wx1;v+=(wx1-wx0)/120){ const inflow=wa.plant_ok?Math.min(wa.max_m3_h*Math.max(.15,Math.min(1,(wa.cap-v)/60)),Math.max(0,(wa.cap-v)*60)):0; const y=sy(Math.max(-m,Math.min(m,inflow-wa.use))); v>wx0?c.lineTo(sx(v),y):c.moveTo(sx(v),y); } c.stroke();
    comet(c,pts,sx,sy,'rgba(90,169,255,A)'); if(wa.v_star>0) ring(c,sx(wa.v_star),sy(0),'#5ec07a','settles '+Math.round(wa.v_star)); else ring(c,sx(0),sy(0),'#e2574d','empty');
    setPill('pw',wa.verdict); $('vw').textContent=wa.verdict[1]; }
  { const [c,w,h]=panel('cp'); const iA=col('avail_kw'), iD=col('demand_kw'), iU=col('ups'); const pts=F.map(r=>[r[iA]-r[iD], r[iU]*100]); const m=Math.max(500,...pts.map(p=>Math.abs(p[0])))*1.15;
    const [sx,sy]=frame(c,w,h,[-m,m],[0,105],v=>Math.round(v)+'',v=>Math.round(v)+'%');
    zone(c,sx,sy,0,m,90,105,'rgba(94,192,122,.10)'); zone(c,sx,sy,-m,0,0,20,'rgba(226,87,77,.12)'); c.fillStyle='rgba(94,192,122,.7)'; c.font='10px sans-serif'; c.textAlign='right'; c.fillText('healthy',sx(m)-4,sy(95)); c.fillStyle='rgba(226,87,77,.7)'; c.textAlign='left'; c.fillText('blackout',sx(-m)+4,sy(8));
    comet(c,pts,sx,sy,'rgba(242,193,78,A)'); setPill('pp',A.power.verdict); $('vp').textContent=A.power.verdict[1]; }
  { const [c,w,h]=panel('cr'); const iO=col('open'), iB=col('burst'); const pts=F.map(r=>[r[iO], r[iB]]); const mx=Math.max(8,...pts.map(p=>p[0]))*1.15, my=Math.max(5,...pts.map(p=>p[1]))*1.15;
    const [sx,sy]=frame(c,w,h,[0,mx],[0,my],v=>Math.round(v)+'',v=>Math.round(v)+'');
    const rho=A.repairs.rho; if(rho<1){ const L=rho/(1-rho); ring(c,sx(Math.min(mx,L)),sy(0),'#5ec07a','queue settles'); }
    comet(c,pts,sx,sy,'rgba(180,142,173,A)'); setPill('pr',A.repairs.verdict); $('vr').textContent=`${A.repairs.verdict[1]} (${A.repairs.lam} new a day, crews close about ${A.repairs.mu})`; }
  { const [c,w,h]=panel('cm'); const pts=[], G=r=>r.length>3?r[3]:r[1]; for(let k=4;k<S.length;k++){ pts.push([S[k][1]/1000, (G(S[k])-G(S[k-4]))/1000]); } const mo=A.money;
    const xs=pts.map(p=>p[0]).concat([mo.colony/1000, mo.target/1000].concat(mo.colony<30000?[0]:[])), ys=pts.map(p=>Math.abs(p[1])).concat([2]); const x0=Math.min(...xs)-10, x1=Math.max(...xs)+10, m=Math.max(...ys)*1.15;
    const [sx,sy]=frame(c,w,h,[x0,x1],[-m,m],v=>Math.round(v)+'k',v=>v.toFixed(0));
    if(x0<0) zone(c,sx,sy,x0,0,-m,m,'rgba(226,87,77,.12)'); c.strokeStyle='rgba(94,192,122,.35)'; c.setLineDash([3,4]); c.beginPath(); c.moveTo(sx(mo.target/1000),sy(m)); c.lineTo(sx(mo.target/1000),sy(-m)); c.stroke(); c.setLineDash([]);
    comet(c,pts,sx,sy,'rgba(94,192,122,A)'); if(mo.b_star) ring(c,sx(mo.b_star/1000),sy(0),'#5ec07a','settles '+Math.round(mo.b_star/1000)+'k');
    setPill('pm',mo.verdict); $('vm').textContent=mo.verdict[1]+(mo.last_levy?`, last levy ${Math.round(mo.last_levy/1000)}k`:''); } }
function counts(){ const h=A.houses, k=h.counts; $('counts').innerHTML=`<span class="ok">${k[0]} warm</span>, <span class="warn">${k[1]} cool</span>, <span class="bad">${k[2]} freezing</span>, ${k[3]} burst${h.first_freeze_h>0?`; first pipes freeze in <b class="bad">${h.first_freeze_h} h</b>`:''}. Outside ${A.t_out}°, wind ${A.wind} m/s.`; $('navtime').textContent=A.time; }
// The original thermal phase portrait remains the default. The 3D view plots
// measured state dimensions, rather than adding an unrelated chaotic oscillator.
const BASIN_KEY=$('phase-colour-key').innerHTML;
let phaseView='thermal',phaseColour='basin',phaseYaw=-.65,phasePitch=.35,phaseDrag=null,phaseMoved=false,phaseSamples=[],phaseLastTick=-1;
const SECTOR_COL=['#72c6ba','#b3bd80','#e0ad72','#b394c7','#7aaee2','#cc929b'];
function phaseColor(i){const h=A.houses;if(phaseColour==='sector')return SECTOR_COL[h.sector[i]%6];if(phaseColour==='pressure'){const t=Math.max(0,Math.min(1,h.pressure_kpa[i]/600));return `hsl(${12+t*173},65%,${56+t*8}%)`;}return COL[h.basin[i]];}
function phasePoint(T,rate,pressure){const x=(T-10)/35,y=rate/2.4,z=pressure/300-1;
 const xx=x*Math.cos(phaseYaw)-z*Math.sin(phaseYaw),zz=x*Math.sin(phaseYaw)+z*Math.cos(phaseYaw),yy=y*Math.cos(phasePitch)-zz*Math.sin(phasePitch),depth=y*Math.sin(phasePitch)+zz*Math.cos(phasePitch);
 const scale=Math.min(W*.23,Hh*.28),perspective=3.8/(3.8+depth*.28);return{x:W*.5+xx*scale*perspective,y:Hh*.47-yy*scale*perspective,depth};}
function setPhaseView(name){phaseView=name;phaseMoved=false;dirty=true;hp=[];hover=-1;tip.style.display='none';trc.clearRect(0,0,W,Hh);bgc.clearRect(0,0,W,Hh);document.querySelectorAll('[data-phase]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.phase===name)));$('oDust').disabled=name==='coupled';$('oCurves').disabled=name==='coupled';$('phase-help').textContent=name==='thermal'?'Thermal phase portrait · click a house to open its details':'Temperature × thermal rate × pressure · drag to rotate · click a house to inspect';}
document.querySelectorAll('[data-phase]').forEach(b=>b.onclick=()=>setPhaseView(b.dataset.phase));
$('phase-colour').onchange=e=>{phaseColour=e.target.value;dirty=true;$('phase-colour-key').innerHTML=phaseColour==='pressure'?'Colour: red 0 kPa → cyan 600 kPa':phaseColour==='sector'?SECTOR_COL.map((c,i)=>`<span style="color:${c}">● District ${i+1}</span>`).join(' · '):BASIN_KEY;};
function capturePhase(d){if(d.t===phaseLastTick)return;if(d.t<phaseLastTick)phaseSamples=[];phaseLastTick=d.t;phaseSamples.push({t:d.t,T:d.houses.t,R:d.houses.rate,P:d.houses.pressure_kpa});if(phaseSamples.length>90)phaseSamples.shift();}
function drawCoupled(){const c=tpc;c.clearRect(0,0,W,Hh);bgc.clearRect(0,0,W,Hh);if(!A)return;
 const line=(a,b,color,width=1)=>{const p=phasePoint(...a),q=phasePoint(...b);c.beginPath();c.moveTo(p.x,p.y);c.lineTo(q.x,q.y);c.strokeStyle=color;c.lineWidth=width;c.stroke();};
 for(let t=-40;t<=40;t+=20)line([t,0,0],[t,0,600],'#243637');for(let p=0;p<=600;p+=150)line([-40,0,p],[40,0,p],'#243637');
 line([-40,0,0],[40,0,0],'#b2ba86',1.5);line([-40,-2.4,0],[-40,2.4,0],'#b3a0cb',1.5);line([-40,0,0],[-40,0,600],'#73bfc4',1.5);
 c.font='11px sans-serif';c.textAlign='center';for(const [pt,label,color] of [[[43,0,0],'Temperature °C','#b2ba86'],[[-40,2.6,0],'Change °C / h','#b3a0cb'],[[-40,0,650],'Pressure kPa','#73bfc4']]){const q=phasePoint(...pt);c.fillStyle=color;c.fillText(label,q.x,q.y-8);}
 for(const T of [-40,0,40]){const q=phasePoint(T,0,0);c.fillStyle='#b2ba86';c.fillText(String(T),q.x,q.y+15);}
 for(const rate of [-2,0,2]){const q=phasePoint(-40,rate,0);c.fillStyle='#b3a0cb';c.fillText(String(rate),q.x-12,q.y);}
 for(const pressure of [0,300,600]){const p=phasePoint(-40,0,pressure);c.fillStyle='#92a7a3';c.fillText(String(pressure),p.x-10,p.y+15);}
 // Recent real trajectories for the hovered house (or six district exemplars).
 const focus=hover>=0?[hover]:Array.from({length:6},(_,k)=>k*Math.floor(A.houses.t.length/6));
 for(const i of focus)for(let k=1;k<phaseSamples.length;k++){const a=phaseSamples[k-1],b=phaseSamples[k];if(b.t-a.t>Math.max(120,A.speed*4))continue;const p=phasePoint(a.T[i],a.R[i],a.P[i]),q=phasePoint(b.T[i],b.R[i],b.P[i]);c.globalAlpha=.08+.48*k/phaseSamples.length;c.strokeStyle=phaseColor(i);c.lineWidth=i===hover?2:1;c.beginPath();c.moveTo(p.x,p.y);c.lineTo(q.x,q.y);c.stroke();}
 c.globalAlpha=1;const h=A.houses;hp=h.t.map((t,i)=>phasePoint(t,h.rate[i],h.pressure_kpa[i]));
 if(opt.houses)hp.map((p,i)=>({p,i})).sort((a,b)=>b.p.depth-a.p.depth).forEach(({p,i})=>{const color=phaseColor(i);c.fillStyle=color;c.globalAlpha=.13;c.beginPath();c.arc(p.x,p.y,i===hover?12:7,0,Math.PI*2);c.fill();c.globalAlpha=.95;c.beginPath();c.arc(p.x,p.y,i===hover?5.5:3.3,0,Math.PI*2);c.fill();if(i===hover){c.strokeStyle='#fff';c.stroke();}});c.globalAlpha=1;
 c.fillStyle='#8ca49b';c.font='10px sans-serif';c.textAlign='left';c.fillText(`${phaseSamples.length} observed samples · trails ${hover>=0?'selected house':'one house per district'}`,pad.l,54);
}
TP.addEventListener('pointerdown',e=>{if(phaseView!=='coupled')return;phaseDrag={x:e.clientX,y:e.clientY,yaw:phaseYaw,pitch:phasePitch};phaseMoved=false;TP.setPointerCapture(e.pointerId);});
TP.addEventListener('pointermove',e=>{if(!phaseDrag)return;const dx=e.clientX-phaseDrag.x,dy=e.clientY-phaseDrag.y;if(Math.hypot(dx,dy)>4)phaseMoved=true;phaseYaw=phaseDrag.yaw+dx*.006;phasePitch=Math.max(-1.1,Math.min(1.1,phaseDrag.pitch+dy*.005));tip.style.display='none';});
TP.addEventListener('pointerup',()=>{phaseDrag=null;});TP.addEventListener('pointercancel',()=>{phaseDrag=null;phaseMoved=true;});
async function poll(){ try{ const want=(pollN++%10===0); const d=await (await fetch('/attractors.json'+(want?'?hist=1':''))).json(); if(want) H=d; const first=!A; A=d;capturePhase(d);$("connection").textContent=d.paused?"Simulation paused":"Live · tick "+d.t; if(first) seedDust(2600); dirty=true; counts(); }catch(e){$("connection").textContent="Connection lost · retrying";} setTimeout(poll,1000); }
let fr=0,lastFrame=0;function loop(now=0){requestAnimationFrame(loop);if(now-lastFrame<33)return;lastFrame=now;if(phaseView==='thermal'){if(dirty)drawBg();stepDust();drawTop();}else drawCoupled();if(fr++%3===0)drawPanels();}
resize(); poll(); loop();
</script></body></html>
""".replace("NAVCSS", NAV_CSS).replace("NAVHTML", NAV_HTML)


# ------------------------------------------------------------------------------------
# Internet
# ------------------------------------------------------------------------------------

def internet_step(w: World):
    c = w.cfg
    S = w.S
    center_ok = w.comms_ok and w.comms_powered
    w.mobile_online = bool(center_ok and w.tower_ok and w.tower_line_ok)
    w.uplink_ok = bool(center_ok and w.dish_ok and w.tower_line_ok and w.trunk_ok and w.substation_ok)
    for s in range(S):
        if w.sector_online[s] and w.rp_ok[s]:
            w.cabinet_ups_h[s] = min(2.0, w.cabinet_ups_h[s] + 1 / 240)
            powered = True
        else:
            w.cabinet_ups_h[s] = max(0.0, w.cabinet_ups_h[s] - 1 / 60)
            powered = w.cabinet_ups_h[s] > 0
        w.cabinet_online[s] = bool(w.cabinet_ok[s] and powered and center_ok)
    w.net_sector_online = w.cabinet_online
    house_net = w.net_chain[w.h_pole] & w.h_terminal_ok & w.cabinet_online[w.h_sector] & w.h_power_ok
    w.h_net_online = house_net
    w.packets_per_min = int(house_net.sum()) * 2 + (12 if center_ok else 0)
    if w.t % 2 == 0:
        online = np.flatnonzero(house_net)
        if len(online):
            pick = w.rng.choice(online, size=min(4, len(online)), replace=False)
            for i in pick:
                w.packets.append({"t": w.t, "from": "house", "id": int(i), "sector": int(w.h_sector[i]),
                                  "uplink": bool(w.uplink_ok), "kind": "telemetry"})
    if w.t % 5 == 0 and center_ok:
        w.packets.append({"t": w.t, "from": "hub", "id": -1, "sector": -1, "uplink": bool(w.uplink_ok and w.r_link_ok),
                          "kind": "reactor" if w.r_link_ok else "lost"})
    w.r_link_ok = center_ok and w.trunk_ok
    w.packets = [p for p in w.packets if w.t - p["t"] < 6]


# ------------------------------------------------------------------------------------
# People: walkers between home and the hub along the streets, xenomorphs
# ------------------------------------------------------------------------------------

def walker_path_point(w: World, i, p):
    """House -> along its row street to the boundary street of the sector -> down the boundary street to the hub."""
    c = w.cfg
    h = w.w_home[i]
    a0 = float(w.h_angle[h]); r_street = float(w.h_radius[h]) - 30.0 + 5.0      # sidewalk side of the row street
    ba = float(w.h_sector[h]) * 60.0 + math.degrees(6.0 / r_street)
    arc = abs(a0 - ba) * math.pi / 180.0 * r_street
    rad = r_street - (c["hub_radius"] + 10)
    L = arc + rad
    d = p * L
    if d <= arc:
        a = a0 + (ba - a0) * (d / arc if arc > 0 else 1.0)
        rr = r_street
    else:
        a = ba
        rr = r_street - (d - arc)
    return rr * math.cos(math.radians(a)), rr * math.sin(math.radians(a))


def people_step(w: World):
    W = len(w.w_home)
    night = w.is_night()
    storm = w.storm_ticks > 0
    speed = 1.0 / 400.0
    for i in range(W):
        st = w.w_state[i]
        h = w.w_home[i]
        if st == 0:
            w.w_timer[i] -= 1
            if w.w_timer[i] <= 0 and not storm and not (night and w.rng.random() < 0.9) \
                    and not w.lockdown_ticks[w.h_sector[h]] and w.h_power_ok[h]:
                w.w_state[i] = 1
                w.w_prog[i] = 0.0
            else:
                continue
        if st == 1:
            w.w_prog[i] = min(1.0, w.w_prog[i] + speed)
            if w.w_prog[i] >= 1.0:
                w.w_state[i] = 2
                w.w_timer[i] = int(w.rng.integers(30, 240))
        elif st == 2:
            w.w_timer[i] -= 1
            if w.w_timer[i] <= 0 or storm:
                w.w_state[i] = 3
        elif st == 3:
            w.w_prog[i] = max(0.0, w.w_prog[i] - speed * 1.3)
            if w.w_prog[i] <= 0.0:
                w.w_state[i] = 0
                w.w_timer[i] = int(w.rng.integers(120, 900))
        x, y = walker_path_point(w, i, float(w.w_prog[i]))
        w.w_x[i], w.w_y[i] = x, y
    xeno_step(w)
    squad_step(w)


def move_toward(m, tx, ty, speed):
    dx, dy = tx - m["x"], ty - m["y"]
    d = math.hypot(dx, dy)
    if d <= speed:
        m["x"], m["y"] = tx, ty
        return True
    m["x"] += dx / d * speed
    m["y"] += dy / d * speed
    m["heading"] = math.atan2(dy, dx)
    return False


def street_path(w: World, sector, house):
    """Waypoints from the hub end of the sector's boundary street to a house along the streets."""
    ba = sector * 60.0 + math.degrees(6.0 / 300)
    r_street = float(w.h_radius[house]) - 30.0 + 5.0
    pts = [polar(ba, w.cfg["hub_radius"] + 12), polar(ba, r_street)]
    pts += arc_waypoints(ba, float(w.h_angle[house]), r_street, 4.0)
    return pts


def xeno_step(w: World):
    c = w.cfg
    WR = c["wall_radius"]
    alive = []
    for m in w.xeno_markers:
        st = m.get("state", "hunt")
        s = m["sector"]
        if st == "approach":
            if move_toward(m, *polar(m["angle"], WR + 4), 3.0):
                m["state"], m["timer"] = "breach", 25
        elif st == "breach":
            m["timer"] -= 1
            if m["timer"] <= 0:
                if w.wall_breach[s] is None:
                    w.wall_breach[s] = m["angle"]
                    w.open_issue("wall_breach", f"wall:{s}", s, "xenomorph", "wall", polar(m["angle"], WR), "critical")
                    w.log("ALARM", f"Xenomorphs breached the wall of sector {s + 1}")
                m["state"] = "hunt"
                hs = np.flatnonzero(w.h_sector == s)
                m["target"] = int(w.rng.choice(hs))
                m["kills"] = 0
        elif st == "hunt":
            j = m["target"]
            if move_toward(m, float(w.h_x[j]), float(w.h_y[j]), 2.6):
                m["state"], m["timer"] = "attack", 40
                if w.h_wiring_ok[j]:
                    damage_target(w, f"house:{j}", "xenomorph", 1.0)
        elif st == "attack":
            m["timer"] -= 1
            if m["timer"] <= 0:
                m["kills"] = m.get("kills", 0) + 1
                if m["kills"] < 2:
                    hs = np.flatnonzero(w.h_sector == s)
                    m["target"] = int(w.rng.choice(hs))
                    m["state"] = "hunt"
                else:
                    m["state"] = "retreat"
        elif st == "retreat":
            ang = w.wall_breach[s] if w.wall_breach[s] is not None else m["angle"]
            if move_toward(m, *polar(ang, WR + 160), 3.5):
                continue                      # gone
        elif st == "dying":
            m["timer"] -= 1
            if m["timer"] <= 0:
                continue
        if w.t > m["until"] and st in ("hunt", "attack"):
            m["state"] = "retreat"
        if m["state"] in ("breach", "hunt", "attack"):
            w.lockdown_ticks[s] = max(w.lockdown_ticks[s], 30)     # lockdown holds while they are inside
        alive.append(m)
    w.xeno_markers = alive


def squad_step(w: World):
    """Four marines from the operations center: go to the locked sector, kill what they reach, come back."""
    q = w.squad
    c = w.cfg
    if q["state"] == "BASE":
        threats = [m for m in w.xeno_markers if m.get("state") in ("hunt", "attack", "breach")]
        if threats:
            m = threats[0]
            q["sector"] = m["sector"]
            q["route"] = street_path(w, m["sector"], m.get("target", int(np.flatnonzero(w.h_sector == m["sector"])[0])))
            q["state"] = "DEPLOY"
            w.log("WARN", f"Marine squad deployed to sector {m['sector'] + 1}")
    elif q["state"] == "DEPLOY":
        if q["route"]:
            tx, ty = q["route"][0]
            if move_toward(q, tx, ty, 7.0):
                q["route"].pop(0)
        else:
            q["state"], q["timer"] = "FIGHT", 240
    elif q["state"] == "FIGHT":
        q["timer"] -= 1
        threats = [m for m in w.xeno_markers if m.get("state") in ("hunt", "attack", "breach", "approach") and m["sector"] == q["sector"]]
        if threats:
            m = min(threats, key=lambda m: math.hypot(m["x"] - q["x"], m["y"] - q["y"]))
            if move_toward(q, m["x"], m["y"], 3.5) or math.hypot(m["x"] - q["x"], m["y"] - q["y"]) < 25:
                m["state"], m["timer"] = "dying", 12
                w.log("INFO", f"Marines killed a xenomorph in sector {q['sector'] + 1}")
                if w.rng.random() < 0.25:
                    hs = np.flatnonzero(w.h_sector == q["sector"])
                    j = int(hs[np.argmin((w.h_x[hs] - q["x"]) ** 2 + (w.h_y[hs] - q["y"]) ** 2)])
                    if w.h_terminal_ok[j]:
                        damage_target(w, f"terminal:{j}", "marines", 1.0)
        elif q["timer"] <= 0 or not [m for m in w.xeno_markers if m["sector"] == q["sector"]]:
            q["route"] = list(reversed(street_path(w, q["sector"], int(np.flatnonzero(w.h_sector == q["sector"])[0]))))[:2] + [(0.0, 60.0)]
            q["state"] = "RETURN"
    elif q["state"] == "RETURN":
        if q["route"]:
            tx, ty = q["route"][0]
            if move_toward(q, tx, ty, 4.0):
                q["route"].pop(0)
        else:
            q["state"] = "BASE"


# ------------------------------------------------------------------------------------
# Roads, gates, rovers, waste, sewage
# ------------------------------------------------------------------------------------

def angle_diff(a, b):
    return (b - a + 180.0) % 360.0 - 180.0


def arc_waypoints(a0, a1, r, step=6.0):
    """Points along an arc from a0 to a1 (shortest way, unless |a1-a0| given explicitly > 180)."""
    d = a1 - a0
    n = max(1, int(abs(d) / step))
    return [polar(a0 + d * k / n, r) for k in range(1, n + 1)]


def ring_blocked(w: World, a0, a1, rover: Rover):
    """True if the ring road between a0 and a1 (in the direction of a1 - a0) crosses a broken segment."""
    if rover.kind == "repair":
        return False
    d = a1 - a0
    n = max(1, int(abs(d) / 5.0))
    for k in range(n):
        a = a0 + d * (k + 0.5) / n
        if w.road_integrity[int((a % 360.0) // 60.0)] < 20:
            return True
    return False


def ring_route(w: World, a0, a1, rover: Rover):
    """Arc along the ring road from a0 to a1, picking a direction that is not blocked. None if both are."""
    d = angle_diff(a0, a1)
    for dd in (d, d - 360.0 if d > 0 else d + 360.0):
        if not ring_blocked(w, a0, a0 + dd, rover):
            return arc_waypoints(a0, a0 + dd, w.cfg["ring_road_radius"])
    return None


def rover_polar(r: Rover):
    return math.degrees(math.atan2(r.y, r.x)) % 360.0, math.hypot(r.x, r.y)


def traffic_junctions(c):
    radii=[c['hub_radius']-22,210]+[c['house_radius_min']-30+k*c['house_ring_step'] for k in range(c['house_rows']+1)]+[c['ring_road_radius']]
    return [dict(x=polar(s*60,r)[0],y=polar(s*60,r)[1],angle=s*60,sector=s,row=k,offset=s*2+k*3)
            for s in range(c['sectors']) for k,r in enumerate(radii)]+[dict(x=x,y=y,angle=0,sector=-1,row=i,offset=i*2) for i,(x,y) in enumerate([(-53,0),(0,0),(53,0),(c['tower_junction'][0],0),(c['reactor_pos'][0]+70,0),(c['reactor_pos'][0]+70,220),(c['reactor_pos'][0]+70,620)])]


def signal_phase(t,j):
    phase=(t+j['offset'])%12
    return phase


def make_traffic(c):
    fleet=[]
    for i in range(c.get('traffic_vehicles',18)):
        radius=c['ring_road_radius'] if i%3==0 else c['house_radius_min']-30+(i%c['house_rows'])*c['house_ring_step']
        r=Rover('transit-'+str(i+1),'transit',*polar(i*137.508%360,radius),state='CIRCULATING',speed=16+i%4*2)
        r.job={'radius':radius,'direction':1 if i%2 else -1,'cargo':False};r.heading=math.radians(i*137.508%360)+(math.pi/2 if i%2 else -math.pi/2);fleet.append(r)
    for i in range(2):
        a,rr=c['cargo_depot'];r=Rover('freight-'+str(i+1),'freight',*polar(a-11+i*9,rr),state='TO_DEPOT',speed=13)
        r.job={'cargo':True,'radius':rr,'direction':1};fleet.append(r)
    return fleet


def traffic_step(w):
    for r in w.traffic:
        if r.kind=='transit':
            if not r.route:
                a=math.degrees(math.atan2(r.y,r.x));r.route=arc_waypoints(a,a+r.job['direction']*60,r.job['radius'],2)
            if math.hypot(r.x,r.y)>w.cfg['ring_road_radius']-5:
                a=math.degrees(math.atan2(r.y,r.x))%360
                nearest=int(round(a/60))%6
                if abs(angle_diff(a,nearest*60))<2 and w.gate_state[nearest]=='LOCKDOWN':r.velocity=0;continue
            rover_move(w,r)
            if r.fuel_l<15 and not r.route:r.fuel_l=120  # fuel service at a route endpoint
        elif r.state in ('TO_DEPOT','RETURN'):
            if not r.route:
                aa,rr=w.cfg['cargo_depot'];a=math.degrees(math.atan2(r.y,r.x));r.route=arc_waypoints(a,aa,rr,2)
            if rover_move(w,r):r.state='WAITING';r.velocity=0
        elif r.state=='DELIVER':
            if rover_move(w,r):r.state='UNLOADING';r.timer=8
        elif r.state=='UNLOADING':
            r.timer-=1
            if r.timer<=0:r.load=0;r.state='RETURN';w.cargo['completed']+=1
    # One rail-mounted crane serves one truck; no container teleport between vehicles.
    if w.cargo['phase']=='WAIT':
        ready=[i for i,r in enumerate(w.traffic) if r.kind=='freight' and r.state=='WAITING']
        if ready and w.cargo['loaded']<24:w.cargo.update(phase='LIFT',progress=0.0,truck=ready[0]);w.traffic[ready[0]].state='LOADING'
    else:
        w.cargo['progress']+=1/24
        if w.cargo['progress']>=1:
            r=w.traffic[w.cargo['truck']];r.load=1;r.state='DELIVER';a,rr=w.cfg['cargo_depot']
            r.route=arc_waypoints(a,420,rr,2);w.cargo['loaded']+=1;w.cargo['phase']='WAIT';w.cargo['progress']=0


def exterior_route(c, x, y):
    """West gate -> distribution junction -> paved industrial service corridor."""
    gate=(-c['wall_radius']-30,0.0)
    junction=(c['tower_junction'][0],0.0)
    spine=c['reactor_pos'][0]+70
    # Stop at each service apron, outside the building footprint.
    for key,stand in [('reactor_pos',55),('water_plant_pos',36),('mine_pos',36),('solar_pos',75),('radwaste_pos',42)]:
        px,py=c[key]
        if math.hypot(x-px,y-py)<1:
            return [gate,(spine,0.0),(spine,py),(px+stand,py)]
    tx,ty=c['tower_pos']
    if math.hypot(x-tx,y-ty)<1:
        return [gate,junction,(tx,ty+40),(tx+79,ty+40),(tx+79,ty),(tx+72,ty)]
    dx,dy=c['dish_pos']
    if math.hypot(x-dx,y-dy)<1:
        return [gate,junction,(tx,ty+40),(tx+30,ty+40),(tx+30,dy+105),(dx+88,dy+105),(dx+88,dy),(dx+72,dy)]
    if abs(y)<20 and x>=spine:
        return [gate,(x,0.0),(x,y)]
    if y < -100 and x > spine:
        return [gate,junction,(junction[0],y),(x,y)]
    if x > spine and y > 30:
        return [gate,(x,0.0),(x,y)]
    return [gate,(spine,0.0),(spine,y),(x,y)]


def plan_route(w: World, r: Rover, target):
    """Build a road route from the rover to a target, expressed as a dict:
       {"kind": "house", "i": idx} | {"kind": "bin", "s": sector} | {"kind": "outside", "x":, "y":}
       | {"kind": "hub", "s": sector} | {"kind": "ring", "a": angle}. Returns False if blocked right now."""
    c = w.cfg
    R = c["ring_road_radius"]
    a, rr = rover_polar(r)
    route = []
    # 1. get to the ring road first, along the nearest boundary street or the outside road
    if rr > R + 10:                       # outside the wall: come back along the west road
        route += list(reversed(exterior_route(c, r.x, r.y)))
        gate = 3
        if w.gate_state[gate] != "OPEN":
            return False
        route += [polar(180.0, R)]
        a = 180.0
    elif rr < R - 10:                     # inside: along the row street to the boundary street, then out
        s = int(a // 60.0)
        ba = s * 60.0
        street_r = c["house_radius_min"] - 30 + round((rr - (c["house_radius_min"] - 30)) / c["house_ring_step"]) * c["house_ring_step"]
        street_r = clamp(street_r, c["hub_radius"] + 20, R)
        if abs(rr - street_r) > 5 or rr < c["hub_radius"] + 30:
            street_r = max(street_r, c["hub_radius"] + 30)
        route += arc_waypoints(a, ba, street_r, 4.0)
        route += [polar(ba, R)]
        a = ba
    kind = target["kind"]
    if kind == "ring":
        arc = ring_route(w, a, target["a"], r)
        if arc is None:
            return False
        route += arc
    elif kind == "bin":
        arc = ring_route(w, a, target["s"] * 60.0 + 30.0, r)
        if arc is None:
            return False
        route += arc + [polar(target["s"] * 60.0 + 30.0, R + 22)]
    elif kind == "house":
        i = target["i"]
        s = int(w.h_sector[i])
        ba = s * 60.0
        arc = ring_route(w, a, ba, r)
        if arc is None:
            return False
        street_r = float(w.h_radius[i]) - 30.0
        route += arc + [polar(ba, street_r)] + arc_waypoints(ba, float(w.h_angle[i]), street_r, 4.0)
    elif kind == "hub":
        ba = target["s"] * 60.0
        arc = ring_route(w, a, ba, r)
        if arc is None:
            return False
        route += arc + [polar(ba, c["hub_radius"] + 30)]
    elif kind == "garage":
        ga, gr = c["garage"]
        ba = 60.0
        arc = ring_route(w, a, ba, r)
        if arc is None:
            return False
        route += arc + [polar(ba, gr)] + arc_waypoints(ba, ga, gr, 4.0)
    elif kind == "outside":
        arc = ring_route(w, a, 180.0, r)
        if arc is None:
            return False
        if w.gate_state[3] != "OPEN":
            return False
        route += arc + exterior_route(c, target["x"], target["y"])
    r.route = route
    return True


def rover_move(w: World, r: Rover):
    """Advance along the planned route. Returns True when the route is finished."""
    if r.wait > 0:
        r.wait -= 1
        r.velocity=0.0
        return False
    if not r.route:
        r.velocity=0.0
        gx,gy=polar(*w.cfg['garage'])
        if math.hypot(r.x-gx,r.y-gy)<40:r.fuel_l=min(120,getattr(r,'fuel_l',120)+20)
        return True
    tx,ty=r.route[0]
    dx,dy=tx-r.x,ty-r.y
    d=math.hypot(dx,dy)
    grade=abs(site_elevation(tx,ty,w.cfg)-site_elevation(r.x,r.y,w.cfg))/max(d,1)
    target_speed=r.speed*(.5 if w.road_icy and not w.road_heating_on else 1)/(1+grade*5)
    # Brake for the next bend and give moving vehicles a following gap.
    if len(r.route)>1 and d<18:
        nx,ny=r.route[1][0]-tx,r.route[1][1]-ty
        turn=abs(math.atan2(math.sin(math.atan2(ny,nx)-math.atan2(dy,dx)),math.cos(math.atan2(ny,nx)-math.atan2(dy,dx))))
        target_speed*=max(.3,1-turn/math.pi)
    for other in w.rovers+getattr(w,'traffic',[]):
        if other is r or (other.state=='IDLE' and not other.route):continue
        ox,oy=other.x-r.x,other.y-r.y
        ahead=(ox*dx+oy*dy)/max(d,1e-6)
        side=abs(ox*dy-oy*dx)/max(d,1e-6)
        gap=18 if r.kind=='freight' or other.kind=='freight' else 6
        if 0<ahead<gap+5 and side<3 and math.cos(other.heading-math.atan2(dy,dx))>.7:
            target_speed=min(target_speed,max(0,ahead-gap))
    r.velocity=min(target_speed,getattr(r,'velocity',0)+2.5)
    r.fuel_l=getattr(r,'fuel_l',120.0)
    if r.fuel_l<=0:r.velocity=0
    budget=r.velocity
    # Synchronized ring-road signals. Keep a 12 m stop line clear of the junction.
    for junction in traffic_junctions(w.cfg):
        ox,oy=junction['x']-r.x,junction['y']-r.y
        ahead=(ox*dx+oy*dy)/max(d,1e-6);lateral=abs(ox*dy-oy*dx)/max(d,1e-6)
        angle=math.radians(junction['angle']);phase=signal_phase(w.t,junction)
        radial=abs((dx*math.cos(angle)+dy*math.sin(angle))/max(d,1e-6))>.7
        green=phase<5 if radial else 6<=phase<11
        if not green and 11.9<=ahead<35 and lateral<4:
            budget=min(budget,max(0,ahead-12));r.velocity=budget
    travelled=0.0
    while budget>1e-9 and r.route:
        tx,ty=r.route[0];dx,dy=tx-r.x,ty-r.y;d=math.hypot(dx,dy)
        if d>1e-8:r.heading=math.atan2(dy,dx)
        step=min(d,budget)
        if d<=budget:r.x,r.y=tx,ty;r.route.pop(0)
        else:r.x+=dx/d*step;r.y+=dy/d*step
        budget-=step;travelled+=step
    r.odometer_m=getattr(r,'odometer_m',0)+travelled
    r.fuel_l=max(0,r.fuel_l-travelled*.00045*(1+grade*6))
    if not r.route:
        r.velocity=0
        gx,gy=polar(*w.cfg['garage'])
        if math.hypot(r.x-gx,r.y-gy)<40:r.fuel_l=120.0
    return not r.route


def roads_step(w: World):
    c = w.cfg
    S = w.S
    wear = 0.0004 + (0.001 if w.road_icy and not w.road_heating_on else 0.0)
    w.road_integrity = np.maximum(0.0, w.road_integrity - wear)
    for s in range(S):
        if w.road_integrity[s] < 20:
            w.open_issue("road_blocked", f"road:{s}", s, "wear", "road", polar(s * 60 + 30, c["ring_road_radius"]))
    # gates: gate g sits at boundary g*60; sector s locks gates s and s+1
    for s in range(S):
        if w.lockdown_ticks[s] > 0:
            w.lockdown_ticks[s] -= 1
            if w.lockdown_ticks[s] == 0:
                w.log("INFO", f"Sector {s + 1} lockdown lifted")
    for g in range(S):
        locked = w.lockdown_ticks[g] > 0 or w.lockdown_ticks[(g - 1) % S] > 0
        if locked:
            w.gate_state[g] = "LOCKDOWN"
        elif not w.gate_ok[g]:
            w.gate_state[g] = "CLOSED"
        elif not (w.sector_online[g] or w.ups_state[g] not in ("DEPLETED", "FAULT")):
            pass  # unpowered: keeps its last state
        else:
            w.gate_state[g] = "OPEN"
        want = 1.0 if w.gate_state[g] == "OPEN" else 0.0
        w.gate_open_frac[g] += clamp(want - w.gate_open_frac[g], -0.25, 0.25)
    residents = np.bincount(w.h_sector, weights=w.h_residents, minlength=S)
    w.waste_level = np.minimum(1.2, w.waste_level + residents * c["waste_per_resident_per_tick"])
    overflow = w.waste_level >= 1.0
    sewage_bad = (~w.h_aeration_ok) | (w.h_sludge >= 1.0)
    sew_bad_frac = np.bincount(w.h_sector, weights=sewage_bad.astype(float), minlength=S) / c["houses_per_sector"]
    w.sanitary = np.clip(w.sanitary - overflow * 0.05 - sew_bad_frac * 0.1 + (~overflow) * 0.02, 0, 100)
    garbage, sludge = w.rovers[0], w.rovers[1]
    _garbage_rover(w, garbage)
    _sludge_rover(w, sludge)
    for r in w.rovers[2:]:
        _repair_rover(w, r)
    traffic_step(w)


def _go_home(w: World, r: Rover):
    """Idle rovers park at the vehicle bay instead of standing in the street."""
    ga, gr = w.cfg["garage"]
    gx, gy = polar(ga, gr)
    if math.hypot(r.x - gx, r.y - gy) > 40 and r.wait <= 0:
        if plan_route(w, r, {"kind": "garage"}):
            r.state = "TO_GARAGE"
        else:
            r.wait = 30


def _garbage_rover(w: World, r: Rover):
    c = w.cfg
    if r.state == "TO_GARAGE":
        if rover_move(w, r):
            r.state = "IDLE"
        return
    if r.state == "IDLE":
        need = np.flatnonzero(w.waste_level >= 0.9)
        if not len(need):
            _go_home(w, r)
        if len(need):
            s = int(need[np.argmax(w.waste_level[need])])
            if plan_route(w, r, {"kind": "bin", "s": s}):
                r.job = s
                r.state = "TO_BIN"
            else:
                r.wait = 20
    elif r.state == "TO_BIN":
        if rover_move(w, r):
            r.state = "LOADING"
            r.timer = 10
    elif r.state == "LOADING":
        r.timer -= 1
        if r.timer <= 0:
            s = r.job
            take = min(1.0 - r.load, float(w.waste_level[s]))
            w.waste_level[s] -= take
            r.load += take
            if finance_pay(w, "waste_trip", s, "normal_operation", f"waste collection sector {s + 1}"):
                w.log("INFO", f"Garbage rover emptied sector {s + 1} bin")
            else:
                w.log("WARN", f"Sector {s + 1} could not pay for waste collection")
            if r.load >= 0.99 or not np.any(w.waste_level >= 0.9):
                if plan_route(w, r, {"kind": "outside", "x": c["waste_station_pos"][0] + 40, "y": 20.0}):
                    r.state = "TO_STATION"
                else:
                    r.state = "WAIT_GATE"
                    r.wait = 30
            else:
                r.state = "IDLE"
    elif r.state == "WAIT_GATE":
        if plan_route(w, r, {"kind": "outside", "x": c["waste_station_pos"][0] + 40, "y": 20.0}):
            r.state = "TO_STATION"
        else:
            r.wait = 30
    elif r.state == "TO_STATION":
        if rover_move(w, r):
            r.state = "UNLOADING"
            r.timer = 15
    elif r.state == "UNLOADING":
        r.timer -= 1
        if r.timer <= 0:
            w.waste_station_level += r.load
            r.load = 0.0
            if plan_route(w, r, {"kind": "ring", "a": 195.0}):
                r.state = "RETURN"
            else:
                r.wait = 30
    elif r.state == "RETURN":
        if rover_move(w, r):
            r.state = "IDLE"


def _sludge_rover(w: World, r: Rover):
    c = w.cfg
    if r.state == "TO_GARAGE":
        if rover_move(w, r):
            r.state = "IDLE"
        return
    if r.state == "IDLE":
        full = np.flatnonzero(w.h_sludge >= 0.95)
        if not len(full) and r.load <= 0.5:
            _go_home(w, r)
        if len(full) and r.load < 0.99:
            i = int(full[0])
            if plan_route(w, r, {"kind": "house", "i": i}):
                r.job = i
                r.state = "TO_HOUSE"
            else:
                r.wait = 20
        elif r.load > 0.5:
            s = int(np.argmin(w.sludge_store))
            if plan_route(w, r, {"kind": "bin", "s": s}):
                r.job = s
                r.state = "TO_STORE"
            else:
                r.wait = 20
    elif r.state == "TO_HOUSE":
        if rover_move(w, r):
            r.state = "PUMPING"
            r.timer = 8
    elif r.state == "PUMPING":
        r.timer -= 1
        if r.timer <= 0:
            i = r.job
            r.load = min(1.0, r.load + float(w.h_sludge[i]) * 0.25)
            w.h_sludge[i] = 0.05
            finance_pay(w, "sludge_trip", int(w.h_sector[i]), "normal_operation", f"sludge collection house {i + 1}")
            r.state = "IDLE"
    elif r.state == "TO_STORE":
        if rover_move(w, r):
            s = r.job
            w.sludge_store[s] = min(1.0, w.sludge_store[s] + r.load * 0.2)
            r.load = 0.0
            r.state = "IDLE"
    w.sludge_store = np.maximum(0.0, w.sludge_store - 0.00005)


HOUSE_TARGETS = ("house", "aeration", "terminal")
REPAIR_PRIORITY = {"reactor": 0, "trunk": 1, "substation": 1, "wall": 2, "feeder": 2, "rp": 2, "ups": 3, "pole": 3, "span": 4,
                   "cabinet": 4, "tower_line": 5, "net_span": 5, "gate": 5, "road": 5, "lamp": 6, "solar": 6}
OUTSIDE_TARGETS = ("reactor", "trunk", "solar", "water_plant", "tower", "tower_line")


def issue_target_spec(w: World, iss: Issue):
    kind, _, arg = iss.target.partition(":")
    x, y = iss.pos
    if kind in OUTSIDE_TARGETS:
        return {"kind": "outside", "x": x + 40, "y": y + 30}
    if kind in ("house", "aeration", "terminal"):
        return {"kind": "house", "i": int(arg)}
    if kind in ("pole", "span", "net_span", "lamp"):
        i = int(arg)
        # nearest house of that pole's row street, or the hub end for spine poles
        if w.p_kind[i] == 1:
            hs = np.flatnonzero(w.h_pole == i)
            j = int(hs[0]) if len(hs) else int(np.argmin((w.h_x - x) ** 2 + (w.h_y - y) ** 2))
            return {"kind": "house", "i": j}
        return {"kind": "hub", "s": int(w.p_sector[i])}
    if kind in ("cabinet", "rp", "feeder", "ups", "substation"):
        return {"kind": "hub", "s": int(iss.sector if iss.sector >= 0 else 0)}
    if kind == "gate":
        g = int(arg)
        return {"kind": "ring", "a": g * 60.0 + 1.0}
    if kind == "wall":
        s = int(arg)
        return {"kind": "ring", "a": (w.wall_breach[s] if w.wall_breach[s] is not None else s * 60.0 + 30.0)}
    if kind == "road":
        return {"kind": "ring", "a": int(arg) * 60.0 + 30.0}
    return {"kind": "ring", "a": math.degrees(math.atan2(y, x)) % 360.0}


def _crew_fits(r: Rover, iss: Issue):
    """Plumber takes house jobs; engineers take the colony network and, when free, house wiring (it is electrical,
    and a house without wiring has no heat: leaving it to the one plumber let whole rows freeze)."""
    house = iss.target.split(":")[0] in HOUSE_TARGETS
    if r.kind == "plumber":
        return house
    return (not house) or iss.kind == "house_wiring"


def _pipes_blocked(w: World, iss: Issue):
    """Fixing pipes in a house that still has no wiring is wasted: it freezes and bursts again."""
    if iss.kind != "pipes_burst":
        return 0
    return 0 if w.h_wiring_ok[int(iss.target.split(":")[1])] else 1


def _repair_rover(w: World, r: Rover):
    if r.state == "TO_GARAGE":
        if rover_move(w, r):
            r.state = "IDLE"
        return
    if r.state == "IDLE":
        cands = [i for i in w.issues if i.status == "funded" and _crew_fits(r, i)]
        if not cands:
            _go_home(w, r)
        if cands:
            cands.sort(key=lambda i: (_pipes_blocked(w, i), REPAIR_PRIORITY.get(i.target.split(":")[0], 9),
                                      i.severity != "critical", i.opened_t))
            iss = cands[0]
            if plan_route(w, r, issue_target_spec(w, iss)):
                r.job = iss
                iss.status = "in_progress"
                iss.started_t = w.t
                r.state = "TO_TARGET"
            else:
                r.wait = 20
    elif r.state == "TO_TARGET":
        if rover_move(w, r):
            r.state = "REPAIRING"
            r.timer = r.job.duration
            s = r.job.sector
            if s >= 0 and w.sector_dark[s] and w.rng.random() < 0.15:
                w.log("ALARM", f"Repair crew attacked by xenomorphs in dark sector {s + 1}, repair aborted")
                r.job.status = "funded"
                r.job = None
                r.state = "IDLE"
                r.wait = 60
                spawn_xeno(w, s)
    elif r.state == "REPAIRING":
        r.timer -= 1
        if r.timer <= 0:
            resolve_issue(w, r.job)
            r.job = None
            r.state = "IDLE"


# ------------------------------------------------------------------------------------
# Incidents, damage, repair resolution
# ------------------------------------------------------------------------------------

def damage_target(w: World, target: str, cause: str, severity: float):
    c = w.cfg
    kind, _, arg = target.partition(":")
    if kind == "span":
        i = int(arg)
        w.s_health[i] = max(0.0, w.s_health[i] - severity)
        if w.s_health[i] < 0.2:
            w.open_issue("span_broken", target, int(w.p_sector[i]), cause, "span", (float(w.p_x[i]), float(w.p_y[i])))
    elif kind == "net_span":
        i = int(arg)
        w.n_span_ok[i] = False
        w.open_issue("cable_broken", target, int(w.p_sector[i]), cause, "net_span", (float(w.p_x[i]), float(w.p_y[i])))
    elif kind == "pole":
        i = int(arg)
        if severity > 0.7:
            w.p_state[i] = 2
            w.p_lamp_ok[i] = False
            w.open_issue("pole_fallen", target, int(w.p_sector[i]), cause, "pole", (float(w.p_x[i]), float(w.p_y[i])), "critical")
        elif severity > 0.3:
            w.p_state[i] = max(w.p_state[i], 1)
            w.open_issue("pole_tilted", target, int(w.p_sector[i]), cause, "pole", (float(w.p_x[i]), float(w.p_y[i])))
    elif kind == "lamp":
        i = int(arg)
        w.p_lamp_ok[i] = False
        w.open_issue("lamp_broken", target, int(w.p_sector[i]), cause, "lamp", (float(w.p_x[i]), float(w.p_y[i])), "info")
    elif kind == "house":
        i = int(arg)
        w.h_wiring_ok[i] = False
        w.open_issue("house_wiring", target, int(w.h_sector[i]), cause, "wiring", (float(w.h_x[i]), float(w.h_y[i])))
    elif kind == "aeration":
        i = int(arg)
        w.h_aeration_ok[i] = False
        w.open_issue("aeration_failure", target, int(w.h_sector[i]), cause, "aeration", (float(w.h_x[i]), float(w.h_y[i])))
    elif kind == "terminal":
        i = int(arg)
        w.h_terminal_ok[i] = False
        w.open_issue("terminal_broken", target, int(w.h_sector[i]), cause, "terminal", (float(w.h_x[i]), float(w.h_y[i])), "info")
    elif kind == "cabinet":
        s = int(arg)
        w.cabinet_ok[s] = False
        w.open_issue("cabinet_damaged", target, s, cause, "cabinet", polar(s * 60 + 3, c["hub_radius"] + 40))
    elif kind == "gate":
        g = int(arg)
        w.gate_ok[g] = False
        w.open_issue("gate_damaged", target, g, cause, "gate", polar(g * 60, c["wall_radius"]))
    elif kind == "road":
        s = int(arg)
        w.road_integrity[s] = max(0.0, w.road_integrity[s] - severity * 100)
    elif kind == "feeder":
        s = int(arg)
        w.feeder_ok[s] = False
        w.open_issue("feeder_broken", target, s, cause, "feeder", polar(s * 60 + 3, c["hub_radius"] - 20), "critical")
    elif kind == "rp":
        s = int(arg)
        w.rp_ok[s] = False
        w.open_issue("rp_damaged", target, s, cause, "rp", polar(s * 60 + 3, c["hub_radius"] + 30), "critical")
    elif kind == "trunk":
        w.trunk_ok = False
        w.open_issue("trunk_broken", "trunk", -1, cause, "trunk", (-c["wall_radius"] - 200, 0), "critical")
    elif kind == "substation":
        w.substation_ok = False
        w.open_issue("substation_damaged", "substation", -1, cause, "substation", (0, -60), "critical")
    elif kind == "tower_line":
        w.tower_line_ok = False
        w.open_issue("tower_line_broken", "tower_line", -1, cause, "tower_line", (c["tower_junction"][0], c["tower_pos"][1] / 2), "warning")
    elif kind == "solar":
        w.solar_health = max(0.0, w.solar_health - severity)
        w.open_issue("solar_damaged", "solar", -1, cause, "solar", c["solar_pos"], "info")
    elif kind == "reactor":
        comp = arg
        if comp == "heat_exchanger":
            w.r_hx = max(0.0, w.r_hx - severity)
            w.open_issue("heat_exchanger_damage", target, -1, cause, "heat_exchanger", c["reactor_pos"], "critical")
        elif comp in ("pump_a", "pump_b"):
            setattr(w, "r_" + comp, 0.1)
            w.open_issue("pump_trip", target, -1, cause, "pump", c["reactor_pos"], "critical")
    elif kind == "ups":
        s = int(arg)
        w.ups_health[s] = 0.1
        w.open_issue("ups_damaged", target, s, cause, "ups", polar(s * 60 + 3, c["hub_radius"] + 50))


def resolve_issue(w: World, iss: Issue):
    kind, _, arg = iss.target.partition(":")
    if kind == "span":
        w.s_health[int(arg)] = 1.0
    elif kind == "net_span":
        w.n_span_ok[int(arg)] = True
    elif kind == "pole":
        i = int(arg)
        w.p_state[i] = 0
        w.p_lamp_ok[i] = True
    elif kind == "lamp":
        w.p_lamp_ok[int(arg)] = True
    elif kind == "house":
        i = int(arg)
        if iss.kind == "pipes_burst":
            w.h_burst[i] = False
            w.h_pipes_ok[i] = True
            w.h_frozen[i] = 0
        else:
            w.h_wiring_ok[i] = True
    elif kind == "aeration":
        w.h_aeration_ok[int(arg)] = True
    elif kind == "terminal":
        w.h_terminal_ok[int(arg)] = True
    elif kind == "cabinet":
        w.cabinet_ok[int(arg)] = True
    elif kind == "gate":
        w.gate_ok[int(arg)] = True
    elif kind == "wall":
        w.wall_breach[int(arg)] = None
    elif kind == "road":
        w.road_integrity[int(arg)] = 100.0
    elif kind == "feeder":
        w.feeder_ok[int(arg)] = True
    elif kind == "rp":
        w.rp_ok[int(arg)] = True
    elif kind == "trunk":
        w.trunk_ok = True
    elif kind == "substation":
        w.substation_ok = True
    elif kind == "tower_line":
        w.tower_line_ok = True
    elif kind == "solar":
        w.solar_health = 1.0
    elif kind == "reactor":
        if arg == "heat_exchanger":
            w.r_hx = 1.0
        else:
            setattr(w, "r_" + arg, 1.0)
    elif kind == "ups":
        w.ups_health[int(arg)] = 1.0
    iss.status = "resolved"
    iss.resolved_t = w.t
    finance_record(w, iss.cost, iss.payer, iss.sector, iss.cause, f"repair {iss.kind} {iss.target}")
    w.log("INFO", f"Repaired {iss.kind} at {iss.target}, {iss.cost:.0f} cr")


def spawn_xeno(w: World, s, n=None):
    """A pack appears outside the wall of the sector and heads for it."""
    n = n or int(w.rng.integers(2, 5))
    ang = s * 60 + w.rng.uniform(8, 52)
    for k in range(n):
        x, y = polar(ang + w.rng.uniform(-3, 3), w.cfg["wall_radius"] + 120 + w.rng.uniform(0, 60))
        w.xeno_markers.append({"x": x, "y": y, "until": w.t + 400, "sector": s, "state": "approach", "angle": ang,
                               "timer": 0, "target": -1, "heading": 0.0, "id": int(w.rng.integers(1, 10 ** 6))})


def incidents_step(w: World):
    c = w.cfg
    S = w.S
    rng = w.rng
    night = w.is_night()
    v = w.wind
    z = 0.35 * (v - 22.0) + 3.0 * w.s_ice + 0.03 * (-w.t_out - 40) - 10.0
    p = 1.0 / (1.0 + np.exp(-z)) * 0.02 * (36.0 / w.P)     # same colony-wide rate as with 36 spans
    p = p * np.where(w.p_state == 1, 2.0, 1.0)
    hit = rng.random(w.P) < p
    for i in np.flatnonzero(hit & (w.s_health >= 0.2)):
        damage_target(w, f"span:{i}", "weather", 1.0)
        if rng.random() < 0.5:
            damage_target(w, f"net_span:{i}", "weather", 1.0)
    pxeno = c["p_xeno"] * (3.0 if night else 1.0)
    for s in range(S):
        if rng.random() < pxeno * (2.0 if w.sector_dark[s] else 1.0):
            spawn_xeno(w, s)
            w.lockdown_ticks[s] = 240
            w.log("ALARM", f"Xenomorphs sighted outside sector {s + 1}: LOCKDOWN")
    if rng.random() < c["p_xeno"] * 0.5:
        w.nest_alert = 300
        w.marines_active = 300
        w.log("ALARM", "Xenomorph nest activity under the atmosphere processor. Marines deployed.")
    if w.nest_alert > 0:
        w.nest_alert -= 1
        w.marines_active = max(0, w.marines_active - 1)
        if rng.random() < c["p_nest_fire"] / 10:
            comp = "heat_exchanger" if rng.random() < 0.6 else ("pump_a" if rng.random() < 0.5 else "pump_b")
            damage_target(w, f"reactor:{comp}", "marines", 0.6)
            w.log("ALARM", f"Stray marine fire damaged reactor {comp}")
    if rng.random() < c["p_vandal"] * (2.0 if night else 1.0):
        s = int(rng.integers(0, S))
        roll = rng.random()
        ps = np.flatnonzero(w.p_sector == s)
        if roll < 0.4:
            damage_target(w, f"lamp:{int(rng.choice(ps))}", "vandal", 1.0)
        elif roll < 0.6:
            damage_target(w, f"gate:{s}", "vandal", 1.0)
        elif roll < 0.8:
            hs = np.flatnonzero(w.h_sector == s)
            damage_target(w, f"terminal:{int(rng.choice(hs))}", "vandal", 1.0)
        else:
            hs = np.flatnonzero(w.h_sector == s)
            damage_target(w, f"aeration:{int(rng.choice(hs))}", "vandal", 1.0)
    if rng.random() < c["p_animal"]:
        i = int(rng.integers(0, w.N))
        damage_target(w, f"house:{i}" if rng.random() < 0.5 else f"aeration:{i}", "wildlife", 1.0)
    for s in range(S):
        if w.sector_dark[s] and rng.random() < c["p_rover_hit"]:
            ps = np.flatnonzero(w.p_sector == s)
            damage_target(w, f"pole:{int(rng.choice(ps))}", "impact", 0.9)
            w.log("WARN", f"Rover hit a pole in dark sector {s + 1}")
    w.xeno_markers = [m for m in w.xeno_markers if m["until"] > w.t]
    for iss in w.issues:
        if iss.status in ("open", "unfunded") and (w.t - iss.opened_t) % 30 == 0:
            if finance_reserve(w, iss):
                iss.status = "funded"
            else:
                if iss.status == "open":
                    w.log("WARN", f"No funds for {iss.kind} at {iss.target} ({iss.cost:.0f} cr)")
                iss.status = "unfunded"


# ------------------------------------------------------------------------------------
# Finance
# ------------------------------------------------------------------------------------

def finance_reserve(w: World, iss: Issue):
    if iss.payer == "colony":
        return w.colony_budget >= iss.cost
    s = iss.sector if iss.sector >= 0 else 0
    return w.sector_budget[s] >= iss.cost or w.colony_budget >= iss.cost


def finance_record(w: World, amount, payer, sector, cause, note):
    s = sector if sector >= 0 else 0
    src = "colony"
    if payer in ("sector", "house") and w.sector_budget[s] >= amount:
        w.sector_budget[s] -= amount
        w.month_expense[s] += amount
        src = f"sector {s + 1}"
    elif w.colony_budget >= amount:
        w.colony_budget -= amount
        w.colony_month_expense += amount
    else:
        w.unfunded_total += amount
        src = "unpaid"
    if payer == "house":
        i = int(note.split("house:")[-1]) if "house:" in note else -1
        if 0 <= i < w.N:
            w.h_repairs_month[i] += amount
    w.cost_records.append({"t": w.t, "amount": amount, "payer": payer, "source": src, "cause": cause, "note": note})
    if len(w.cost_records) > 2000:
        w.cost_records = w.cost_records[-2000:]


def finance_pay(w: World, cost_key, sector, cause, note):
    cost, payer, _ = COSTS[cost_key]
    if w.sector_budget[sector] >= cost:
        finance_record(w, cost, "sector", sector, cause, note)
        return True
    if w.colony_budget >= cost:
        finance_record(w, cost, "colony", -1, cause, note)
        return True
    return False


def finance_day_close(w: World):
    c = w.cfg
    bill = w.h_meter_day * c["tariff_kwh"] + w.h_water_day * c["tariff_water_m3"]
    income = np.bincount(w.h_sector, weights=bill, minlength=w.S)
    w.sector_budget += income
    w.month_income += income
    w.h_meter_day[:] = 0
    w.h_water_day[:] = 0
    payroll = c["colony_payroll_day"]
    w.colony_budget -= payroll          # may go below zero: that is debt, and colony repairs stop being funded
    w.colony_month_expense += payroll


def finance_month_close(w: World):
    c = w.cfg
    S = w.S
    energy = w.h_meter_month * c["tariff_kwh"]
    water = w.h_water_month * c["tariff_water_m3"]
    sewage = np.full(w.N, c["sewage_fee"])
    internet = np.full(w.N, c["internet_fee"])
    repairs = w.h_repairs_month.copy()
    house_total = energy + water + sewage + internet + repairs
    income = np.bincount(w.h_sector, weights=sewage + internet + repairs, minlength=S)
    w.sector_budget += income
    w.month_income += income
    upkeep = c["reactor_upkeep_month"]
    w.colony_budget -= upkeep
    w.colony_month_expense += upkeep
    extra = np.maximum(0.0, w.sector_budget - c["sector_budget_cap"])
    w.sector_budget -= extra
    w.last_sector_transfer = float(extra.sum())
    w.colony_budget += w.last_sector_transfer
    w.colony_month_income += w.last_sector_transfer
    w.last_levy = max(0.0, w.colony_budget - c["company_reserve_target"]) * c["company_levy_frac"]
    w.colony_budget -= w.last_levy
    w.levy_total += w.last_levy
    if w.last_levy > 0:
        w.log("INFO", f"Company took {w.last_levy:.0f} cr of the surplus, sectors passed {w.last_sector_transfer:.0f} cr up")
    common_share = (w.colony_month_expense - w.colony_month_income) / w.N
    top = np.argsort(-house_total)[:5]
    w.last_report = {
        "month": w.month,
        "houses_total": float(house_total.sum()),
        "energy_total": float(energy.sum()), "water_total": float(water.sum()),
        "repairs_total": float(repairs.sum()),
        "kwh_total": float(w.h_meter_month.sum()),
        "sector_income": [round(float(x), 1) for x in income],
        "sector_expense": [round(float(x), 1) for x in w.month_expense],
        "sector_budget": [round(float(x), 1) for x in w.sector_budget],
        "colony_expense": round(w.colony_month_expense, 1),
        "colony_income": round(w.colony_month_income, 1),
        "colony_budget": round(w.colony_budget, 1),
        "common_share_per_house": round(float(common_share), 2),
        "unpaid": round(w.unfunded_total, 1),
        "levy": round(w.last_levy, 1), "sector_transfer": round(w.last_sector_transfer, 1),
        "top_houses": [{"house": int(i) + 1, "sector": int(w.h_sector[i]) + 1, "energy": round(float(energy[i]), 1),
                        "water": round(float(water[i]), 1), "repairs": round(float(repairs[i]), 1),
                        "total": round(float(house_total[i]), 1)} for i in top],
        "by_cause": _expense_by_cause(w),
    }
    w.log("INFO", f"Month {w.month} closed: owners paid {house_total.sum():.0f} cr, colony spent {w.colony_month_expense:.0f} cr")
    w.month += 1
    w.h_meter_month[:] = 0
    w.h_water_month[:] = 0
    w.h_water_m3[:] = 0
    w.h_repairs_month[:] = 0
    w.month_income[:] = 0
    w.month_expense[:] = 0
    w.colony_month_expense = 0.0
    w.colony_month_income = 0.0
    w.prog_stats = {}


def _expense_by_cause(w: World):
    out = {}
    for r in w.cost_records:
        if r["t"] > w.t - w.cfg["ticks_per_day"] * w.cfg["days_per_month"]:
            out[r["cause"]] = round(out.get(r["cause"], 0.0) + r["amount"], 1)
    return out


# ------------------------------------------------------------------------------------
# Attractors: where each subsystem is heading if nothing else happens
# ------------------------------------------------------------------------------------

def pipes_audit(w: World):
    """Reconcile: every burst house must have an open pipes_burst issue, or nobody will ever fix it."""
    for i in np.flatnonzero(w.h_burst):
        w.open_issue("pipes_burst", f"house:{i}", int(w.h_sector[i]), "freeze", "pipes",
                     (float(w.h_x[i]), float(w.h_y[i])), "critical")


def attractor_sample(w: World):
    c = w.cfg
    ups_cap = c["ups_sector_kwh"] * w.S + c["ups_center_kwh"]
    ups = (float(w.ups_kwh.sum()) + float(w.ups_center_kwh)) / ups_cap
    opened = sum(1 for i in w.issues if i.status != "resolved")
    frozen = int((~w.h_pipes_ok & ~w.h_burst).sum())
    w.attr_fast.append((w.t, round(w.water_tank_m3, 1), round(w.water_plant_m3_h, 2), round(w.water_flow_m3_h, 2),
                        round(w.available_kw), round(w.demand_kw), round(ups, 3), int(w.shedding), opened,
                        int(w.h_burst.sum()), frozen, round(w.colony_budget), round(float(w.sector_budget.sum())),
                        round(float(w.mine_frac), 2)))
    if len(w.attr_fast) > 720:
        del w.attr_fast[:len(w.attr_fast) - 720]
    if w.t % 360 == 0:
        w.attr_slow.append((w.t, round(w.colony_budget), round(float(w.sector_budget.sum())),
                            round(w.colony_budget + w.levy_total)))
        if len(w.attr_slow) > 240:
            del w.attr_slow[:len(w.attr_slow) - 240]


FAST_KEYS = ["t", "tank", "water_in", "water_use", "avail_kw", "demand_kw", "ups", "shedding", "open", "burst",
             "frozen", "colony", "sectors", "mine"]


def _houses_attractors(w: World):
    ua = w.h_ua * (1.0 + 0.006 * w.wind)
    q_now = (w.h_draw_w - w.h_heat_w) * 0.8 + w.h_residents * 80.0
    rate = (w.h_heat_w + q_now - ua * (w.h_t_in - w.t_out)) / w.h_cap * 3600.0          # C per hour, same law as houses_step
    q_int = q_now
    nonheater = np.maximum(0.0, w.h_draw_w - w.h_heat_w)
    p_on = np.where(w.h_power_ok, np.where(w.h_limit_w > 0, np.clip(w.h_limit_w - nonheater, 0, w.h_heater_w), w.h_heater_w), 0.0)
    eq_on = w.t_out + (p_on + q_int) / ua        # where the house settles with the heater always on
    eq_off = w.t_out + q_int / ua                # ... and with it always off
    tau_h = w.h_cap / ua / 3600.0                # how fast it gets there, hours
    target = w.h_target
    att = np.clip(target, eq_off, eq_on)
    basin = np.where(w.h_burst, 3, np.where(np.abs(att-target)<=1.0, 0, np.where(att >= 0.0, 1, 2)))
    with np.errstate(divide="ignore", invalid="ignore"):
        ttf = np.where((basin == 2) & (w.h_t_in > 0), tau_h * np.log((w.h_t_in - eq_on) / (0.0 - eq_on)), -1.0)
    return {
        "t": np.round(w.h_t_in, 2).tolist(), "rate": np.round(rate, 3).tolist(),
        "eq_on": np.round(eq_on, 1).tolist(), "eq_off": np.round(eq_off, 1).tolist(), "tau": np.round(tau_h, 1).tolist(),
        "target": np.round(target, 1).tolist(), "att": np.round(att, 1).tolist(), "basin": basin.tolist(),
        "ttf": np.round(np.nan_to_num(ttf, nan=-1.0), 1).tolist(), "sector": w.h_sector.tolist(),
        "pressure_kpa": np.round(w.utilities.pressure, 2).tolist(),
        "water_l_min": np.round(w.utilities.delivered * 60000 / w.cfg["tick_seconds"], 4).tolist(),
        "counts": [int((basin == k).sum()) for k in range(4)],
        "first_freeze_h": round(float(ttf[ttf > 0].min()), 1) if (ttf > 0).any() else -1,
    }


def attractor_snapshot(w: World, with_hist: bool):
    c = w.cfg
    fast = w.attr_fast
    day = [r for r in fast if r[0] > w.t - c["ticks_per_day"]] or fast[-1:]

    # water: plant throttles as the tank fills, so inflow = use has one solution
    use = sum(r[3] for r in day) / len(day) if day else w.water_flow_m3_h
    nominal, cap = c["water_plant_m3_h"], c["water_tank_m3"]
    ice=max(0,-w.t_out) if w.t_out<-2 else 0
    melt_kwh_m3=(2.1*ice+(334 if ice else 0)+4.18*5)/3.6
    vmax=min(nominal,w.water_heat_available_kw/max(melt_kwh_m3,1e-9)*c['water_recovery'])
    if not w.water_plant_ok:
        v_star = 0.0
    elif use <= 0.15 * nominal and use < vmax:
        v_star = cap
    elif use < vmax:
        v_star = cap - 60.0 * use / nominal
    else:
        v_star = 0.0
    runway_w = w.water_tank_m3 / use if use > 0 else -1
    if not w.water_plant_ok:
        wv = ("bad", f"plant down: tank drains to zero, {runway_w:.0f} h left")
    elif v_star < 0.3 * cap:
        wv = ("warn", f"use {use:.1f} m3/h is close to plant capacity, tank settles low")
    else:
        wv = ("ok", f"settles at {v_star:.0f} m3 with a daily loop; {runway_w:.0f} h of water if the plant stops")

    # power
    margin = w.available_kw - w.demand_kw
    ups_cap = c["ups_sector_kwh"] * w.S + c["ups_center_kwh"]
    ups_kwh = float(w.ups_kwh.sum()) + float(w.ups_center_kwh)
    if w.r_mode not in ("ONLINE",):
        pv = ("bad" if w.r_mode != "RUNBACK" else "warn", f"reactor {w.r_mode}: UPS {ups_kwh:.0f} kWh is the only buffer")
    elif w.shedding > 0:
        pv = ("warn", f"shedding level {w.shedding}: the grid trades comfort for balance")
    else:
        pv = ("ok", f"margin {margin:.0f} kW, UPS {100 * ups_kwh / ups_cap:.0f}% full")

    # repairs as a queue: arrivals vs what the crews can close
    t0 = w.t - c["ticks_per_day"]
    lam = sum(1 for i in w.issues if i.opened_t > t0)
    done = [i for i in w.issues if i.status == "resolved" and i.started_t >= 0][-30:]
    svc = (sum(i.resolved_t - i.started_t for i in done) / len(done)) if done else 180.0
    crews = sum(1 for r in w.rovers if r.kind in ("repair", "plumber"))
    mu = crews * c["ticks_per_day"] / (svc + 40.0)
    rho = lam / mu if mu > 0 else 9.9
    unfunded = sum(1 for i in w.issues if i.status == "unfunded")
    backlog = len(w.open_issues())
    if unfunded:
        rv = ("bad", f"{unfunded} repairs wait for money: failures pile up")
    elif rho >= 1:
        rv = ("bad", f"load {rho:.2f}: failures arrive faster than crews close them")
    elif rho > 0.7:
        rv = ("warn", f"load {rho:.2f}: queue grows as 1/(1-load)")
    else:
        rv = ("ok", f"load {rho:.2f}: backlog returns to about {rho / (1 - rho):.1f}")

    # money: the company levy pulls the budget toward a fixed point
    slow = w.attr_slow
    tgt, f = c["company_reserve_target"], c["company_levy_frac"]
    net_month = None
    if len(slow) >= 5:
        # the budget as if the company never took anything: the formula needs the flow before the levy
        old = slow[max(0, len(slow) - 121)]
        span_days = (w.t - old[0]) / c["ticks_per_day"]
        gross_old = old[3] if len(old) > 3 else old[1]
        net_month = (w.colony_budget + w.levy_total - gross_old) / max(span_days, 0.25) * c["days_per_month"]
    burn = c["colony_payroll_day"]
    runway_m = w.colony_budget / burn if w.colony_budget > 0 else 0.0
    b_star = None
    if w.colony_budget < 0:
        mv = ("bad", "in debt: colony repairs are not funded, the loop feeds itself")
    elif net_month is None:
        mv = ("ok", "collecting history")
    elif net_month <= 0:
        mv = ("warn", f"losing {-net_month:.0f} cr a month, {runway_m:.0f} days of payroll left")
    elif f <= 0:
        mv = ("warn", "no company levy: positive income has no finite budget equilibrium")
    else:
        b_star = tgt + net_month / f - net_month
        mv = ("ok", f"settles near {b_star / 1000:.0f}k cr; {runway_m:.0f} days of payroll if income stops")

    out = {
        "time": w.time_str(), "t": w.t, "t_out": round(w.t_out, 1), "wind": round(w.wind, 1),
        "paused": bool(w.paused), "speed": w.speed,
        "houses": _houses_attractors(w),
        "water": {"tank": round(w.water_tank_m3, 1), "cap": cap, "in": round(w.water_plant_m3_h, 2), "use": round(use, 2),
                  "v_star": round(v_star, 1), "runway_h": round(runway_w, 1), "verdict": wv,
                  "max_m3_h": vmax, "plant_ok": bool(w.water_plant_ok),
                  "leak_m3_h": round(float(w.utilities.leaks.sum())*3600/c["tick_seconds"],4)},
        "power": {"margin": round(margin), "ups": round(ups_kwh / ups_cap, 3), "shedding": w.shedding, "mode": w.r_mode,
                  "verdict": pv},
        "repairs": {"lam": lam, "mu": round(mu, 1), "rho": round(rho, 2), "backlog": backlog, "unfunded": unfunded,
                    "burst": int(w.h_burst.sum()), "verdict": rv},
        "money": {"colony": round(w.colony_budget), "sectors": round(float(w.sector_budget.sum())), "target": tgt,
                  "levy_frac": f, "net_month": None if net_month is None else round(net_month),
                  "b_star": None if b_star is None else round(b_star), "runway_days": round(runway_m, 1),
                  "last_levy": round(w.last_levy), "verdict": mv},
    }
    if with_hist:
        out["fast_keys"] = FAST_KEYS
        out["fast"] = fast
        out["slow"] = slow
    return out


# ------------------------------------------------------------------------------------
# Tick
# ------------------------------------------------------------------------------------

def house_events(w: World):
    """Log state transitions per house in plain words; sample temperature history every 10 minutes."""
    cur = {"power": w.h_power_ok.copy(), "ups": w.h_on_ups.copy(), "water": w.h_water_ok.copy(), "net": w.h_net_online.copy(),
           "pipes": w.h_pipes_ok.copy(), "burst": w.h_burst.copy(), "limit": (w.h_limit_w > 0).copy(), "heater": w.h_heater_on.copy(),
           "target": w.h_target.copy(), "prog": list(w.h_program), "reason": list(w.h_reason)}
    prev = w.h_prev
    if prev is not None:
        texts = {"power": ("power restored", "power lost"), "ups": ("back on the grid", "running on the sector UPS"),
                 "water": ("water supply restored", "no water"), "net": ("network link up", "network link lost"),
                 "pipes": ("pipes thawed or repaired", "pipes frozen"), "burst": ("pipes repaired", "pipes burst"),
                 "limit": ("power limit lifted", "power limit imposed by the grid")}
        for key, (up, down) in texts.items():
            changed = np.flatnonzero(cur[key] != prev[key])
            for i in changed:
                w.h_log[i].appendleft((w.t, up if cur[key][i] else down))
        ext = getattr(w, "h_ext", np.zeros(w.N, dtype=bool))
        for i in range(w.N):
            if ext[i] and (cur["reason"][i] != prev["reason"][i] or abs(cur["target"][i] - prev["target"][i]) > 0.1):
                text = f"{cur['prog'][i]}: {cur['reason'][i]} (target {cur['target'][i]:.1f} C)"
                if not w.h_log[i] or w.h_log[i][0][1] != text:
                    w.h_log[i].appendleft((w.t, text))
    w.h_prev = cur
    if w.t % 10 == 0:
        w.h_hist[:, w.h_hist_i] = w.h_t_in
        w.h_hist_draw[:, w.h_hist_i] = w.h_draw_w
        w.h_hist_i = (w.h_hist_i + 1) % w.h_hist.shape[1]


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
        return {"x": float(w.p_x[i]), "y": float(w.p_y[i]), "text": f"Span {i} broken in sector {int(w.p_sector[i]) + 1}"}
    elif cmd == "pole":
        i = int(rng.integers(0, w.P))
        damage_target(w, f"pole:{i}", "impact", 1.0)
        w.log("WARN", f"[manual] pole {i} fallen")
        return {"x": float(w.p_x[i]), "y": float(w.p_y[i]), "text": f"Pole {i} fell in sector {int(w.p_sector[i]) + 1}"}
    elif cmd == "xeno":
        s = int(rng.integers(0, w.S))
        spawn_xeno(w, s, 4)
        w.lockdown_ticks[s] = 240
        w.log("ALARM", f"[manual] xenomorph pack outside sector {s + 1}: LOCKDOWN")
        return {"sector": s, "x": polar(s * 60 + 30, w.cfg["wall_radius"] + 60)[0], "y": polar(s * 60 + 30, w.cfg["wall_radius"] + 60)[1], "text": f"Xenomorphs outside sector {s + 1}"}
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
        return {"x": c["reactor_pos"][0], "y": c["reactor_pos"][1], "text": "Reactor pump B tripped"}
    elif cmd == "marines":
        w.nest_alert = 300
        w.marines_active = 300
        damage_target(w, "reactor:heat_exchanger", "marines", 0.8)
        w.log("ALARM", "[manual] marines hit the heat exchanger")
        return {"x": c["reactor_pos"][0], "y": c["reactor_pos"][1], "text": "Stray fire hit the heat exchanger"}
    elif cmd == "scram":
        reactor_scram(w, "operator")
        return {"x": c["reactor_pos"][0], "y": c["reactor_pos"][1], "text": "Reactor SCRAM"}
    elif cmd == "money":
        w.colony_budget += 50000
        w.log("INFO", "[manual] corporation transferred 50 000 cr to the colony")
        return {"text": "50 000 cr received"}
    elif cmd == "road":
        s = int(rng.integers(0, w.S))
        damage_target(w, f"road:{s}", "impact", 1.0)
        w.log("WARN", f"[manual] road segment {s + 1} collapsed")
        return {"x": polar(s * 60 + 30, c["ring_road_radius"])[0], "y": polar(s * 60 + 30, c["ring_road_radius"])[1], "text": f"Ring road collapsed in sector {s + 1}"}
    elif cmd == "storm":
        pass
    return {"text": cmd}


# ------------------------------------------------------------------------------------
# Snapshot for the UI
# ------------------------------------------------------------------------------------

def snapshot(w: World):
    S = w.S
    c = w.cfg
    sec = []
    for s in range(S):
        m = w.h_sector == s
        sec.append({
            "id": s + 1,
            "online": bool(w.sector_online[s]),
            "demand_kw": round(float(w.sector_demand_kw[s]), 1),
            "avg_t": round(float(w.h_t_in[m].mean()), 1),
            "min_t": round(float(w.h_t_in[m].min()), 1),
            "water_ok": int(w.h_water_ok[m].sum()),
            "power_ok": int(w.h_power_ok[m].sum()),
            "net_ok": int(w.h_net_online[m].sum()),
            "water_m3_h": round(float(w.sector_water_m3[s]) * 60, 2),
            "ups": w.ups_state[s], "ups_kwh": round(float(w.ups_kwh[s]), 0),
            "budget": round(float(w.sector_budget[s]), 0),
            "waste": round(float(w.waste_level[s]), 2),
            "sludge": round(float(w.sludge_store[s]), 2),
            "sanitary": round(float(w.sanitary[s]), 0),
            "gate": w.gate_state[s], "gate_ok": bool(w.gate_ok[s]), "gate_open": round(float(w.gate_open_frac[s]), 2),
            "road": round(float(w.road_integrity[s]), 0),
            "cabinet": bool(w.cabinet_online[s]), "cabinet_ups_h": round(float(w.cabinet_ups_h[s]), 1),
            "rp_ok": bool(w.rp_ok[s]), "feeder_ok": bool(w.feeder_ok[s]),
            "dark": bool(w.sector_dark[s]),
            "lamps_on": int(w.p_lamp_on[w.p_sector == s].sum()),
            "lockdown": int(w.lockdown_ticks[s]),
        })
    issues = [{"id": i.id, "kind": i.kind, "target": i.target, "sector": i.sector + 1, "cause": i.cause,
               "cost": i.cost, "payer": i.payer, "status": i.status, "sev": i.severity,
               "x": round(i.pos[0]), "y": round(i.pos[1]), "age": w.t - i.opened_t}
              for i in w.open_issues()][-40:]
    return {
        "t": w.t, "time": w.time_str(), "paused": w.paused, "speed": w.speed,
        "finished": w.finished, "finish_reason": w.finish_reason,
        "env": {"t_out": round(w.t_out, 1), "wind": round(w.wind, 1), "precip": w.precip,
                "daylight": round(w.daylight, 3), "dust": round(w.dust, 2), "storm": w.storm_ticks > 0,
                "night": w.is_night(), "icy": w.road_icy, "visibility": w.visibility},
        "power": {"available_kw": round(w.available_kw), "demand_kw": round(w.demand_kw),
                  "deficit_kw": round(w.deficit_kw), "shedding": w.shedding, "solar_kw": round(w.solar_kw, 1),
                  "trunk": w.trunk_ok, "substation": w.substation_ok, "tower_line": w.tower_line_ok,
                  "feeder": [bool(x) for x in w.feeder_online], "mine": w.mine_powered, "mine_frac": w.mine_frac,
                  "ups_center": w.ups_center_state, "ups_center_kwh": round(w.ups_center_kwh),
                  "infra": w.infra_loads_kw, "road_heating": w.road_heating_on, "storm_lighting": w.storm_lighting,
                  "sector_kw": [round(float(x), 1) for x in w.sector_demand_kw]},
        "reactor": {"mode": w.r_mode, "power_mw": round(w.r_power_mw, 2), "setpoint_mw": round(w.r_setpoint_mw, 2),
                    "available_mw": round(w.r_available_mw, 2),
                    "core_temp": round(w.r_core_temp), "coolant_temp": round(w.r_coolant_temp), "flow": round(w.r_flow, 2),
                    "decay_mw": round(w.r_decay_mw, 2),
                    "pump_a": round(w.r_pump_a, 2), "pump_b": round(w.r_pump_b, 2), "hx": round(w.r_hx, 2),
                    "battery_h": round(w.r_battery_h, 1), "faults": w.r_faults, "link": w.r_link_ok,
                    "marines": w.marines_active > 0, "thermal_mw": round(w.r_power_mw / 0.3, 1)},
        "hydraulics": w.utilities.state(),
        "water": {"tank_m3": round(w.water_tank_m3, 1), "tank_cap": c["water_tank_m3"], "plant": w.water_plant_ok,
                  "source":"ocean", "intake_ok":w.intake_ok,"raw_m3_h":round(w.raw_intake_m3_h,3),"brine_m3_h":round(w.brine_m3_h,3),"heat_kw":round(w.water_heat_used_kw,2),"heat_available_kw":round(w.water_heat_available_kw,2),
                  "heat": w.water_plant_heat, "plant_m3_h": round(w.water_plant_m3_h, 2), "flow_m3_h": round(w.water_flow_m3_h, 2),
                  "pump": w.pump_station_ok, "houses_ok": int(w.h_water_ok.sum()),
                  "burst": int(w.h_burst.sum()), "frozen": int((~w.h_pipes_ok).sum()),
                  "sector_m3_h": [round(float(x) * 60, 2) for x in w.sector_water_m3]},
        "net": {"mobile":w.mobile_online,"dish":w.dish_ok,"uplink": w.uplink_ok, "tower": w.tower_ok, "comms": w.comms_ok, "houses_online": int(w.h_net_online.sum()),
                "packets_per_min": w.packets_per_min, "reactor_link": w.r_link_ok,
                "packets": w.packets[-40:]},
        "finance": {"colony": round(w.colony_budget), "sectors": [round(float(x)) for x in w.sector_budget],
                    "unpaid": round(w.unfunded_total), "month": w.month,
                    "month_expense": round(w.colony_month_expense), "month_income": round(w.colony_month_income),
                    "waste_station": round(w.waste_station_level, 2)},
        "sectors": sec,
        "houses": {"t": [round(float(x), 1) for x in w.h_t_in], "power": w.h_power_ok.astype(int).tolist(),
                   "ups": w.h_on_ups.astype(int).tolist(), "water": w.h_water_ok.astype(int).tolist(),
                   "net": w.h_net_online.astype(int).tolist(), "heater": w.h_heater_on.astype(int).tolist(),
                   "pipes":w.h_pipes_ok.astype(int).tolist(), "burst": w.h_burst.astype(int).tolist(), "sludge": [round(float(x), 2) for x in w.h_sludge],
                   "limit": [int(x) for x in w.h_limit_w], "draw": [int(x) for x in w.h_draw_w]},
        "poles": {"state": w.p_state.tolist(), "lamp": w.p_lamp_on.astype(int).tolist(),
                  "span": w.s_online.astype(int).tolist(), "net": w.net_chain.astype(int).tolist(),
                  "ice": [round(float(x), 2) for x in w.s_ice]},
        "rovers": [{"name": r.name, "kind": r.kind, "state": r.state, "x": round(r.x,3), "y": round(r.y,3),
                    "fuel_l":round(r.fuel_l,2),"distance_m":round(r.odometer_m,3),"velocity":round(r.velocity,3),
                    "heading": round(r.heading, 2), "load": round(r.load, 2),
                    "job": (r.job.kind if isinstance(r.job, Issue) else (r.job + 1 if isinstance(r.job, (int, np.integer)) else None))}
                   for r in w.rovers+getattr(w,"traffic",[])],
        "cargo":w.cargo,
        "xenos": [{"id": m.get("id", 0), "x": round(m["x"]), "y": round(m["y"]), "state": m.get("state", "hunt"), "sector": m["sector"] + 1,
                   "heading": round(m.get("heading", 0.0), 2), "target": int(m.get("target", -1)) + 1} for m in w.xeno_markers],
        "squad": {"x": round(w.squad["x"]), "y": round(w.squad["y"]), "state": w.squad["state"], "sector": w.squad["sector"] + 1,
                  "heading": round(w.squad.get("heading", 0.0), 2)},
        "wall_breach": [None if a is None else round(float(a), 1) for a in w.wall_breach],
        "people": [[round(float(x)), round(float(y)), int(s), int(h)] for x, y, s, h in zip(w.w_x, w.w_y, w.w_state, w.w_home) if s != 0],
        "marines": [[c["reactor_pos"][0] + 60 + 24 * k, c["reactor_pos"][1] - 50 + 20 * (k % 2)] for k in range(4)] if w.marines_active > 0 else [],
        "issues": issues, "issues_total": len(w.open_issues()),
        "events": list(w.events)[:40],
        "report": w.last_report,
        "month_progress": {"day": w.t // c["ticks_per_day"] % c["days_per_month"] + 1, "days": c["days_per_month"],
                           "sector_income": [round(float(x)) for x in w.month_income], "sector_expense": [round(float(x)) for x in w.month_expense],
                           "colony_income": round(w.colony_month_income), "colony_expense": round(w.colony_month_expense),
                           "kwh": round(float(w.h_meter_month.sum())), "water_m3": round(float(w.h_water_month.sum()), 1),
                           "repairs": round(float(w.h_repairs_month.sum()))},
        "control": {"programs": w.h_program, "reasons": w.h_reason, "ext": getattr(w, "h_ext", np.zeros(w.N, dtype=bool)).astype(int).tolist(),
                    "targets": [round(float(x), 1) for x in w.h_target],
                    "mqtt": (w.bridge.status() if getattr(w, "bridge", None) else {"enabled": False})},
    }


def bus_snapshot(w: World):
    """Everything the /bus page shows: bus status, message tail, per-house control table, per-program comparison."""
    c = w.cfg
    ext = getattr(w, "h_ext", np.zeros(w.N, dtype=bool))
    bridge = getattr(w, "bridge", None)
    houses = []
    for i in range(w.N):
        houses.append([i + 1, int(w.h_sector[i]) + 1, (w.h_program[i] if ext[i] else "thermostat"), w.h_reason[i] if ext[i] else "",
                       round(float(w.h_target[i]), 1), round(float(w.h_t_in[i]), 1), int(w.h_heater_on[i]), int(w.h_draw_w[i]),
                       int(w.h_power_ok[i]), int(w.h_on_ups[i]), int(w.h_limit_w[i]), int(w.h_water_ok[i]), int(w.h_net_online[i]),
                       int(w.t - bridge.last_pub_t[i]) if bridge else -1, int(w.t - w.h_ctrl_t[i]) if ext[i] else -1,
                       int(w.h_appliances_on[i]), int(w.h_valve_open[i])])
    progs = []
    current = [(p if (p and ext[i]) else "thermostat") for i, p in enumerate(w.h_program)]
    for name, st in sorted(w.prog_stats.items()):
        ht = max(1, st["house_ticks"])
        progs.append({"program": name, "houses": current.count(name),
                      "avg_t": round(st["t_sum"] / ht, 2), "kwh_per_house_day": round(st["kwh"] / ht * 1440, 2),
                      "cold_share": round(st["cold_ticks"] / ht * 100, 2), "cost_per_house_day": round(st["cost"] / ht * 1440, 2)})
    return {"t": w.t, "time": w.time_str(), "mqtt": bridge.status() if bridge else {"enabled": False},
            "tail": bridge.tail_list() if bridge else [], "houses": houses, "programs": progs,
            "env": {"t_out": round(w.t_out, 1), "storm": w.storm_ticks > 0, "shedding": w.shedding}}


def house_snapshot(w: World, i: int):
    c = w.cfg
    ext = getattr(w, "h_ext", np.zeros(w.N, dtype=bool))
    heater = float(w.h_heat_w[i]); aeration = c["aeration_w"] if w.h_aeration_ok[i] else 0.0
    draw = float(w.h_draw_w[i]); fridge = 100.0 if w.h_power_ok[i] else 0.0
    rest = max(0.0, draw - heater - (aeration if w.h_power_ok[i] else 0.0) - fridge)
    order = [(w.h_hist_i + k) % w.h_hist.shape[1] for k in range(w.h_hist.shape[1])]
    events = [e for e in list(w.events) if f"House {i + 1}:" in e["text"] or f"house:{i}" in e["text"] or f"house {i + 1}" in e["text"].lower()][:10]
    return {"id": i + 1, "sector": int(w.h_sector[i]) + 1, "type": TYPE_NAMES[int(w.h_type[i])], "residents": int(w.h_residents[i]),
            "t_in": round(float(w.h_t_in[i]), 1), "target": round(float(w.h_target[i]), 1), "t_out": round(w.t_out, 1),
            "heater_on": bool(w.h_heater_on[i]), "heater_w": int(w.h_heater_w[i]), "heat_w": int(heater),
            "draw_w": int(draw), "split": {"heater": int(heater), "appliances": int(rest), "aeration": int(aeration if w.h_power_ok[i] else 0), "fridge": int(fridge)},
            "power_ok": bool(w.h_power_ok[i]), "on_ups": bool(w.h_on_ups[i]), "limit_w": int(w.h_limit_w[i]),
            "ups_kwh": round(float(w.ups_kwh[w.h_sector[i]]), 0), "ups_cap": c["ups_sector_kwh"], "ups_state": w.ups_state[w.h_sector[i]],
            "water_ok": bool(w.h_water_ok[i]), "pipes_ok": bool(w.h_pipes_ok[i]), "burst": bool(w.h_burst[i]), "valve_open": bool(w.h_valve_open[i]),
            "pressure_kpa": round(float(w.utilities.pressure[i]), 2),
            "delivered_l": round(float(w.utilities.delivered[i])*1000, 4),
            "leak_l": round(float(w.utilities.leaks[i])*1000, 4),
            "water_month_m3": round(float(w.h_water_month[i]), 2), "tank_m3": round(w.water_tank_m3, 0), "tank_cap": c["water_tank_m3"],
            "net_online": bool(w.h_net_online[i]), "terminal_ok": bool(w.h_terminal_ok[i]), "cabinet": bool(w.cabinet_online[w.h_sector[i]]),
            "sludge": round(float(w.h_sludge[i]), 2), "aeration_ok": bool(w.h_aeration_ok[i]), "appliances_on": bool(w.h_appliances_on[i]),
            "kwh_month": round(float(w.h_meter_month[i]), 1), "kwh_total": round(float(w.h_meter_kwh[i]), 1),
            "bill_month": round(float(w.h_meter_month[i]) * c["tariff_kwh"] + float(w.h_water_month[i]) * c["tariff_water_m3"] + float(w.h_repairs_month[i]), 1),
            "program": (w.h_program[i] if ext[i] else "thermostat"), "reason": w.h_reason[i] if ext[i] else "built-in thermostat",
            "ctrl_age": int(w.t - w.h_ctrl_t[i]) if ext[i] else -1, "pole": int(w.h_pole[i]), "pole_online": bool(w.s_online[w.h_pole[i]]),
            "hist_t": [round(float(w.h_hist[i, k]), 1) for k in order], "hist_w": [int(w.h_hist_draw[i, k]) for k in order],
            "log": [{"t": t, "text": x} for t, x in list(w.h_log[i])], "events": events,
            "issues": [{"kind": s.kind, "status": s.status, "cost": s.cost} for s in w.open_issues() if s.target in (f"house:{i}", f"aeration:{i}", f"terminal:{i}")],
            "time": w.time_str(), "t": w.t, "shedding": w.shedding}


def house_geometry(w: World):
    c = w.cfg
    return {
        "houses": {"x": [round(float(x), 5) for x in w.h_x], "y": [round(float(y), 5) for y in w.h_y],
                   "angle": [round(float(a), 2) for a in w.h_angle], "radius": [round(float(r)) for r in w.h_radius],
                   "sector": w.h_sector.tolist(), "type": w.h_type.tolist(), "pole": w.h_pole.tolist(),
                   "residents": w.h_residents.tolist()},
        "poles": {"x": [round(float(x), 1) for x in w.p_x], "y": [round(float(y), 1) for y in w.p_y],
                  "sector": w.p_sector.tolist(), "k": w.p_k.tolist(), "parent": w.p_parent.tolist(),
                  "kind": w.p_kind.tolist(), "radius": [round(float(r)) for r in w.p_radius],
                  "angle": [round(float(a), 2) for a in w.p_angle]},
        "cfg": {k: c[k] for k in ("hub_radius", "house_radius_min", "house_ring_step", "house_rows", "ring_road_radius",
                                  "wall_radius", "spine_radii", "reactor_pos", "solar_pos", "water_plant_pos",
                                  "radwaste_pos", "mine_pos", "waste_station_pos", "tower_junction", "tower_pos",
                                  "landing_pad_pos", "garage", "medlab", "school", "sectors", "water_tank_m3",
                                  "dish_pos","ocean_intake_pos","ocean_level_m","ocean_center","ocean_radii","cargo_depot")},
        "junctions":traffic_junctions(c),"river":RIVER_PROFILE,"utilities": w.utilities.geometry(w),
        "types": TYPE_NAMES,
    }


# ------------------------------------------------------------------------------------
# MQTT bridge: the world publishes sensors, the runtime answers with actuators.
# Topics (prefix hh/): tick, env/weather, env/power, house/{id}/sensors (retained),
# house/{id}/actuators (from the runtime). The bridge is optional: without --mqtt the
# built-in thermostat runs every house.
# ------------------------------------------------------------------------------------

class MqttBridge:
    def __init__(self, w: World, url: str):
        import paho.mqtt.client as mqtt
        host, _, port = url.partition(":")
        self.w = w
        self.host, self.port = host or "localhost", int(port or 1883)
        self.cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="hh-world", clean_session=True)
        self.cli.on_connect = self._on_connect
        self.cli.on_disconnect = lambda *a: setattr(self, "connected", False)
        self.cli.on_message = self._on_message
        self.connected = False
        self.inbox = deque()
        self.last_t_in = np.full(w.N, -999.0)
        self.last_flags = np.full((w.N, 6), -1, dtype=int)
        self.last_pub_t = np.full(w.N, -999)
        self.sent = 0
        self.received = 0
        self.last_try = 0.0
        self.tail = deque(maxlen=150)       # recent messages for the /bus page
        self.rate_in = deque(maxlen=600)    # (wall time) of received actuators, for messages per second
        self.rate_out = deque(maxlen=600)
        self.cli.connect_async(self.host, self.port, keepalive=30)
        self.cli.loop_start()

    def _watchdog(self):
        """paho does not retry a connection that never succeeded; try again every few seconds."""
        if self.connected or time.time() - self.last_try < 5.0:
            return
        self.last_try = time.time()
        try:
            self.cli.reconnect()
        except Exception:
            pass

    def _on_connect(self, client, userdata, flags, reason, properties=None):
        self.connected = True
        client.subscribe("hh/house/+/actuators")
        self.last_pub_t[:] = -999      # resend everything after a reconnect

    def _on_message(self, client, userdata, msg):
        try:
            hid = int(msg.topic.split("/")[2])
            body = msg.payload.decode("utf-8")
            self.inbox.append((hid, json.loads(body)))
            self.rate_in.append(time.time())
            if hid % 7 == 0:
                self.tail.append({"dir": "in", "topic": msg.topic, "body": body[:160], "at": time.time()})
        except Exception:
            pass

    def apply(self):
        """Called at the start of a tick under the world lock: move received actuators into the arrays."""
        w = self.w
        while self.inbox:
            hid, a = self.inbox.popleft()
            if not (0 <= hid < w.N):
                continue
            self.received += 1
            w.h_ctrl_t[hid] = w.t
            w.h_ctrl_heater[hid] = bool(a.get("heater_on", w.h_ctrl_heater[hid]))
            w.h_ctrl_target[hid] = float(a.get("target_c", w.h_ctrl_target[hid]))
            w.h_ctrl_valve[hid] = bool(a.get("valve_open", True))
            w.h_ctrl_appl[hid] = bool(a.get("appliances_on", True))
            w.h_program[hid] = str(a.get("program", ""))[:24]
            w.h_reason[hid] = str(a.get("reason", ""))[:60]

    def publish(self):
        """Called at the end of a tick: env every tick, houses on change or every 10 ticks."""
        w = self.w
        if not self.connected:
            self._watchdog()
            return
        c = self.cli
        hour = w.t // 60 % 24 + (w.t % 60) / 60.0
        c.publish("hh/tick", json.dumps({"t": w.t, "time": w.time_str()}), qos=0)
        c.publish("hh/env/weather", json.dumps({"t": w.t, "t_out": round(w.t_out, 1), "wind": round(w.wind, 1), "storm": w.storm_ticks > 0,
                                                 "precip": w.precip, "hour": round(hour, 2), "night": w.is_night(), "daylight": round(w.daylight, 3)}), qos=0, retain=True)
        c.publish("hh/env/power", json.dumps({"t": w.t, "available_kw": round(w.available_kw), "demand_kw": round(w.demand_kw), "shedding": w.shedding,
                                               "reactor_mode": w.r_mode, "tariff_kwh": w.cfg["tariff_kwh"]}), qos=0, retain=True)
        flags = np.stack([w.h_power_ok, w.h_on_ups, w.h_water_ok, w.h_pipes_ok, w.h_net_online, w.h_limit_w > 0], axis=1).astype(int)
        changed = (np.abs(w.h_t_in - self.last_t_in) >= 0.2) | (flags != self.last_flags).any(axis=1) | (w.t - self.last_pub_t >= 10)
        for i in np.flatnonzero(changed):
            payload = {"t": w.t, "id": int(i), "sector": int(w.h_sector[i]) + 1, "t_in": round(float(w.h_t_in[i]), 1),
                       "power_ok": bool(w.h_power_ok[i]), "on_ups": bool(w.h_on_ups[i]), "limit_w": int(w.h_limit_w[i]),
                       "water_ok": bool(w.h_water_ok[i]), "pipes_ok": bool(w.h_pipes_ok[i]), "burst": bool(w.h_burst[i]),
                       "net_online": bool(w.h_net_online[i]), "sludge": round(float(w.h_sludge[i]), 2), "draw_w": int(w.h_draw_w[i]),
                       "heater_on": bool(w.h_heater_on[i]), "residents": int(w.h_residents[i]),
                       "pressure_kpa": round(float(w.utilities.pressure[i]), 2),
                       "water_l_min": round(float(w.utilities.delivered[i])*60000/w.cfg["tick_seconds"], 4),
                       "leak_l_min": round(float(w.utilities.leaks[i])*60000/w.cfg["tick_seconds"], 4)}
            body = json.dumps(payload)
            c.publish(f"hh/house/{int(i)}/sensors", body, qos=0, retain=True)
            self.rate_out.append(time.time())
            if i % 7 == 0:
                self.tail.append({"dir": "out", "topic": f"hh/house/{int(i)}/sensors", "body": body[:160], "at": time.time()})
            self.last_t_in[i] = w.h_t_in[i]
            self.last_flags[i] = flags[i]
            self.last_pub_t[i] = w.t
            self.sent += 1

    def status(self):
        w = self.w
        fresh = int(((w.t - w.h_ctrl_t) < 15).sum())
        now = time.time()
        return {"enabled": True, "connected": self.connected, "broker": f"{self.host}:{self.port}", "controlled": fresh,
                "sent": self.sent, "received": self.received,
                "out_per_s": sum(1 for t in self.rate_out if now - t < 5) / 5.0, "in_per_s": sum(1 for t in self.rate_in if now - t < 5) / 5.0}

    def tail_list(self):
        now = time.time()
        return [{"dir": m["dir"], "topic": m["topic"], "body": m["body"], "age": round(now - m["at"], 1)} for m in list(self.tail)[-60:]]


# ------------------------------------------------------------------------------------
# Persistence: pickle of the world for resume, sqlite for history
# ------------------------------------------------------------------------------------

class Store:
    def __init__(self, data_dir: str):
        self.dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.pkl = os.path.join(data_dir, "world.pkl")
        self.db = os.path.join(data_dir, "history.db")
        con = sqlite3.connect(self.db)
        con.executescript("""
            CREATE TABLE IF NOT EXISTS hourly (t INTEGER PRIMARY KEY, time TEXT, t_out REAL, wind REAL, storm INTEGER,
                available_kw REAL, demand_kw REAL, shedding INTEGER, reactor_mode TEXT, core_temp REAL,
                water_tank REAL, houses_power INTEGER, houses_water INTEGER, houses_net INTEGER, burst INTEGER,
                issues INTEGER, colony REAL, sectors TEXT, avg_t REAL, min_t REAL);
            CREATE TABLE IF NOT EXISTS events (t INTEGER, level TEXT, text TEXT);
            CREATE TABLE IF NOT EXISTS reports (month INTEGER PRIMARY KEY, saved_t INTEGER, json TEXT);
        """)
        con.commit()
        con.close()
        self.last_event_t = -1
        self.last_report_month = 0

    def load_world(self) -> Optional[World]:
        if not os.path.exists(self.pkl):
            return None
        try:
            with open(self.pkl, "rb") as f:
                w = pickle.load(f)
            if getattr(w, "schema", 1) != World.SCHEMA:
                old = self.pkl.replace(".pkl", ".old.pkl")
                os.replace(self.pkl, old)
                print(f"saved world has schema {getattr(w, 'schema', 1)}, current is {World.SCHEMA}; moved it to {old}, starting a new world")
                return None
            added = self.migrate(w)
            print(f"resumed world from {self.pkl} at {w.time_str()} (tick {w.t}){', added fields: ' + ', '.join(added) if added else ''}")
            return w
        except Exception as e:
            print(f"could not load {self.pkl}: {e}; starting a new world")
            return None

    @staticmethod
    def migrate(w: World):
        """Fill in attributes a newer version added since the world was saved, using a fresh world's defaults."""
        w.cfg = {**CFG, **w.cfg}
        fresh = World(w.cfg)
        added = []
        for k, v in fresh.__dict__.items():
            if k not in w.__dict__:
                setattr(w, k, UtilityNetwork(w) if k == "utilities" else v)
                added.append(k)
        for k, v in fresh.cfg.items():
            w.cfg.setdefault(k, v)
        if w.utilities.version != UtilityNetwork.VERSION:
            old=w.utilities;w.utilities=UtilityNetwork(w)
            for key in ('sewer_storage','storm_storage','snow_m3','pump_speed','overflow_m3'):
                setattr(w.utilities,key,getattr(old,key,getattr(w.utilities,key)))
            added.append('utilities v3')
        for r in w.rovers:
            for key,value in [('velocity',0.0),('fuel_l',120.0),('odometer_m',0.0)]:
                if key not in r.__dict__:setattr(r,key,value)
        return added

    def save_world(self, w: World):
        tmp = self.pkl + ".tmp"
        with open(tmp, "wb") as f:
            pickle.dump(w, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, self.pkl)

    def record_hour(self, w: World):
        con = sqlite3.connect(self.db)
        con.execute("INSERT OR REPLACE INTO hourly VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            w.t, w.time_str(), round(w.t_out, 1), round(w.wind, 1), int(w.storm_ticks > 0),
            round(w.available_kw), round(w.demand_kw), w.shedding, w.r_mode, round(w.r_core_temp),
            round(w.water_tank_m3, 1), int(w.h_power_ok.sum()), int(w.h_water_ok.sum()), int(w.h_net_online.sum()),
            int(w.h_burst.sum()), len(w.open_issues()), round(w.colony_budget),
            json.dumps([round(float(x)) for x in w.sector_budget]), round(float(w.h_t_in.mean()), 1),
            round(float(w.h_t_in.min()), 1)))
        new_events = [e for e in list(w.events) if e["t"] > self.last_event_t]
        if new_events:
            con.executemany("INSERT INTO events VALUES (?,?,?)", [(e["t"], e["level"], e["text"]) for e in reversed(new_events)])
            self.last_event_t = max(e["t"] for e in new_events)
        if w.last_report and w.last_report["month"] > self.last_report_month:
            con.execute("INSERT OR REPLACE INTO reports VALUES (?,?,?)", (w.last_report["month"], w.t, json.dumps(w.last_report)))
            self.last_report_month = w.last_report["month"]
        con.commit()
        con.close()

    def history(self, hours: int):
        con = sqlite3.connect(self.db)
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT * FROM hourly ORDER BY t DESC LIMIT ?", (hours,)).fetchall()
        reports = con.execute("SELECT json FROM reports ORDER BY month").fetchall()
        con.close()
        return {"hourly": [dict(r) for r in reversed(rows)], "reports": [json.loads(r[0]) for r in reports]}


# ------------------------------------------------------------------------------------
# Simulation thread and HTTP server
# ------------------------------------------------------------------------------------

def new_colony(w_holder: dict, reason: str):
    """Replace the finished world with a fresh one; the old world's events stay in history.db."""
    old = w_holder["w"]
    w = World(CFG)
    w.speed = old.speed
    w.bridge = getattr(old, "bridge", None)
    if w.bridge:
        w.bridge.w = w
        w.bridge.last_pub_t[:] = -999
    w.log("INFO", f"New colony founded ({reason}); the previous one ended with: {old.finish_reason or 'operator reset'}")
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
                    w = new_colony(w_holder, "automatic restart two minutes after the end")
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


def make_handler(w_holder: dict, html: str, geom_json: str, store: Optional[Store], admin_token: str,
                 html3d: str = "", vendor_dir: str = ""):
    from http.server import BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _send(self, code, ctype, body: bytes):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/" or self.path.startswith("/index") or self.path.startswith("/?"):
                self._send(200, "text/html; charset=utf-8", (html3d or html).encode("utf-8"))
            elif self.path.startswith("/flat"):
                self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))
            elif self.path.startswith("/vendor/") and vendor_dir:
                rel = os.path.normpath(self.path.split("?")[0][len("/vendor/"):])
                fp = os.path.join(vendor_dir, rel)
                if rel.startswith("..") or not os.path.isfile(fp):
                    self._send(404, "text/plain", b"not found")
                    return
                with open(fp, "rb") as f:
                    self._send(200, "text/javascript" if fp.endswith(".js") else "application/octet-stream", f.read())
            elif self.path.startswith("/geometry"):
                self._send(200, "application/json", geom_json.encode("utf-8"))
            elif self.path.startswith("/state"):
                w = w_holder["w"]
                with w.lock:
                    body = json.dumps(snapshot(w)).encode("utf-8")
                self._send(200, "application/json", body)
            elif self.path.startswith("/house.json"):
                w = w_holder["w"]
                try:
                    hid = int(clamp(int(self.path.split("id=")[1].split("&")[0]) - 1, 0, w.N - 1))
                except (IndexError, ValueError):
                    hid = 0
                with w.lock:
                    body = json.dumps(house_snapshot(w, hid)).encode("utf-8")
                self._send(200, "application/json", body)
            elif self.path.startswith("/house"):
                self._send(200, "text/html; charset=utf-8", HTMLHOUSE.encode("utf-8"))
            elif self.path.startswith("/attractors.json"):
                w = w_holder["w"]
                with w.lock:
                    body = json.dumps(attractor_snapshot(w, "hist=1" in self.path)).encode("utf-8")
                self._send(200, "application/json", body)
            elif self.path.startswith("/attractors"):
                self._send(200, "text/html; charset=utf-8", HTMLATTR.encode("utf-8"))
            elif self.path.startswith("/graph"):
                self._send(200, "text/html; charset=utf-8", HTMLGRAPH.encode("utf-8"))
            elif self.path.startswith("/bus.json"):
                w = w_holder["w"]
                with w.lock:
                    body = json.dumps(bus_snapshot(w)).encode("utf-8")
                self._send(200, "application/json", body)
            elif self.path.startswith("/bus"):
                self._send(200, "text/html; charset=utf-8", HTMLBUS.encode("utf-8"))
            elif self.path.startswith("/history"):
                hours = 720
                if "hours=" in self.path:
                    try:
                        hours = int(clamp(int(self.path.split("hours=")[1].split("&")[0]), 1, 24 * 365))
                    except ValueError:
                        pass
                body = json.dumps(store.history(hours) if store else {"hourly": [], "reports": []}).encode("utf-8")
                self._send(200, "application/json", body)
            else:
                self._send(404, "text/plain", b"not found")

        def do_POST(self):
            n = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(n) if n else b"{}"
            try:
                req = json.loads(raw.decode("utf-8") or "{}")
            except Exception:
                req = {}
            cmd = req.get("cmd", "")
            w = w_holder["w"]
            if cmd == "auth":
                ok = (not admin_token) or req.get("token", "") == admin_token
                self._send(200, "application/json", json.dumps({"ok": ok, "protected": bool(admin_token)}).encode())
                return
            if admin_token and req.get("token", "") != admin_token:
                self._send(403, "application/json", b'{"ok": false, "error": "admin token required"}')
                return
            with w.lock:
                if cmd == "pause":
                    w.paused = not w.paused
                elif cmd == "speed":
                    w.speed = int(clamp(int(req.get("value", 20)), 0, 600))
                    if w.speed == 0:
                        w.paused = True
                    elif w.paused:
                        w.paused = False
                elif cmd == "inject":
                    info = inject(w, req.get("value", "")) or {}
                    self._send(200, "application/json", json.dumps({"ok": True, **info}).encode())
                    return
                elif cmd == "reset":
                    w = new_colony(w_holder, "operator")
                elif cmd == "reactor":
                    v = req.get("value", "")
                    if v == "scram":
                        reactor_scram(w, "operator")
            self._send(200, "application/json", b'{"ok": true}')

    return Handler


def main():
    import argparse
    from http.server import ThreadingHTTPServer

    ap = argparse.ArgumentParser(description="Hadley's Hope colony simulation")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", CFG["http_port"])))
    ap.add_argument("--data", default=os.environ.get("DATA_DIR", ""), help="directory for autosave and history (empty = no persistence)")
    ap.add_argument("--fresh", action="store_true", help="ignore a saved world and start over")
    ap.add_argument("--speed", type=int, default=CFG["default_speed"], help="simulated minutes per real second")
    ap.add_argument("--seed", type=int, default=CFG["seed"])
    ap.add_argument("--headless", type=int, default=0, help="run N ticks without the server, print a summary and exit")
    ap.add_argument("--mqtt", default=os.environ.get("MQTT_URL", ""), help="broker host:port; enables the sensor/actuator bus for external house controllers")
    args = ap.parse_args()
    CFG["seed"] = args.seed
    store = Store(args.data) if args.data else None
    w = None if (args.fresh or not store) else store.load_world()
    if w is None:
        w = World(CFG)
    w.speed = args.speed
    admin_token = os.environ.get("ADMIN_TOKEN", "")
    w.bridge = None
    if args.mqtt:
        try:
            w.bridge = MqttBridge(w, args.mqtt)
            print(f"mqtt bridge: {args.mqtt}")
        except ImportError:
            print("paho-mqtt is not installed, run: pip install paho-mqtt ; continuing without the bus")
    if args.headless:
        t0 = time.time()
        for _ in range(args.headless):
            world_tick(w)
        dt = time.time() - t0
        snap = snapshot(w)
        print(f"{args.headless} ticks in {dt:.2f} s ({args.headless / max(dt, 1e-9):.0f} ticks/s)")
        print(json.dumps({k: snap[k] for k in ("time", "env", "power", "reactor", "water", "finance")}, indent=1, ensure_ascii=False))
        print("open issues:", snap["issues_total"])
        for e in list(w.events)[:15]:
            print(f"  t={e['t']:6d} {e['level']:5s} {e['text']}")
        return
    holder = {"w": w}
    threading.Thread(target=sim_loop, args=(holder, store), daemon=True).start()
    vendor_dir = ""
    for cand in (os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"), os.path.join(args.data or ".", "vendor")):
        if os.path.isfile(os.path.join(cand, "three", "build", "three.module.js")):
            vendor_dir = cand
            break
    three_base = "/vendor/three/" if vendor_dir else "https://cdn.jsdelivr.net/npm/three@0.160.0/"
    html3d = HTML3D.replace("__THREE_BASE__", three_base)
    handler = make_handler(holder, HTML, json.dumps(house_geometry(w)), store, admin_token, html3d, vendor_dir)
    srv = None
    for attempt in range(30):
        try:
            srv = ThreadingHTTPServer(("0.0.0.0", args.port), handler)
            break
        except OSError as e:
            if attempt == 0:
                print(f"port {args.port} busy ({e}), retrying for 30 s")
            time.sleep(1)
    if srv is None:
        print(f"could not bind port {args.port}; is another instance running? check: ss -tlnp | grep :{args.port}")
        raise SystemExit(1)
    print(f"Hadley's Hope simulation: open http://localhost:{args.port}  (speed {w.speed} min/s, seed {args.seed})")
    print(f"persistence: {args.data or 'off'}; admin token: {'set' if admin_token else 'not set, everyone can inject'}")
    print("Ctrl+C to stop")

    def shutdown(*_):
        if store:
            with w.lock:
                store.save_world(w)
            print("world saved at", w.time_str())
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, shutdown)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
