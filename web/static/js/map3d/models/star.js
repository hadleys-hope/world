/** White stellar photosphere and corona. Visual animation uses real time. */
import * as THREE from "three";

export function createStar(radius = 8500) {
  const group = new THREE.Group();
  const material = new THREE.ShaderMaterial({
    uniforms: { time: { value: 0 } },
    vertexShader: `
      varying vec3 surface;
      void main() {
        surface = normalize(position);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: `
      uniform float time;
      varying vec3 surface;
      void main() {
        vec3 p = normalize(surface);
        float granules = sin(p.x * 110.0 + sin(p.y * 73.0 + time * .7) * 3.0)
                       * sin(p.z * 97.0 - time * .5);
        float convection = sin(p.x * 17.0 + p.y * 11.0 + time * .2)
                         * sin(p.z * 23.0 - time * .13);
        vec3 white = vec3(1.55, 1.58, 1.65);
        gl_FragColor = vec4(white * (1.0 + .09 * granules + .06 * convection), 1.0);
      }`,
    toneMapped: false,
  });
  group.add(new THREE.Mesh(new THREE.SphereGeometry(radius, 96, 64), material));
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 128;
  const ctx = canvas.getContext("2d");
  const gradient = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
  gradient.addColorStop(0, "rgba(255,255,255,1)");
  gradient.addColorStop(0.25, "rgba(230,243,255,.65)");
  gradient.addColorStop(0.5, "rgba(165,201,255,.13)");
  gradient.addColorStop(1, "rgba(140,180,255,0)");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, 128, 128);
  const corona = new THREE.Sprite(
    new THREE.SpriteMaterial({
      map: new THREE.CanvasTexture(canvas),
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      toneMapped: false,
    }),
  );
  corona.scale.setScalar(radius * 7.3);
  group.add(corona);
  group.userData.photosphere = material;
  return group;
}
