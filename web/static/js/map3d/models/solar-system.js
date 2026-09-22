/** models/solar-system: procedural colony viewer. */
import { state } from "../state.js";
import { createStar } from "./star.js";
import {
  activeCentre,
  navigationHUD,
  nearClip,
  surfaceClearance,
} from "../camera.js";
import { stopDriving } from "../driving.js";
import { textSprite } from "../render/textures.js";
import { flyTo, renderInfo } from "../ui/inspection.js";
import * as THREE from "three";

export function buildSolarSystem() {
  const specs = [
    {
      name: "HEPHAESTUS",
      radius: 4200,
      orbit: 27000,
      period: 2400,
      phase: 0.4,
      color: 0xce8949,
      climate: "+310 °C / ACID CYCLONES",
      kind: 0,
    },
    {
      name: "RUSSET",
      radius: 3700,
      orbit: 48000,
      period: 5700,
      phase: 2.5,
      color: 0xa55738,
      climate: "+85 °C / DUST STORMS",
      kind: 1,
    },
    {
      name: "ACHERON · LV–426",
      radius: state.RP,
      orbit: 74000,
      period: 10800,
      phase: 4.2,
      color: 0x8dabb9,
      climate: "−55 °C / FROZEN OCEAN",
      kind: 2,
    },
    {
      name: "NIX",
      radius: 2800,
      orbit: 101000,
      period: 17200,
      phase: 5.8,
      color: 0x81bed2,
      climate: "−180 °C / ICE DWARF",
      kind: 3,
    },
  ];
  const star = createStar();
  state.scene.add(star);
  const bodies = specs.map((s, i) => {
    const body = new THREE.Group();
    if (i === 2) return body;
    const geom = new THREE.SphereGeometry(s.radius, 128, 96),
      mat = new THREE.ShaderMaterial({
        uniforms: {
          uTime: { value: 0 },
          uKind: { value: s.kind },
          uLight: { value: new THREE.Vector3(1, 0.2, 0) },
        },
        vertexShader: `varying vec3 vN;varying vec3 vP;void main(){vN=normal;vP=position;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`,
        fragmentShader: `uniform float uTime,uKind;uniform vec3 uLight;varying vec3 vN,vP;
 float hash(vec3 p){return fract(sin(dot(p,vec3(127.1,311.7,74.7)))*43758.5453);}
 float noise(vec3 p){vec3 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(mix(hash(i),hash(i+vec3(1,0,0)),f.x),mix(hash(i+vec3(0,1,0)),hash(i+vec3(1,1,0)),f.x),f.y),mix(mix(hash(i+vec3(0,0,1)),hash(i+vec3(1,0,1)),f.x),mix(hash(i+vec3(0,1,1)),hash(i+vec3(1,1,1)),f.x),f.y),f.z);}
 float n(vec3 p){float v=0.,a=.53;for(int j=0;j<5;j++){v+=noise(p)*a;p=p*2.03+vec3(9.7,3.4,1.2);a*=.5;}return v;}
 void main(){vec3 p=normalize(vP);float lon=atan(p.z,p.x),lat=asin(p.y);float bands=sin(lat*32.+(n(p*8.+vec3(uTime*.004,0.,0.))-.5)*12.+uTime*.03);float turbulence=n(p*8.+uTime*.001);vec3 col;
 if(uKind<.5){float storm=sin(length(vec2((lon-.4)*cos(lat),lat-.2))*80.-atan(lat-.2,lon-.4)*5.+uTime*.3);col=mix(vec3(.30,.10,.04),vec3(.90,.64,.27),.5+.22*bands+.18*turbulence);col+=vec3(.25,.13,.05)*storm*exp(-12.*length(vec2(lon-.4,lat-.2)));}
 else if(uKind<1.5){float ridges=pow(1.-abs(n(p*23.)*2.-1.),5.);col=mix(vec3(.19,.08,.05),vec3(.67,.31,.14),n(p*4.));col+=vec3(.18,.11,.06)*ridges;float dust=smoothstep(.5,.8,n(p*11.+vec3(uTime*.01,0.,0.)));col=mix(col,vec3(.74,.5,.27),dust*.45);}
 else{vec3 warp=p*13.+vec3(n(p*7.),n(p*7.+9.),n(p*7.+21.))*3.;float crack=1.-smoothstep(.009,.035,abs(n(warp)-.5));float frost=smoothstep(.38,.68,n(p*8.)+abs(p.y)*.16);col=mix(vec3(.20,.43,.57),vec3(.83,.91,.94),frost);col=mix(col,vec3(.12,.29,.39),crack*.65);col+=noise(p*400.)*.045;}
 float light=max(0.,dot(normalize(vN),normalize(uLight)));gl_FragColor=vec4(col*(.16+.84*light),1.);}`,
      });
    body.add(new THREE.Mesh(geom, mat));
    body.userData.surface = mat;
    const atmosphere = new THREE.Mesh(
      new THREE.SphereGeometry(s.radius * 1.025, 64, 48),
      new THREE.MeshBasicMaterial({
        color: s.color,
        transparent: true,
        opacity: i === 0 ? 0.19 : 0.09,
        side: THREE.BackSide,
        depthWrite: false,
      }),
    );
    body.add(atmosphere);
    state.scene.add(body);
    return body;
  });
  const orbitGroup = new THREE.Group();
  for (const s of specs) {
    const pts = [];
    for (let i = 0; i <= 256; i++) {
      const a = (i * Math.PI) / 128;
      pts.push(
        new THREE.Vector3(
          Math.cos(a) * s.orbit,
          Math.sin(a) * s.orbit * 0.07,
          Math.sin(a) * s.orbit,
        ),
      );
    }
    orbitGroup.add(
      new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(pts),
        new THREE.LineBasicMaterial({
          color: 0x71827f,
          transparent: true,
          opacity: 0.45,
        }),
      ),
    );
  }
  state.scene.add(orbitGroup);
  const labels = specs.map((s, i) => {
    const label = textSprite(i + 1 + "  " + s.name, "#c7d5d1");
    label.scale.multiplyScalar(700);
    label.material.depthTest = false;
    label.renderOrder = 30;
    state.scene.add(label);
    return label;
  });
  state.solarSystem = {
    specs,
    bodies,
    star,
    orbitGroup,
    labels,
    epoch: 0,
    lastAt: performance.now(),
    lastCentre: new THREE.Vector3(),
  };
  document
    .querySelectorAll("[data-planet]")
    .forEach((b) => (b.onclick = () => switchPlanet(+b.dataset.planet)));
  updateSolarSystem(performance.now(), 0);
  navigationHUD();
}

