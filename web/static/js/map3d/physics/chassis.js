/** Fixed-step chassis dynamics: engine, gearbox, tire forces and four spring contacts.
 * Units: metres, seconds, radians, kilograms. No fuel is consumed in manual mode. */
import * as THREE from "three";
import { state } from "../state.js";
import {
  surfaceHeight,
  xyNormal,
  normalXY,
  quatAt,
} from "../geometry/planet.js";
import { onRoad } from "../geometry/roads.js";

export function groundAt(x, y) {
  const h = surfaceHeight(x, y),
    road = onRoad(x, y),
    ice = h < state.G.cfg.ocean_level_m + 0.1;
  return {
    height: ice
      ? state.G.cfg.ocean_level_m
      : Math.max(-10, h) + (road ? 1 : 0.08),
    mu: ice
      ? 0.14
      : road
        ? state.S?.env.icy && !state.S?.power.infra.road_heating
          ? 0.38
          : 0.92
        : 0.58,
    rolling: road ? 0.018 : 0.075,
    road,
    ice,
  };
}

export function chassisState(x, y, heading = 0) {
  const g = groundAt(x, y);
  return {
    x,
    y,
    heading,
    v: 0,
    lateral: 0,
    alt: g.height + 0.055,
    vertical: 0,
    pitch: 0,
    roll: 0,
    steer: 0,
    rpm: 850,
    gear: 1,
    shift: 0,
    distance: 0,
    compression: [0.115, 0.115, 0.115, 0.115],
    wheelY: [0.67, 0.67, 0.67, 0.67],
    grounded: true,
    mu: g.mu,
    surface: g.ice ? "ICE" : g.road ? "ASPHALT" : "OFF ROAD",
    throttle: 0,
    brake: 0,
  };
}

