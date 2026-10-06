/** render/ground: what the ground is made of, close up. The landscape around the colony keeps its lit,
 * shadow-receiving standard material; this adds planet-local detail at four scales (0.5 m to 300 m), snow on
 * the flats and bare rock on the slopes, wet dark ground at the waterline, and a lawn under the dome. No
 * texture to pixelate when you land: every pixel is computed where it is. */
import { GLSL_NOISE, WATER_LEVEL } from "../geometry/noise.js";

export function detailGround(material, { radius, dome = 0 }) {
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uPR = { value: radius };
    shader.uniforms.uDome = { value: dome };
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nvarying vec3 vGP;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\nvGP = transformed;");
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", `#include <common>\nvarying vec3 vGP; uniform float uPR, uDome;\n${GLSL_NOISE}`)
      .replace(
        "#include <color_fragment>",
        `#include <color_fragment>
        {
          vec3 up = normalize(vGP);
          float alt = length(vGP) - uPR;                                   // metres above the datum
          float arc = acos(clamp(up.y, -1.0, 1.0)) * uPR;                  // distance from the colony centre
          vec3 fn = normalize(cross(dFdx(vGP), dFdy(vGP)));
          float flatness = abs(dot(fn, up));
          float n1 = n3(vGP * 1.9), n2 = n3(vGP * 0.31), n3v = n3(vGP * 0.045), n4 = n3(vGP * 0.004);
          float grain = 0.82 + 0.18 * n1 + 0.14 * (n2 - 0.5);
          vec3 snow = mix(vec3(0.80, 0.84, 0.90), vec3(0.93, 0.95, 0.98), n2) * (0.94 + 0.06 * n1);
          vec3 rock = mix(vec3(0.20, 0.19, 0.19), vec3(0.42, 0.40, 0.37), n3v) * (0.75 + 0.5 * n1);
          rock = mix(rock, vec3(0.30, 0.27, 0.24), smoothstep(0.4, 0.7, n4));   // strata of a warmer stone
          float snowy = smoothstep(0.80, 0.93, flatness + 0.12 * (n2 - 0.5) + 0.05 * (n3v - 0.5));
          vec3 col = mix(rock, snow, snowy);
          // the waterline: wet, dark, a little rime above it
          float wet = 1.0 - smoothstep(0.0, 2.2, alt - (${WATER_LEVEL.toFixed(1)}) - 0.0);
          col = mix(col, vec3(0.16, 0.17, 0.17) * (0.8 + 0.4 * n1), wet * 0.85);
          // under the dome: a lawn with soil showing through, darker where it is trodden
          float lawn = uDome * (1.0 - smoothstep(uDome * 0.97, uDome, arc));
          vec3 grass = mix(vec3(0.16, 0.30, 0.12), vec3(0.32, 0.46, 0.18), n2) * (0.8 + 0.35 * n1);
          grass = mix(grass, vec3(0.30, 0.24, 0.17), smoothstep(0.62, 0.75, n3v) * 0.7);
          col = mix(col, grass, lawn);
          diffuseColor.rgb = col * grain;
        }`,
      );
  };
  material.needsUpdate = true;
}
