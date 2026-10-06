/** Small finite-volume Saint-Venant solver for visual river motion, not colony water accounting.
 * h_t + (hu)_s = 0; (hu)_t + (hu² + g h²/2)_s = -g h z_s - friction.
 * Hydrostatic reconstruction + Rusanov flux; CFL <= .4; fixed-size arrays; no frame allocations.
 * Sources: https://www.clawpack.org/riemann_book/html/Shallow_water.html
 * https://www.hec.usace.army.mil/confluence/rasdocs/hecras/latest/technical-reference/hydraulic-equations/shallow-water-equations
 */
export class RiverFlow {
  constructor({
    count = 160,
    length = 5000,
    bed = () => 0,
    depth = () => 8,
    inletSpeed = 1.6,
    g = 9.81,
  } = {}) {
    this.count = count;
    this.dx = length / count;
    this.g = g;
    this.inletSpeed = inletSpeed;
    this.time = 0;
    this.h = new Float64Array(count);
    this.q = new Float64Array(count);
    this.z = new Float64Array(count);
    this.initialH = new Float64Array(count);
    this.fluxH = new Float64Array(count + 1);
    this.fluxQ = new Float64Array(count + 1);
    this.correctionL = new Float64Array(count + 1);
    this.correctionR = new Float64Array(count + 1);
    this.encoded = new Uint8Array(count * 4);
    this.initialVolume = 0;
    this.boundaryVolume = 0;
    for (let i = 0; i < count; i++) {
      const s = (i + 0.5) * this.dx;
      this.z[i] = bed(s);
      this.h[i] = this.initialH[i] = depth(s);
      this.q[i] = this.h[i] * inletSpeed;
      this.initialVolume += this.h[i] * this.dx;
    }
    this.encode();
  }
  step(seconds) {
    let remaining = Math.max(0, Math.min(0.15, seconds));
    while (remaining > 1e-9) {
      let speed = 1;
      for (let i = 0; i < this.count; i++)
        speed = Math.max(
          speed,
          Math.abs(this.q[i] / this.h[i]) + Math.sqrt(this.g * this.h[i]),
        );
      const dt = Math.min(remaining, (0.4 * this.dx) / speed);
      remaining -= dt;
      this.advance(dt);
      this.time += dt;
    }
    this.encode();
  }
  advance(dt) {
    const { count: n, h, q, z, g } = this;
    for (let j = 0; j <= n; j++) {
      const l = Math.max(0, j - 1),
        r = Math.min(n - 1, j),
        hl = j === 0 ? this.initialH[0] : h[l],
        hr = j === n ? this.initialH[n - 1] : h[r];
      const ul = j === 0 ? this.inletSpeed : q[l] / h[l],
        ur = j === n ? q[r] / h[r] : q[r] / h[r];
      const top = Math.max(z[l], z[r]),
        a = Math.max(0.001, hl + z[l] - top),
        b = Math.max(0.001, hr + z[r] - top);
      const speed = Math.max(
        Math.abs(ul) + Math.sqrt(g * a),
        Math.abs(ur) + Math.sqrt(g * b),
      );
      this.fluxH[j] = 0.5 * (a * ul + b * ur - speed * (b - a));
      this.fluxQ[j] =
        0.5 *
        (a * ul * ul +
          0.5 * g * a * a +
          b * ur * ur +
          0.5 * g * b * b -
          speed * (b * ur - a * ul));
      this.correctionL[j] = 0.5 * g * (hl * hl - a * a);
      this.correctionR[j] = 0.5 * g * (hr * hr - b * b);
    }
    for (let i = 0; i < n; i++) {
      const nh = h[i] - (dt / this.dx) * (this.fluxH[i + 1] - this.fluxH[i]);
      let nq =
        q[i] -
        (dt / this.dx) *
          (this.fluxQ[i + 1] +
            this.correctionL[i + 1] -
            this.fluxQ[i] -
            this.correctionR[i]);
      // Semi-implicit Manning drag keeps the fixed visual reach dissipative.
      nq /=
        1 +
        (dt * g * 0.024 ** 2 * Math.abs(nq)) /
          Math.pow(Math.max(0.05, nh), 7 / 3);
      h[i] = Math.max(0.05, nh);
      q[i] = Number.isFinite(nq) ? nq : 0;
    }
    this.boundaryVolume += dt * (this.fluxH[0] - this.fluxH[n]);
  }
  sample(s) {
    const f = Math.max(0, Math.min(this.count - 1, s / this.dx - 0.5)),
      i = Math.floor(f),
      j = Math.min(this.count - 1, i + 1),
      t = f - i;
    return {
      depth: this.h[i] * (1 - t) + this.h[j] * t,
      speed: (this.q[i] / this.h[i]) * (1 - t) + (this.q[j] / this.h[j]) * t,
    };
  }
  encode() {
    for (let i = 0; i < this.count; i++) {
      const u = this.q[i] / this.h[i],
        j = Math.min(this.count - 1, i + 1),
        grad = (this.q[j] / this.h[j] - u) / this.dx;
      this.encoded[i * 4] = Math.round(
        Math.max(0, Math.min(1, (u + 8) / 32)) * 255,
      );
      this.encoded[i * 4 + 1] = Math.round(
        Math.max(0, Math.min(1, this.h[i] / 20)) * 255,
      );
      this.encoded[i * 4 + 2] = Math.round(
        Math.max(0, Math.min(1, Math.abs(grad) * 12)) * 255,
      );
      this.encoded[i * 4 + 3] = 255;
    }
  }
  volumeError() {
    return (
      this.h.reduce((s, h) => s + h * this.dx, 0) -
      this.initialVolume -
      this.boundaryVolume
    );
  }
}
/** Cross-section reconstruction: streamwise velocity tapers at both banks.
 * Divergence du/ds + dv/dn and vorticity dv/ds - du/dn are diagnostics of this
 * reduced reconstruction; this is not a full 2D turbulence/erosion solver. */
export function flowDiagnostics(flow, s, n, width = 40) {
  const ds = flow.dx,
    u = flow.sample(s).speed,
    grad = (flow.sample(s + ds).speed - flow.sample(s - ds).speed) / (2 * ds);
  const eta = Math.max(-1, Math.min(1, n / width)),
    profile = 1 - 0.65 * eta * eta;
  return {
    u: u * profile,
    v: 0,
    divergence: grad * profile,
    vorticity: (1.3 * u * eta) / width,
  };
}