export function stepChassis(
  d,
  input,
  dt,
  ground = groundAt,
  blocked = () => false,
) {
  const mass = d.name?.startsWith("freight") ? 5500 : 2200,
    wheelRadius = 0.66,
    wheelbase = 3.8,
    track = 2.5,
    g = 7.5 * (state.RP / (state.RP + Math.max(-20, d.alt))) ** 2,
    N = mass * g;
  let throttle = input.forward ? 1 : 0,
    brake = input.back && d.v > 0.35 ? 1 : input.forward && d.v < -0.35 ? 1 : 0;
  if (input.back && Math.abs(d.v) < 0.35) {
    d.gear = -1;
    throttle = 1;
  } else if (input.back && d.v < 0) throttle = 1;
  if (input.forward && Math.abs(d.v) < 0.35 && d.gear < 0) d.gear = 1;
  const ratios = [0, 3.8, 2.4, 1.6, 1.15, 0.85],
    ratio = d.gear < 0 ? 3.2 : ratios[d.gear],
    direction = d.gear < 0 ? -1 : 1;
  const coupled =
      ((Math.abs(d.v) / wheelRadius) * ratio * 3.9 * 60) / (Math.PI * 2),
    targetRPM = Math.max(850, coupled, throttle ? 1300 : 850);
  d.rpm += (targetRPM - d.rpm) * (1 - Math.exp(-10 * dt));
  d.rpm = THREE.MathUtils.clamp(d.rpm, 750, 6200);
  d.shift = Math.max(0, d.shift - dt);
  if (d.gear > 0 && d.shift === 0) {
    if (coupled > 3900 && d.gear < 5) {
      d.gear++;
      d.shift = 0.24;
    } else if (coupled < 1350 && d.gear > 1) {
      d.gear--;
      d.shift = 0.18;
    }
  }
  const steerTarget =
    (((input.right ? 1 : 0) - (input.left ? 1 : 0)) * 0.52) /
    (1 + Math.abs(d.v) * 0.023);
  d.steer += (steerTarget - d.steer) * (1 - Math.exp(-7 * dt));
  const center = ground(d.x, d.y),
    f = [Math.cos(d.heading), Math.sin(d.heading)],
    side = [-f[1], f[0]],
    contacts = [];
  for (const xx of [-1.9, 1.9])
    for (const zz of [-1.25, 1.25])
      contacts.push(
        ground(d.x + f[0] * xx + side[0] * zz, d.y + f[1] * xx + side[1] * zz),
      );
  const stiffness = mass * 16.36,
    damping = mass * 1.65;
  let springForce = 0;
  for (let i = 0; i < 4; i++) {
    const xx = i < 2 ? -1.9 : 1.9,
      zz = i % 2 ? -1.25 : 1.25,
      bodyAt = d.alt + Math.sin(d.pitch) * xx + Math.sin(d.roll) * zz,
      compression = THREE.MathUtils.clamp(
        0.16 + contacts[i].height - bodyAt,
        0,
        0.42,
      );
    d.compression[i] = compression;
    const force =
      compression > 0
        ? Math.max(0, stiffness * compression - (damping * d.vertical) / 4)
        : 0;
    springForce += force;
    d.wheelY[i] = 0.67 + compression - 0.115;
  }
  d.grounded = springForce > N * 0.08;
  d.vertical += (springForce / mass - g) * dt;
  d.alt += d.vertical * dt;
  const maxGround = Math.max(...contacts.map((q) => q.height));
  if (d.alt < maxGround - 0.32) {
    d.alt = maxGround - 0.32;
    d.vertical = Math.max(0, d.vertical) * 0.12;
  }
  const front = (contacts[2].height + contacts[3].height) / 2,
    rear = (contacts[0].height + contacts[1].height) / 2,
    left = (contacts[1].height + contacts[3].height) / 2,
    right = (contacts[0].height + contacts[2].height) / 2,
    grade = Math.atan2(front - rear, wheelbase);
  const tireMu = center.mu * (input.handbrake ? 0.55 : 1),
    maxForce = tireMu * Math.min(N * 1.5, springForce),
    torque =
      (mass / 2200) * 390 * Math.max(0.35, 1 - ((d.rpm - 2700) / 5000) ** 2),
    engine =
      d.shift > 0
        ? 0
        : ((throttle * torque * ratio * 3.9 * 0.87) / wheelRadius) * direction;
  const sign = Math.sign(d.v),
    rolling = center.rolling * N * sign,
    drag = 0.5 * 1.2 * 0.48 * 3.8 * d.v * Math.abs(d.v),
    engineBrake = throttle ? 0 : Math.min(1100, Math.abs(d.v) * 100) * sign;
  let force =
    THREE.MathUtils.clamp(engine, -maxForce, maxForce) -
    (brake || input.handbrake ? Math.min(maxForce, N * 1.3) * sign : 0) -
    rolling -
    drag -
    engineBrake -
    N * Math.sin(grade);
  if (
    Math.abs(d.v) < 0.07 &&
    throttle === 0 &&
    Math.abs(N * Math.sin(grade)) < maxForce
  ) {
    d.v = 0;
    force = 0;
  }
  const before = d.v;
  d.v = THREE.MathUtils.clamp(d.v + (force / mass) * dt, -12, 48);
  if ((brake || input.handbrake) && Math.sign(before) !== Math.sign(d.v))
    d.v = 0;
  const desiredYaw = (d.v * Math.tan(d.steer)) / wheelbase,
    maxYaw = (tireMu * g) / Math.max(2, Math.abs(d.v)),
    yaw = d.grounded ? THREE.MathUtils.clamp(desiredYaw, -maxYaw, maxYaw) : 0;
  d.heading += yaw * dt;
  d.lateral += (desiredYaw - yaw) * d.v * dt;
  d.lateral *= Math.exp(
    -(d.grounded ? (input.handbrake ? 1 : 8) * tireMu : 0.1) * dt,
  );
  const oldNormal = xyNormal(d.x, d.y),
    q = quatAt(d.x, d.y, -d.heading),
    forward = new THREE.Vector3(1, 0, 0).applyQuaternion(q),
    rightward = new THREE.Vector3(0, 0, 1).applyQuaternion(q),
    velocity = forward
      .clone()
      .multiplyScalar(d.v)
      .addScaledVector(rightward, d.lateral),
    normal = oldNormal
      .clone()
      .addScaledVector(velocity, dt / (state.RP + d.alt))
      .normalize(),
    xy = normalXY(normal);
  if (blocked(xy[0], xy[1], d.name)) {
    d.v *= -0.12;
    d.lateral = 0;
  } else {
    d.x = xy[0];
    d.y = xy[1];
    d.distance += velocity.length() * dt;
    const transport = new THREE.Quaternion().setFromUnitVectors(
      oldNormal,
      normal,
    );
    forward
      .applyQuaternion(transport)
      .applyQuaternion(quatAt(d.x, d.y).invert());
    d.heading = Math.atan2(forward.z, forward.x);
  }
  d.pitch +=
    (THREE.MathUtils.clamp(grade - (force / mass) * 0.009, -0.55, 0.55) -
      d.pitch) *
    (1 - Math.exp(-9 * dt));
  d.roll +=
    (THREE.MathUtils.clamp(
      Math.atan2(left - right, track) - yaw * d.v * 0.015,
      -0.5,
      0.5,
    ) -
      d.roll) *
    (1 - Math.exp(-8 * dt));
  d.mu = center.mu;
  d.surface = center.ice ? "ICE" : center.road ? "ASPHALT" : "OFF ROAD";
  d.throttle = throttle;
  d.brake = brake;
}
