/** keys: shortcuts by physical key, so they work with any keyboard layout (Russian ЦФЫВ is still WASD). */
const BY_CODE = {
  KeyW: "w", KeyA: "a", KeyS: "s", KeyD: "d", KeyQ: "q", KeyE: "e",
  KeyF: "f", KeyL: "l", KeyM: "m", KeyC: "c", KeyH: "h",
};

export function logicalKey(e) {
  return BY_CODE[e.code] || e.key.toLowerCase();
}
