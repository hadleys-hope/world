/** Common planet-local placement for roads, plots and utilities. */
import { state } from "../../state.js";
import { bodyHeight, PLATEAU } from "../../geometry/noise.js";
import { dirAt } from "../klyaksa.js";

export function createPlacement(R, plan = state.klyaksaPlanData) {
  const cities = plan?.cities || [];
  return (x, y, height = 0) => {
    const n = dirAt(x, y, R);
    const urban = cities.some(
      (c) => Math.hypot(x - c.at[0], y - c.at[1]) <= c.wall + 65,
    );
    // Every city sits on its prepared grade. Bridge decks add their own elevation;
    // sampling the riverbed here would pull a bridge down into its channel.
    const grade = urban
      ? R * PLATEAU
      : Math.max(
          0,
          state.klyaksaGroundAt?.(x, y) ?? bodyHeight(3, n.x, n.y, n.z) * R,
        );
    return n.multiplyScalar(R + grade + 0.25 + height);
  };
}

/** Index narrow road corridors once; vegetation queries inspect only the local cell. */
export function roadClearance(paths, margin = 42, cell = 128) {
  const cells = new Map();
  for (const path of paths)
    for (let i = 1; i < path.length; i++) {
      const [x, y] = path[i - 1],
        [bx, by] = path[i];
      const dx = bx - x,
        dy = by - y;
      const segment = { x, y, dx, dy, length2: dx * dx + dy * dy || 1 };
      for (
        let a = Math.floor((Math.min(x, bx) - margin) / cell);
        a <= Math.floor((Math.max(x, bx) + margin) / cell);
        a++
      ) {
        for (
          let b = Math.floor((Math.min(y, by) - margin) / cell);
          b <= Math.floor((Math.max(y, by) + margin) / cell);
          b++
        ) {
          const key = `${a},${b}`;
          if (!cells.has(key)) cells.set(key, []);
          cells.get(key).push(segment);
        }
      }
    }
  return (x, y) => {
    const nearby = cells.get(`${Math.floor(x / cell)},${Math.floor(y / cell)}`);
    if (!nearby) return false;
    for (const s of nearby) {
      const t = Math.max(
        0,
        Math.min(1, ((x - s.x) * s.dx + (y - s.y) * s.dy) / s.length2),
      );
      if (
        (x - s.x - s.dx * t) ** 2 + (y - s.y - s.dy * t) ** 2 <
        margin * margin
      )
        return true;
    }
    return false;
  };
}
