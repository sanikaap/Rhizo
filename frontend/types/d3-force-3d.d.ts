// d3-force-3d (used by react-force-graph) ships no types; we only use forceCollide.
declare module 'd3-force-3d' {
  export function forceCollide<N>(radius?: number | ((node: N) => number)): ((alpha: number) => void) & { initialize?: (nodes: N[]) => void }
}
