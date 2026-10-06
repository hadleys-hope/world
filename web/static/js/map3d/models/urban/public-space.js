/** Acheron public space: reuse the garden's occupancy map and spherical terrain. */
import { state } from "../../state.js";
import { sph } from "../../geometry/planet.js";
import { Surface } from "./streets.js";
import { Batches, Model, bench, bin, pole, palette } from "./kit.js";
export function buildPublicSpace(ground) {
  const b = new Batches(
      state.world,
      state.RP,
      (x, y, h = 0) => sph(x, y, h),
      state.envUniforms,
    ),
    surfaces = new Surface((x, y, h = 0) => sph(x, y, h));
  let count = 0;
  for (let k = 0; k < 500 && count < 22; k++) {
    const a = k * 2.399963,
      r = 180 + ((k * 53) % 490),
      x = Math.cos(a) * r,
      y = Math.sin(a) * r;
    if (!ground.free(x, y, 10)) continue;
    ground.mark(x, y, 11);
    count++;
    surfaces.quad(
      [
        [x - 7, y - 7, 0.08],
        [x + 7, y - 7, 0.08],
        [x - 7, y + 7, 0.08],
        [x + 7, y + 7, 0.08],
      ],
      0x687e70,
    );
    for (const d of [-4, 4]) {
      b.add("park-bench", bench, x + d, y + 3, 0.12, 1);
      b.add("litter-bin", bin, x + d, y - 3, 0.12, 1);
    }
    b.add("garden-lamp", pole, x - 6, y - 6, 0.12, 0.65);
    if (count % 5 === 0) {
      b.add(
        "stage",
        () =>
          new Model()
            .box(0, 0.4, 0, 8, 0.8, 5, palette.wood)
            .box(0, 3, -2.5, 8, 6, 0.2, palette.dark)
            .box(0, 6, 0, 9, 0.18, 6, palette.white)
            .finish(),
        x,
        y,
        0.1,
      );
    } else if (count % 3 === 0) {
      b.add(
        "table",
        () =>
          new Model()
            .box(0, 0.8, 0, 2, 0.12, 1.2, palette.wood)
            .box(0, 0.4, 0, 0.3, 0.8, 0.3, palette.metal)
            .finish(),
        x,
        y,
        0.12,
      );
    }
  }
  // An outer exercise circuit is emitted only where the complete width is unoccupied.
  for (let k = 0; k < 720; k++) {
    const a = (k * Math.PI) / 360,
      z = ((k + 1) * Math.PI) / 360,
      r = state.G.cfg.wall_radius - 25,
      A = [Math.cos(a) * r, Math.sin(a) * r],
      B = [Math.cos(z) * r, Math.sin(z) * r];
    if (!ground.free(...A, 3) || !ground.free(...B, 3)) continue;
    surfaces.strip(A, B, 2.2, 0.1, 0x708d85, -1.2);
    surfaces.strip(A, B, 1.6, 0.11, 0xac846b, 1.0);
    if (k % 3 === 0) surfaces.strip(A, B, 0.12, 0.13, 0xe1dac3, -1.2);
  }
  state.world.add(surfaces.mesh());
  b.finish();
  state.acheronPublicSpaces = count;
}
