/** Ordered initialization; no bundler or Node runtime is needed in production. */
import { initialize as initUiControls } from './ui/controls.js';
import { initialize as initGeometryPlanet } from './geometry/planet.js';
import { initialize as initRenderFlows } from './render/flows.js';
import { initialize as initRenderTextures } from './render/textures.js';
import { initialize as initRenderScene } from './render/scene.js';
import { initialize as initCamera } from './camera.js';
import { initialize as initRenderSky } from './render/sky.js';
import { initialize as initRenderWorld } from './render/world.js';
import { initialize as initModelsMaterials } from './models/materials.js';
import { initialize as initModelsNeighborhood } from './models/neighborhood.js';
import { initialize as initModelsHabitat } from './models/habitat.js';
import { initialize as initModelsPower } from './models/power.js';
import { initialize as initModelsCampus } from './models/campus.js';
import { initialize as initModelsOcean } from './models/ocean.js';
import { initialize as initGeometryRoads } from './geometry/roads.js';
import { initialize as initRenderStateSync } from './render/state-sync.js';
import { initialize as initUiInspection } from './ui/inspection.js';
import { initialize as initRenderFrame } from './render/frame.js';
import { initialize as initBootstrap } from './bootstrap.js';
initUiControls(); // ui/controls
initGeometryPlanet(); // geometry/planet
initRenderFlows(); // render/flows
initRenderTextures(); // render/textures
initRenderScene(); // render/scene
initCamera(); // camera
initRenderSky(); // render/sky
initRenderWorld(); // render/world
initModelsMaterials(); // models/materials
initModelsNeighborhood(); // models/neighborhood
initModelsHabitat(); // models/habitat
initModelsPower(); // models/power
initModelsCampus(); // models/campus
initModelsOcean(); // models/ocean
initGeometryRoads(); // geometry/roads
initRenderStateSync(); // render/state-sync
initUiInspection(); // ui/inspection
initRenderFrame(); // render/frame
initBootstrap(); // bootstrap
