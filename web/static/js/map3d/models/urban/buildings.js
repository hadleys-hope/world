/** Architectural facade shader: windows, recessed reveals, curtains, brick mortar and rooftop seams.
 * Real geometry handles silhouettes; derivative filtering prevents moire at city/orbit distances. */
import * as T from "three";
import { state } from "../../state.js";
import { instances, chunkedInstances, lifeMaterial } from "../life.js";
import { Model, roofPlant, Batches, palette, planYaw } from "./kit.js";
export function facadeMaterial(env) {
  return new T.ShaderMaterial({
    extensions: { derivatives: true },
    uniforms: env,
    vertexShader: `attribute vec3 aCol,aTint;attribute float aFacade;varying float vFacade; varying vec3 vP,vN,vW,vC,vUp; varying float vSeed;
 void main(){vFacade=aFacade;vec3 scale=vec3(length(instanceMatrix[0].xyz),length(instanceMatrix[1].xyz),length(instanceMatrix[2].xyz));vP=position*scale;
 vec4 w=modelMatrix*instanceMatrix*vec4(position,1.);vW=w.xyz;vN=normalize(mat3(modelMatrix)*mat3(instanceMatrix)*normal);vUp=normalize(mat3(modelMatrix)*instanceMatrix[1].xyz);vC=aCol*aTint;vSeed=dot(instanceMatrix[3].xyz,vec3(.013,.031,.019));gl_Position=projectionMatrix*viewMatrix*w;}`,
    fragmentShader: `varying float vFacade;uniform vec3 uSun; varying vec3 vP,vN,vW,vC,vUp; varying float vSeed;
 float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7))+vSeed)*43758.5453);}
 void main(){vec3 n=normalize(vN),view=normalize(cameraPosition-vW),sun=normalize(uSun);float roof=step(.65,abs(dot(n,normalize(vUp))));
 // Pick the local wall coordinate without needing one draw call for each facade.
 float along=abs(vP.x)>abs(vP.z)*.80?vP.z:vP.x;
 vec2 uv=vec2(along/2.25,vP.y/3.15),f=fract(uv),aa=max(fwidth(uv),vec2(.003));
 float window=(smoothstep(.13-aa.x,.13+aa.x,f.x)-smoothstep(.87-aa.x,.87+aa.x,f.x))*(smoothstep(.25-aa.y,.25+aa.y,f.y)-smoothstep(.82-aa.y,.82+aa.y,f.y))*(1.-roof);
 float reveal=(step(.09,f.x)*step(f.x,.91)*step(.20,f.y)*step(f.y,.86))*(1.-roof);
 float brickY=vP.y/.24;vec2 mortar=fract(vec2(along/.55+mod(floor(brickY),2.)*.5,brickY));float detail=1.-smoothstep(.02,.2,length(fwidth(vP)));
 float joint=(1.-step(.06,min(mortar.x,mortar.y)))*detail;
 float floorBand=(1.-smoothstep(.02,.055,min(f.y,1.-f.y)))*(1.-roof);
 vec3 wall=vC*(.94-.18*joint-.24*floorBand);wall=mix(wall,vec3(.12,.17,.19),reveal*.85);
 float fres=pow(1.-abs(dot(n,view)),3.);float reflected=pow(max(dot(reflect(-sun,n),view),0.),64.);
 float occupied=step(.32,hash(floor(uv)));float curtain=step(.5,fract(f.x*6.+hash(floor(uv))))*.07;
 float day=smoothstep(-.12,.3,dot(normalize(vUp),sun));
 vec3 glass=mix(vec3(.07,.18,.23),vec3(.47,.68,.76),fres)*(.4+.6*day)+reflected*vec3(1.,.85,.6)+curtain;
 glass+=occupied*(1.-day)*vec3(.95,.58,.22)*.8;
 float mullion=(1.-smoothstep(.01,.025,abs(f.x-.5)))*detail;glass*=1.-mullion*.6;
 vec3 lit=wall*(.3+.65*max(dot(n,sun),0.)*day+.15*(1.-day));
 gl_FragColor=vec4(pow(max(mix(lit,glass,window*vFacade),vec3(0.)),vec3(1./2.2)),1.);}`,
  });
}
export function buildHomes(body, R, plan, point, env) {
  const items = [],
    map = [],
    plants = [],
    balconies = [];
  let global = 0;
  for (const c of plan.cities)
    for (let i = 0; i < c.houses; i++, global++) {
      const x = c.at[0] + c.x[i],
        z = c.at[1] + c.y[i],
        p = point(x, z, 0),
        seed = Math.imul(i + 31, 2654435761) >>> 0,
        floors = 1 + (seed % 10);
      // Preserve the server's footprint and ID: height variation does not move a simulated house.
      const height = floors * 3.15 + 0.7,
        yaw = planYaw(point, x, z, Math.atan2(c.y[i], c.x[i]) + Math.PI / 2);
      items.push({
        n: p.clone().normalize().toArray(),
        h: p.length() - R,
        s: 1,
        sy: height / 5,
        yaw,
        tint: [
          [1, 0.95, 0.85],
          [0.8, 0.9, 1],
          [0.94, 0.81, 0.67],
          [0.87, 0.92, 0.88],
        ][seed % 4],
      });
      map.push({
        city: c.id,
        index: i,
        id: c.first_id + i,
        floors,
        x,
        z,
        height,
      });
      plants.push({
        n: p.clone().normalize().toArray(),
        h: p.length() - R + height + 0.15,
        s: 1,
        yaw,
      });
      if (seed % 3 !== 0)
        for (let floor = 1; floor < floors; floor++)
          balconies.push({
            n: p.clone().normalize().toArray(),
            h: p.length() - R + floor * 3.15,
            s: 1,
            yaw,
          });
    }
  const m = new Model()
    .box(0, 2.5, 0, 8.6, 5, 10.5, 0xb9b5a7, 1)
    .box(0, 4.98, 0, 9, 0.08, 10.9, 0x46515a);
  // Only the main envelope and service riser are submitted at orbital distances.
  m.box(4.34, 2.5, 3.8, 0.11, 5, 0.18, palette.metal);
  const mesh = instances(m.finish(), facadeMaterial(env), items, R);
  mesh.name = "Klyaksa · all 5010 homes";
  mesh.userData.homes = map;
  state.klyaksaHouses = mesh;
  state.klyaksaHouseMeta = map;
  body.add(mesh);
  const ao = new T.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    side: T.DoubleSide,
    vertexShader: `varying vec2 vP;void main(){vP=position.xz/vec2(8.,9.);gl_Position=projectionMatrix*modelViewMatrix*instanceMatrix*vec4(position,1.);}`,
    fragmentShader: `varying vec2 vP;void main(){float d=max(abs(vP.x),abs(vP.y));gl_FragColor=vec4(.015,.025,.025,(1.-smoothstep(.45,1.,d))*.23);}`,
  });
  body.add(
    instances(
      new T.PlaneGeometry(16, 18).rotateX(-Math.PI / 2),
      ao,
      items.map((i) => ({ ...i, sy: 1, h: i.h + 0.035 })),
      R,
    ),
  );
  state.klyaksaBaseTint = Float32Array.from(items.flatMap((i) => i.tint));
  const roofDetails = () => {
    const m = new Model();
    for (const z of [-5.35, 5.35])
      m.box(0, 0.35, z, 9, 0.7, 0.15, palette.white);
    for (const x of [-4.42, 4.42])
      m.box(x, 0.35, 0, 0.15, 0.7, 10.8, palette.white);
    for (const x of [-4.48, 4.48])
      for (const z of [-5.43, 5.43])
        m.cyl(x, 0.55, z, 0.07, 1.1, palette.metal, 0.07, 5);
    m.parts.push([roofPlant().scale(0.8, 0.8, 0.8), null]);
    return m.finish();
  };
  const root = chunkedInstances(
    roofDetails,
    lifeMaterial(env, { indoor: 1 }),
    plants,
    R,
    { cell: 0.025, maxDist: 700 },
  );
  body.add(root);
  state.klyaksaLod.push(root);
  const balcony = () => {
    const m = new Model()
      .box(0, 0, 5.75, 2.8, 0.16, 1.1, palette.concrete)
      .box(0, 0.95, 6.25, 2.8, 0.08, 0.08, palette.metal);
    for (let k = -3; k <= 3; k++)
      m.box(k * 0.42, 0.47, 6.25, 0.035, 0.95, 0.035, palette.metal);
    return m.finish();
  };
  const entrance = () => {
    const m = new Model()
      .box(0, 1.1, 5.28, 1.2, 2.2, 0.08, palette.dark)
      .box(0.42, 1, 5.34, 0.06, 0.2, 0.05, palette.brass);
    for (let k = 0; k < 3; k++)
      m.box(
        0,
        0.08 + k * 0.08,
        6.4 - k * 0.35,
        2,
        0.16 + k * 0.16,
        0.4,
        palette.concrete,
      );
    return m.finish();
  };
  const doors = chunkedInstances(
    entrance,
    lifeMaterial(env, { indoor: 1 }),
    items.map((i) => ({ ...i, sy: 1 })),
    R,
    { cell: 0.02, maxDist: 500 },
  );
  body.add(doors);
  state.klyaksaLod.push(doors);
  const detail = chunkedInstances(
    balcony,
    lifeMaterial(env, { indoor: 1 }),
    balconies,
    R,
    { cell: 0.02, maxDist: 420 },
  );
  body.add(detail);
  state.klyaksaLod.push(detail);
}
export function civicGeometry(kind) {
  const m = new Model();
  if (kind === "tank") {
    for (let k = 0; k < 4; k++) {
      const a = (k * Math.PI) / 2 + 0.78;
      m.beam(
        [Math.cos(a) * 6, 0, Math.sin(a) * 6],
        [Math.cos(a) * 4, 22, Math.sin(a) * 4],
        0.45,
      );
      m.beam(
        [Math.cos(a) * 6, 1, Math.sin(a) * 6],
        [Math.cos(a + Math.PI / 2) * 4, 18, Math.sin(a + Math.PI / 2) * 4],
        0.15,
      );
    }
    m.cyl(0, 20.2, 0, 7, 0.4, palette.metal)
      .cyl(0, 28.4, 0, 7.5, 0.6, palette.white)
      .cyl(0, 18.5, 0, 1, 8);
    for (let y = 0; y < 29; y++) m.box(6, y, 0, 0.7, 0.08, 0.18, palette.metal);
  } else if (kind === "reactor") {
    m.cyl(-12, 12, 0, 11, 24, palette.white)
      .cyl(-12, 25, 0, 11, 3, palette.metal, 6, 20)
      .box(12, 7, 0, 24, 14, 22, palette.concrete);
    for (let k = 0; k < 7; k++) {
      m.beam([-19 + k * 5, 2, 14], [-19 + k * 5, 2, 25], 0.55, 0x869fa6);
      m.cyl(-19 + k * 5, 5, 25, 0.55, 6, 0x869fa6);
      m.box(3 + k * 3, 14.5, 0, 1.3, 1, 21, palette.metal);
    }
    for (const z of [-10, 10]) m.cyl(30, 12, z, 6, 24, palette.metal, 4, 16);
  } else if (kind === "church") {
    m.box(0, 6, 0, 20, 12, 30, palette.white).box(
      0,
      16,
      10,
      6,
      20,
      6,
      palette.concrete,
    );
    m.parts.push([
      new T.ConeGeometry(6, 12, 4).rotateY(Math.PI / 4).translate(0, 31, 10),
      palette.dark,
    ]);
    m.box(0, 39, 10, 0.3, 5, 0.3, palette.brass).box(
      0,
      39.5,
      10,
      2.3,
      0.3,
      0.3,
      palette.brass,
    );
  } else {
    const tall = kind === "bank",
      h = tall ? 65 : kind === "hospital" ? 16 : 9,
      w = tall ? 15 : 28,
      d = tall ? 17 : 20;
    m.box(0, h / 2, 0, w, h, d, tall ? palette.glass : palette.concrete, 1).box(
      0,
      1,
      0,
      w + 2,
      2,
      d + 2,
      palette.dark,
    );
    for (let y = 3; y < h; y += 3.2)
      m.box(0, y, 0, w + 0.4, 0.23, d + 0.4, palette.white);
    for (let x = -w / 2 + 1.5; x < w / 2; x += 3)
      for (const z of [-d / 2 - 0.04, d / 2 + 0.04])
        m.box(x, h / 2, z, 0.12, h, 0.16, palette.brass);
    m.box(0, 3, d / 2 + 2, w * 0.65, 0.4, 4, palette.metal);
    if (kind === "hospital")
      m.box(0, h + 2, 0, 1, 5, 0.4, 0xd7544b).box(
        0,
        h + 2,
        0,
        4,
        1,
        0.4,
        0xd7544b,
      );
    if (kind === "network")
      for (let k = 0; k < 5; k++)
        m.box(-9 + k * 4, h + 1, 0, 2, 2, 3, palette.dark);
    if (kind === "garage" || kind === "fire")
      for (let k = -1; k <= 1; k++)
        m.box(k * 8, 2.7, 10.1, 6, 5, 0.15, palette.dark);
    if (kind === "garage" || kind === "fire") {
      for (let x = -13; x <= 13; x += 1.2)
        m.box(x, h + 0.12, 0, 0.08, 0.24, 20, palette.metal);
      for (let bay = -1; bay <= 1; bay++)
        for (let row = 0; row < 12; row++)
          m.box(bay * 8, 0.5 + row * 0.4, 10.2, 5.8, 0.06, 0.08, palette.metal);
      for (const x of [-12, -4, 4, 12])
        m.box(
          x,
          2.5,
          10.4,
          0.45,
          5,
          0.5,
          kind === "fire" ? 0xc45b43 : palette.brass,
        );
    }
    if (kind === "library" || kind === "coworking") {
      for (let x = -11; x <= 11; x += 4.4)
        m.box(x, 1.5, 12, 0.35, 3, 0.35, palette.white);
      m.box(0, 3.1, 12, 25, 0.2, 4, palette.white);
      for (let k = 0; k < 3; k++)
        m.box(-9 + k * 9, h + 0.3, 0, 5, 0.6, 5, palette.green);
    }
    if (kind === "sports")
      m.parts.push([
        new T.SphereGeometry(14, 20, 10, 0, Math.PI * 2, 0, Math.PI / 2)
          .scale(1, 0.38, 0.72)
          .translate(0, h, 0),
        palette.metal,
      ]);
    if (kind === "cafe") {
      for (let x = -10; x <= 10; x += 2)
        m.box(x, 3, 12, 1.9, 0.15, 4, x % 4 === 0 ? 0xd0a468 : palette.white);
      for (let x = -9; x <= 9; x += 6)
        m.box(x, 0.8, 13, 2, 0.12, 1.2, palette.wood).box(
          x,
          0.4,
          13,
          0.12,
          0.8,
          0.12,
          palette.metal,
        );
    }
    if (tall) m.box(3, h + 4, 0, 7, 8, 10, palette.metal);
  }
  return m.finish();
}
