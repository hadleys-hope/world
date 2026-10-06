/** Reproducible geometry/behavior checks using the repository's vendored Three.js. */
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
const root = fileURLToPath(new URL("../", import.meta.url));
function run(command, args) {
  const result = spawnSync(command, args, { cwd: root, stdio: "inherit" });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status || 1);
}
run(process.env.PYTHON || "python3", ["tests/export_visual_fixture.py"]);
for (const name of [
  "build-queue",
  "camera-clipping",
  "planet-rotation",
  "urban-civic",
  "klyaksa-streets",
  "klyaksa-traffic",
  "klyaksa-utilities",
  "klyaksa-connections",
  "klyaksa-terrain",
  "river-flow",
  "river-port-layout",
  "klyaksa-visuals",
]) {
  run(process.execPath, [
    "--experimental-loader",
    "./tests/three-loader.mjs",
    `tests/${name}.mjs`,
  ]);
}
