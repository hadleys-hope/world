/** Refine only the channel neighbourhood; conforming edge stitching avoids terrain cracks. */
export function refineRiverTerrain({
  xy,
  heights,
  cells,
  sample,
  contains,
  bounds,
  spacing = 16,
}) {
  const midpoints = new Map(),
    leaves = [];
  const key = (a, b) => (a < b ? `${a}:${b}` : `${b}:${a}`);
  const vertex = (x, y) => {
    const i = xy.length;
    xy.push([x, y]);
    heights.push(sample(x, y));
    return i;
  };
  const middle = (a, b) => {
    const k = key(a, b);
    if (!midpoints.has(k))
      midpoints.set(
        k,
        vertex((xy[a][0] + xy[b][0]) / 2, (xy[a][1] + xy[b][1]) / 2),
      );
    return midpoints.get(k);
  };
  const length = (a, b) => Math.hypot(xy[a][0] - xy[b][0], xy[a][1] - xy[b][1]);
  const split = (a, b, c, cell, level = 0) => {
    const size = Math.max(length(a, b), length(b, c), length(c, a));
    const x = (xy[a][0] + xy[b][0] + xy[c][0]) / 3;
    const y = (xy[a][1] + xy[b][1] + xy[c][1]) / 3;
    const inReach = x + size >= bounds.source && x - size <= bounds.mouth;
    const near =
      inReach &&
      contains(
        Math.max(bounds.source, Math.min(bounds.mouth, x)),
        y,
        size + 40,
      );
    if (size > spacing && near && level < 7) {
      const ab = middle(a, b),
        bc = middle(b, c),
        ca = middle(c, a);
      split(a, ab, ca, cell, level + 1);
      split(ab, b, bc, cell, level + 1);
      split(ca, bc, c, cell, level + 1);
      split(ab, bc, ca, cell, level + 1);
    } else leaves.push({ a, b, c, cell });
  };
  cells.forEach((triangles, cell) => {
    for (let i = 0; i < triangles.length; i += 3)
      split(...triangles.slice(i, i + 3), cell);
  });
  const indices = [],
    refinedCells = new Map();
  const emit = (cell, a, b, c) => {
    indices.push(a, b, c);
    if (!refinedCells.has(cell)) refinedCells.set(cell, []);
    refinedCells.get(cell).push(a, b, c);
  };
  const edge = (a, b, result) => {
    const m = midpoints.get(key(a, b));
    if (m !== undefined) {
      edge(a, m, result);
      edge(m, b, result);
    } else result.push(a);
  };
  for (const { a, b, c, cell } of leaves) {
    const perimeter = [];
    edge(a, b, perimeter);
    edge(b, c, perimeter);
    edge(c, a, perimeter);
    if (perimeter.length === 3) emit(cell, a, b, c);
    else {
      const centre = vertex(
        (xy[a][0] + xy[b][0] + xy[c][0]) / 3,
        (xy[a][1] + xy[b][1] + xy[c][1]) / 3,
      );
      for (let i = 0; i < perimeter.length; i++)
        emit(cell, centre, perimeter[i], perimeter[(i + 1) % perimeter.length]);
    }
  }
  return { indices, cells: refinedCells };
}
