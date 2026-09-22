/** Feature regression over the real local API; no mocked driving commands. */
import assert from 'node:assert/strict';
import { resolve } from 'node:path';

export async function verifyExploration(page, root) {
  await page.evaluate(async()=>{
    const {state:s}=await import('/static/js/map3d/state.js');
    await fetch('/cmd',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cmd:'speed',value:0,token:s.ADMIN})});
  });
  await page.keyboard.press('0');
  assert.equal(await page.locator('[data-planet="-1"]').getAttribute('aria-pressed'), 'true');
  const system = await page.evaluate(async () => {
    const { state: s } = await import('/static/js/map3d/state.js');
    s.composer.render();
    return { count: s.solarSystem.specs.length, radius: s.RP, worldHidden: !s.world.visible,
      star: !!s.solarSystem.star.userData.photosphere, ocean: s.G.cfg.ocean_radii };
  });
  assert.deepEqual(system, {count: 4, radius: 4000, worldHidden: true, star: true, ocean: [1080,1380]});
  await page.screenshot({path:resolve(root,'test-results/system.png')});
  for (let i = 0; i < 4; i++) {
    await page.locator(`[data-planet="${i}"]`).click();
    assert.equal(await page.locator(`[data-planet="${i}"]`).getAttribute('aria-pressed'), 'true');
    await page.evaluate(async () => {
      const { state: s } = await import('/static/js/map3d/state.js');
      s.composer.render();
    });
    await page.screenshot({path:resolve(root,`test-results/planet-${i}.png`)});
  }
  const orbits = await page.evaluate(async () => {
    const { state: s } = await import('/static/js/map3d/state.js');
    const { updateSolarSystem } = await import('/static/js/map3d/models/solar-system.js');
    // Sample two epochs deterministically without changing the server simulation.
    const saved = s.S, ss = s.solarSystem;
    const local = s.camera.position.clone().sub(ss.bodies[3].position);
    const before = ss.bodies.map(b=>b.position.clone());
    s.S = {...saved, paused:true, t:saved.t+120};
    updateSolarSystem(performance.now(),0);
    const movement = ss.bodies.map((b,i)=>b.position.distanceTo(before[i]));
    const followError = local.distanceTo(s.camera.position.clone().sub(ss.bodies[3].position));
    const paused = ss.bodies[0].position.clone();
    updateSolarSystem(performance.now()+500,0);
    const pauseDrift = paused.distanceTo(ss.bodies[0].position);
    const homeOrbit = ss.bodies[2].position.distanceTo(ss.star.position);
    s.S = saved; updateSolarSystem(performance.now(),0);
    return {movement, followError, pauseDrift, homeOrbit};
  });
  assert.ok(orbits.movement[0]>100 && orbits.movement[1]>100 && orbits.movement[3]>100);
  assert.ok(orbits.followError<1e-6 && orbits.pauseDrift===0);
  // Acheron is the floating origin, but still orbits relative to the star.
  assert.ok(Math.abs(orbits.homeOrbit-74000)<200);
  console.log('Orbits:', orbits);

  await page.keyboard.press('Home');
  assert.equal(await page.locator('[data-planet="2"]').getAttribute('aria-pressed'), 'true');
  await page.evaluate(async () => {
    const { state:s }=await import('/static/js/map3d/state.js');
    s.camera.position.copy(s.flyAnim.to); s.controls.target.copy(s.flyAnim.tto);
    s.camera.lookAt(s.controls.target); s.flyAnim=null;
  });
  await page.keyboard.press('Shift');
  assert.match(await page.locator('#camera-mode').innerText(), /FREE FLIGHT/);
  await page.keyboard.down('w');
  const moved = await page.evaluate(async () => {
    const {state:s}=await import('/static/js/map3d/state.js');
    const {updateCameraMotion}=await import('/static/js/map3d/camera.js');
    const before=s.camera.position.clone(), start=performance.now();
    s.cameraLast=start;
    for(let i=1;i<=30;i++)updateCameraMotion(start+i*16);
    return before.distanceTo(s.camera.position);
  });
  await page.keyboard.up('w');
  assert.ok(moved>10,'Free flight must move at a useful speed');
  await page.mouse.move(600,400);
  await page.mouse.wheel(0,-30);
  assert.match(await page.locator('#camera-mode').innerText(), /FREE FLIGHT/);
  await page.keyboard.press('Shift');
  assert.match(await page.locator('#camera-mode').innerText(), /PLANET ORBIT/);

  const physics=await page.evaluate(async()=>{
    const {chassisState,stepChassis}=await import('/static/js/map3d/physics/chassis.js');
    const flat=(mu=.92)=>()=>({height:0,mu,rolling:.018,road:true,ice:mu<.2});
    const run=(d,input,seconds,ground=flat(),blocked=()=>false)=>{
      for(let i=0;i<seconds*120;i++)stepChassis(d,input,1/120,ground,blocked);
      return d;
    };
    const spawn=()=>Object.assign(chassisState(700,0,0),{alt:.055});
    const idle=run(spawn(),{},15), car=run(spawn(),{forward:true},12);
    const speed=car.v,gear=car.gear;
    run(car,{back:true},3);const braked=car.v;
    run(car,{back:true},10);const reverse=car.v;
    const ice=run(spawn(),{forward:true},5,flat(.14)),dry=run(spawn(),{forward:true},5);
    const collision=run(spawn(),{forward:true},5,flat(),()=>true);
    const jump=spawn();jump.alt=8;run(jump,{},.5);const falling=jump.alt<8;run(jump,{},10);
    const steering=run(spawn(),{forward:true,left:true},5);
    return {speed,gear,braked,reverse,ice:ice.v,dry:dry.v,collision:collision.distance,
      falling,landed:jump.alt,idle:idle.vertical,steering:steering.heading,
      finite:[idle,car,ice,dry,collision,jump,steering].every(d=>Object.values(d).filter(v=>typeof v==='number').every(Number.isFinite))};
  });
  assert.ok(physics.finite && physics.speed>10 && physics.gear>1 && physics.braked<physics.speed);
  assert.ok(physics.reverse<-.5 && physics.ice<physics.dry && physics.collision===0);
  assert.ok(physics.falling && Math.abs(physics.landed)<.3 && Math.abs(physics.idle)<.01 && Math.abs(physics.steering)>.1);
  console.log('Chassis:',physics);

  // Select a real rendered rover through its canvas hit target.
  const screen=await page.evaluate(async()=>{
    const {state:s}=await import('/static/js/map3d/state.js');
    const {focusPoint}=await import('/static/js/map3d/camera.js');
    const rover=s.rovers['transit-1'].g;
    focusPoint(rover.position,18);
    s.camera.position.copy(s.flyAnim.to);s.controls.target.copy(s.flyAnim.tto);
    s.camera.lookAt(s.controls.target);s.flyAnim=null;
    s.renderer.render(s.scene,s.camera);
    const p=rover.position.clone().addScaledVector(rover.position.clone().normalize(),1.5).project(s.camera);
    const r=s.renderer.domElement.getBoundingClientRect();
    return {x:r.left+(p.x+1)*r.width/2,y:r.top+(1-p.y)*r.height/2};
  });
  await page.mouse.click(screen.x,screen.y);
  await page.locator('[data-drive="transit-1"]').waitFor();
  await page.locator('[data-drive="transit-1"]').click();
  await page.waitForFunction(()=>!document.getElementById('driving-hud').hidden, null, {polling:100});
  const initial=await page.evaluate(async()=>{
    const {state:s}=await import('/static/js/map3d/state.js');
    return {x:s.drive.x,y:s.drive.y};
  });
  await page.keyboard.down('w');
  for(let i=0;i<16;i++){
    await page.waitForTimeout(50);
    await page.evaluate(async()=>{
      const {updateDriving}=await import('/static/js/map3d/driving.js');
      updateDriving(.05,performance.now());
    });
  }
  await page.keyboard.up('w');
  const driven=await page.evaluate(async()=>{
    const {state:s}=await import('/static/js/map3d/state.js');
    const {sendDriverPose}=await import('/static/js/map3d/driving.js');
    await sendDriverPose(true);
    const server=await (await fetch('/state')).json(),r=server.rovers.find(r=>r.name==='transit-1');
    return {x:s.drive.x,y:s.drive.y,rpm:s.drive.rpm,server:r,paused:server.paused};
  });
  assert.ok(Math.hypot(driven.x-initial.x,driven.y-initial.y)>.1);
  assert.ok(driven.paused && driven.server.manual && driven.server.state==='DRIVING', JSON.stringify(driven));
  assert.ok(Math.hypot(driven.x-driven.server.x,driven.y-driven.server.y)<.01);
  await page.keyboard.press('Escape');
  await page.waitForFunction(()=>document.getElementById('driving-hud').hidden, null, {polling:100});
  const released=await page.evaluate(async()=>{
    const s=await (await fetch('/state')).json();return s.rovers.find(r=>r.name==='transit-1');
  });
  assert.equal(released.state,'PARKED');assert.equal(released.velocity,0);
  // Software GPU readbacks can exceed the live lease; capture after parking.
  await page.evaluate(async()=>{const {state:s}=await import('/static/js/map3d/state.js');s.renderer.render(s.scene,s.camera);});
  await page.screenshot({path:resolve(root,'test-results/parked-vehicle.png')});
  console.log('Canvas selection, authenticated driving while paused, pose sync and parking: passed');
}
