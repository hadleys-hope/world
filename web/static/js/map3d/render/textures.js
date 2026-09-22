/** render/textures: procedural colony viewer. */
import { state } from '../state.js';
import * as THREE from 'three';
export function tex(draw) {
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  draw(c.getContext('2d'));
  return new THREE.CanvasTexture(c);
}
export function textSprite(text, color = '#d9dde6', px = 28) {
  const key = text + '|' + color + '|' + px;
  if (!state.spriteCache.has(key)) {
    const c = document.createElement('canvas');
    const x = c.getContext('2d');
    x.font = `600 ${px}px sans-serif`;
    const w = Math.ceil(x.measureText(text).width) + 16;
    c.width = w;
    c.height = px + 14;
    const x2 = c.getContext('2d');
    x2.font = `600 ${px}px sans-serif`;
    x2.fillStyle = 'rgba(10,12,18,.78)';
    x2.beginPath();
    x2.roundRect(0, 0, w, px + 14, 8);
    x2.fill();
    x2.fillStyle = color;
    x2.textBaseline = 'middle';
    x2.fillText(text, 8, (px + 14) / 2);
    state.spriteCache.set(key, {
      map: new THREE.CanvasTexture(c),
      w,
      h: px + 14
    });
  }
  const e = state.spriteCache.get(key);
  const s = new THREE.Sprite(new THREE.SpriteMaterial({
    map: e.map,
    transparent: true,
    depthTest: false
  }));
  s.scale.set(e.w / px * 4.6, 4.6 * e.h / px, 1);
  s.userData.px = px;
  return s;
}
export function retext(sprite, text, color) {
  const key = text + '|' + color + '|' + sprite.userData.px;
  if (sprite.userData.key === key) return;
  sprite.userData.key = key;
  const tmp = textSprite(text, color, sprite.userData.px);
  sprite.material.map = tmp.material.map;
  sprite.material.needsUpdate = true;
  sprite.scale.copy(tmp.scale);
}
export function initialize() {
  state.TEX = {
    dot: tex(x => {
      const g = x.createRadialGradient(32, 32, 2, 32, 32, 30);
      g.addColorStop(0, 'rgba(255,255,255,1)');
      g.addColorStop(0.5, 'rgba(255,255,255,.6)');
      g.addColorStop(1, 'rgba(255,255,255,0)');
      x.fillStyle = g;
      x.fillRect(0, 0, 64, 64);
    }),
    glow: tex(x => {
      const g = x.createRadialGradient(32, 32, 0, 32, 32, 32);
      g.addColorStop(0, 'rgba(255,240,180,.9)');
      g.addColorStop(0.3, 'rgba(255,220,120,.35)');
      g.addColorStop(1, 'rgba(255,200,80,0)');
      x.fillStyle = g;
      x.fillRect(0, 0, 64, 64);
    }),
    bang: tex(x => {
      x.fillStyle = '#e2574d';
      x.beginPath();
      x.arc(32, 32, 26, 0, 7);
      x.fill();
      x.fillStyle = '#fff';
      x.font = 'bold 40px sans-serif';
      x.textAlign = 'center';
      x.textBaseline = 'middle';
      x.fillText('!', 32, 34);
    }),
    diamond: tex(x => {
      x.fillStyle = '#ff3b3b';
      x.beginPath();
      x.moveTo(32, 4);
      x.lineTo(60, 32);
      x.lineTo(32, 60);
      x.lineTo(4, 32);
      x.closePath();
      x.fill();
      x.fillStyle = '#200';
      x.beginPath();
      x.arc(32, 32, 7, 0, 7);
      x.fill();
    }),
    bolt: tex(x => {
      x.fillStyle = '#4fd1c5';
      x.beginPath();
      x.arc(32, 32, 28, 0, 7);
      x.fill();
      x.fillStyle = '#062';
      x.beginPath();
      x.moveTo(36, 6);
      x.lineTo(18, 36);
      x.lineTo(31, 36);
      x.lineTo(27, 58);
      x.lineTo(46, 26);
      x.lineTo(33, 26);
      x.closePath();
      x.fill();
    }),
    nonet: tex(x => {
      x.fillStyle = '#d857d8';
      x.beginPath();
      x.arc(32, 32, 26, 0, 7);
      x.fill();
      x.strokeStyle = '#fff';
      x.lineWidth = 6;
      x.beginPath();
      x.moveTo(18, 18);
      x.lineTo(46, 46);
      x.moveTo(46, 18);
      x.lineTo(18, 46);
      x.stroke();
    }),
    person: tex(x => {
      x.fillStyle = '#ffffff';
      x.beginPath();
      x.arc(32, 16, 8, 0, 7);
      x.fill();
      x.beginPath();
      x.roundRect(22, 28, 20, 32, 8);
      x.fill();
    }),
    marine: tex(x => {
      x.fillStyle = '#8be05a';
      x.beginPath();
      x.arc(32, 16, 8, 0, 7);
      x.fill();
      x.beginPath();
      x.roundRect(22, 28, 20, 32, 8);
      x.fill();
      x.fillStyle = '#233';
      x.fillRect(10, 40, 44, 6);
    }),
    flame: tex(x => {
      x.fillStyle = '#ff7a30';
      x.beginPath();
      x.moveTo(32, 6);
      x.bezierCurveTo(50, 26, 50, 44, 32, 58);
      x.bezierCurveTo(14, 44, 14, 26, 32, 6);
      x.fill();
    }),
    rad: tex(x => {
      x.fillStyle = '#e8d34a';
      x.beginPath();
      x.arc(32, 32, 28, 0, 7);
      x.fill();
      x.fillStyle = '#222';
      for (let k = 0; k < 3; k++) {
        x.beginPath();
        x.moveTo(32, 32);
        x.arc(32, 32, 24, k * 2.094 + 0.35, k * 2.094 + 1.4);
        x.closePath();
        x.fill();
      }
      x.beginPath();
      x.arc(32, 32, 5, 0, 7);
      x.fill();
    }),
    steam: tex(x => {
      const g = x.createRadialGradient(32, 32, 0, 32, 32, 30);
      g.addColorStop(0, 'rgba(230,235,245,.55)');
      g.addColorStop(1, 'rgba(230,235,245,0)');
      x.fillStyle = g;
      x.fillRect(0, 0, 64, 64);
    }),
    red: tex(x => {
      const g = x.createRadialGradient(32, 32, 0, 32, 32, 30);
      g.addColorStop(0, 'rgba(255,60,60,1)');
      g.addColorStop(0.4, 'rgba(255,60,60,.5)');
      g.addColorStop(1, 'rgba(255,60,60,0)');
      x.fillStyle = g;
      x.fillRect(0, 0, 64, 64);
    })
  };
  state.spriteCache = new Map();
}
