/** Keep depth precision at overview distance without clipping a nearby inspection target. */
export function clippingNear(clearance, focusDistance) {
  return Math.max(0.005, Math.min(15, clearance * 0.02, focusDistance * 0.02));
}
