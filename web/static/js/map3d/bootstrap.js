/** bootstrap: procedural colony viewer. */
import { state } from './state.js';
import { frame } from './render/frame.js';
import { loadGeom, poll } from './ui/controls.js';
import { flyTo } from './ui/inspection.js';
export function initialize() {
  if (new URLSearchParams(location.search).has('inspect')) window.HH = {
    camera: state.camera,
    controls: state.controls,
    scene: state.scene,
    renderer: state.renderer,
    flyTo,
    houseDetails: state.houseDetails,
    utilityGroup: state.utilityGroup,
    get geometry() {
      return state.G;
    },
    get state() {
      return state.S;
    }
  };
  loadGeom().then(() => {
    poll();
    frame();
  });
}