export function updateSolarSystem(now, dt) {
  if (!state.solarSystem) return;
  state.solarSystem.star.userData.photosphere.uniforms.time.value = now / 1000;
  const ss = state.solarSystem,
    time =
      (state.S?.t || 0) +
      (state.S && !state.S.paused
        ? Math.min(1, (now - state.lastPoll) / 1000) * state.S.speed
        : 0),
    positions = ss.specs.map((s) => {
      const a = s.phase + (time / s.period) * Math.PI * 2;
      return new THREE.Vector3(
        Math.cos(a) * s.orbit,
        Math.sin(a) * s.orbit * 0.07,
        Math.sin(a) * s.orbit,
      );
    }),
    home = positions[2];
  const before = activeCentre().clone();
  ss.star.position.copy(home).negate();
  ss.orbitGroup.position.copy(ss.star.position);
  ss.bodies.forEach((b, i) => {
    b.position.copy(positions[i]).sub(home);
    if (b.userData.surface) {
      b.userData.surface.uniforms.uTime.value = time;
      b.userData.surface.uniforms.uLight.value
        .copy(positions[i])
        .negate()
        .normalize();
    }
  });
  if (state.activeBody !== 2 || state.systemView) {
    const delta = activeCentre().clone().sub(before);
    state.camera.position.add(delta);
    state.controls.target.add(delta);
    if (state.flyAnim) {
      state.flyAnim.from.add(delta);
      state.flyAnim.to.add(delta);
      state.flyAnim.tfrom.add(delta);
      state.flyAnim.tto.add(delta);
    }
  }
  ss.orbitGroup.visible = state.systemView || surfaceClearance() > state.RP * 2;
  state.world.visible = state.activeBody === 2 && !state.systemView;
  const detail =
    state.world.visible &&
    state.camera.position.distanceTo(new THREE.Vector3(0, state.RP, 0)) < 6000;
  if (state.landscapePatch) state.landscapePatch.visible = detail;
  state.planetMat.uniforms.uDetail.value = detail ? 1 : 0;
  ss.labels.forEach((l, i) => {
    l.visible = state.systemView;
    l.position
      .copy(ss.bodies[i].position)
      .add(new THREE.Vector3(0, ss.specs[i].radius + 4500, 0));
  });
  ss.epoch = time;
}

export async function switchPlanet(index) {
  if (state.drive) await stopDriving();
  if (!state.solarSystem) return;
  state.clearInput();
  if (document.pointerLockElement) document.exitPointerLock();
  state.systemView = index < 0;
  if (!state.systemView) state.activeBody = THREE.MathUtils.clamp(index, 0, 3);
  state.cameraMode = "orbit";
  state.selected = null;
  renderInfo();
  const center = activeCentre().clone(),
    r = state.solarSystem.specs[state.activeBody].radius;
  state.camera.up.set(0, 1, 0);
  const offset = state.systemView
    ? new THREE.Vector3(0, 210000, 110000)
    : state.solarSystem.star.position
        .clone()
        .sub(center)
        .normalize()
        .multiplyScalar(0.8)
        .add(new THREE.Vector3(0.35, 0.5, 0.45))
        .normalize()
        .multiplyScalar(r * 3.0);
  state.camera.position.copy(center).add(offset);
  state.controls.target.copy(center);
  state.camera.lookAt(center);
  state.flyAnim = null;
  state.world.visible = state.activeBody === 2 && !state.systemView;
  state.scene.fog.density = 0;
  updateSolarSystem(performance.now(), 0);
  nearClip();
  navigationHUD();
  document
    .querySelectorAll("[data-planet]")
    .forEach((b) =>
      b.setAttribute("aria-pressed", String(+b.dataset.planet === index)),
    );
}

export function goHome() {
  if (state.drive) return;
  state.activeBody = 2;
  state.systemView = false;
  state.world.visible = true;
  state.cameraMode = "orbit";
  flyTo(0, 0, 1300);
  navigationHUD();
}

export function initialize() {
  state.solarSystem = null;
}
