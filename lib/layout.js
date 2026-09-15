/**
 * Hybrid layout: roadmap.sh presentation, arbitrary-DAG tolerance.
 * Core nodes are ranked topologically (falling back to insertion order on a
 * cycle) and pinned to a vertical spine. Everything else hangs off its parent
 * in a side column, sides alternating down the spine. User-dragged positions
 * (x,y persisted on the node) always win.
 */
export const W = 210, H = 42, GAP = 50, COL = 300;

export function layout(nodes, edges) {
  const core = nodes.filter(n => n.track === 'core');
  const byId = new Map(nodes.map(n => [n.id, n]));

  // --- rank the spine ---
  const main = edges.filter(e => e.kind === 'main' &&
    byId.get(e.src)?.track === 'core' && byId.get(e.dst)?.track === 'core');
  const indeg = new Map(core.map(n => [n.id, 0]));
  const out = new Map(core.map(n => [n.id, []]));
  for (const e of main) {
    if (!indeg.has(e.dst) || !out.has(e.src)) continue;
    indeg.set(e.dst, indeg.get(e.dst) + 1);
    out.get(e.src).push(e.dst);
  }
  const ordOf = new Map(core.map(n => [n.id, n.ord ?? 0]));
  const queue = core.filter(n => indeg.get(n.id) === 0).map(n => n.id)
    .sort((a, b) => ordOf.get(a) - ordOf.get(b));
  const spine = [];
  const seen = new Set();
  while (queue.length) {
    const id = queue.shift();
    if (seen.has(id)) continue;
    seen.add(id); spine.push(id);
    const next = [];
    for (const d of out.get(id) ?? []) {
      indeg.set(d, indeg.get(d) - 1);
      if (indeg.get(d) <= 0 && !seen.has(d)) next.push(d);
    }
    queue.push(...next.sort((a, b) => ordOf.get(a) - ordOf.get(b)));
  }
  // cycle or disconnected leftovers -> append in insertion order
  for (const n of core) if (!seen.has(n.id)) spine.push(n.id);

  // --- bucket children under their parent ---
  const kids = new Map(spine.map(id => [id, []]));
  const spineSet = new Set(spine);
  const orphans = [];
  for (const n of nodes) {
    if (n.track === 'core') continue;
    if (spineSet.has(n.parent_id)) kids.get(n.parent_id).push(n);
    else orphans.push(n);
  }
  // orphans: try an incoming branch edge, else pin to the nearest spine node by ord
  for (const n of orphans) {
    const via = edges.find(e => e.dst === n.id && spineSet.has(e.src))?.src;
    const host = via ?? spine.reduce((best, id) =>
      Math.abs((ordOf.get(id) ?? 0) - (n.ord ?? 0)) < Math.abs((ordOf.get(best) ?? 0) - (n.ord ?? 0))
        ? id : best, spine[0]);
    if (host) kids.get(host).push(n);
  }

  // --- place ---
  const pos = {};
  let y = 0, side = -1;
  for (const id of spine) {
    const ch = kids.get(id) ?? [];
    pos[id] = { x: 0, y };
    if (ch.length) {
      const block = ch.length * GAP;
      const top = y + H / 2 - block / 2;
      ch.forEach((c, i) => { pos[c.id] = { x: side * COL, y: top + i * GAP }; });
      side *= -1;
    }
    y += Math.max(90, H / 2 + (ch.length * GAP) / 2 + 34);
  }
  // anything still unplaced (no core nodes at all) — stack it
  let fy = y;
  for (const n of nodes) if (!pos[n.id]) { pos[n.id] = { x: 0, y: fy }; fy += 60; }

  return nodes.map(n => ({
    ...n,
    pos: (n.x != null && n.y != null) ? { x: n.x, y: n.y } : pos[n.id],
  }));
}
