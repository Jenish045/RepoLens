const dagre = require("@dagrejs/dagre");

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => { input += chunk; });
process.stdin.on("end", () => {
  const payload = JSON.parse(input);
  const graph = new dagre.graphlib.Graph({ multigraph: false });
  graph.setGraph({ rankdir: "LR", nodesep: 72, ranksep: 112, marginx: 32, marginy: 32 });
  graph.setDefaultEdgeLabel(() => ({}));
  for (const node of [...payload.nodes].sort((a, b) => a.id.localeCompare(b.id))) {
    graph.setNode(node.id, { width: node.width, height: node.height });
  }
  for (const edge of [...payload.edges].sort((a, b) => a.source.localeCompare(b.source) || a.target.localeCompare(b.target))) {
    if (edge.source !== edge.target) graph.setEdge(edge.source, edge.target, { weight: edge.weight });
  }
  dagre.layout(graph);
  const positions = {};
  for (const id of graph.nodes().sort()) {
    const node = graph.node(id);
    positions[id] = { x: Math.round(node.x - node.width / 2), y: Math.round(node.y - node.height / 2) };
  }
  process.stdout.write(JSON.stringify(positions));
});
