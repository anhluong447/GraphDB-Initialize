import { useState, useEffect, useRef, useCallback } from "react";
import ForceGraph2D from "react-force-graph-2d";
import axios from "axios";

const API = "http://localhost:8080";

// Color scheme for each node type
const NODE_COLORS = {
  Function: "#60a5fa",  // blue
  Class: "#a78bfa",     // purple
  File: "#94a3b8",      // gray
  Concept: "#34d399",   // green
  Feature: "#fbbf24",   // yellow
  Decision: "#f97316",  // orange
  Risk: "#f87171",      // red
  Task: "#fb923c",      // amber
  Person: "#e879f9",    // pink
  Commit: "#6b7280",    // dark gray
  Community: "#14b8a6", // teal
};

const NODE_SIZE = {
  Community: 12, Feature: 10, Concept: 9,
  Class: 8, Risk: 8, Function: 6, File: 5,
  Decision: 7, Task: 7, Person: 8, Commit: 4,
};

export default function App() {
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [communities, setCommunities] = useState([]);
  const [selectedNode, setSelectedNode] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [activeFilter, setActiveFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [highlightNodes, setHighlightNodes] = useState(new Set());
  const [stats, setStats] = useState({ nodes: 0, edges: 0 });
  const graphRef = useRef();

  useEffect(() => {
    loadFullGraph();
    loadCommunities();
  }, []);

  const loadFullGraph = async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/graph/full?limit=300`);
      const nodes = data.nodes.map(n => ({ ...n, id: String(n.id) }));
      const nodeIds = new Set(nodes.map(n => n.id));
      const links = data.edges
        .filter(e => nodeIds.has(String(e.source)) && nodeIds.has(String(e.target)))
        .map(e => ({
          source: String(e.source),
          target: String(e.target),
          label: e.label,
        }));
      setGraphData({ nodes, links });
      setStats({ nodes: nodes.length, edges: links.length });
    } catch (err) {
      console.error("Failed to load graph:", err);
    }
    setLoading(false);
  };

  const loadCommunities = async () => {
    try {
      const { data } = await axios.get(`${API}/communities`);
      setCommunities(data);
    } catch (err) {
      console.error("Failed to load communities:", err);
    }
  };

  const loadCommunitySubgraph = async (communityId) => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/graph/community/${communityId}`);
      const nodes = data.nodes.map(n => ({ ...n, id: String(n.id) }));
      const nodeIds = new Set(nodes.map(n => n.id));
      const links = data.edges
        .filter(e => nodeIds.has(String(e.source)) && nodeIds.has(String(e.target)))
        .map(e => ({
          source: String(e.source),
          target: String(e.target),
          label: e.label,
        }));
      setGraphData({ nodes, links });
      setStats({ nodes: nodes.length, edges: links.length });
    } catch (err) {
      console.error("Failed to load community subgraph:", err);
    }
    setLoading(false);
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      setHighlightNodes(new Set());
      setSearchResults([]);
      return;
    }
    try {
      const { data } = await axios.get(`${API}/graph/search?q=${encodeURIComponent(searchQuery)}`);
      setSearchResults(data);
      const ids = new Set(data.map(n => String(n.id)));
      setHighlightNodes(ids);
    } catch (err) {
      console.error("Search failed:", err);
    }
  };

  const handleNodeClick = async (node) => {
    try {
      const { data } = await axios.get(`${API}/node/${encodeURIComponent(node.name)}`);
      setSelectedNode({ ...node, detail: data });
    } catch (err) {
      setSelectedNode({ ...node, detail: null });
    }
  };

  const filteredData = {
    nodes: activeFilter === "all"
      ? graphData.nodes
      : graphData.nodes.filter(n => n.type === activeFilter),
    links: graphData.links,
  };

  const nodeColor = useCallback((node) => {
    if (highlightNodes.size > 0) {
      return highlightNodes.has(String(node.id))
        ? (NODE_COLORS[node.type] || "#999")
        : "#1e293b";
    }
    return NODE_COLORS[node.type] || "#999";
  }, [highlightNodes]);

  const nodeVal = useCallback((node) => NODE_SIZE[node.type] || 5, []);

  return (
    <div style={{ display: "flex", height: "100vh", background: "#030712", color: "#fff", overflow: "hidden", fontFamily: "'Inter', 'Segoe UI', sans-serif" }}>

      {/* Left Sidebar — Communities */}
      <div style={{ width: "280px", background: "#0f172a", borderRight: "1px solid #1e293b", display: "flex", flexDirection: "column", flexShrink: 0 }}>
        {/* Header */}
        <div style={{ padding: "20px 16px", borderBottom: "1px solid #1e293b" }}>
          <h1 style={{ fontSize: "20px", fontWeight: "800", margin: 0, background: "linear-gradient(135deg, #60a5fa, #a78bfa)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
            ⬡ GraphRAG
          </h1>
          <p style={{ fontSize: "11px", color: "#64748b", marginTop: "4px" }}>Knowledge Graph Explorer</p>
          <div style={{ display: "flex", gap: "12px", marginTop: "8px", fontSize: "11px", color: "#94a3b8" }}>
            <span>🔵 {stats.nodes} nodes</span>
            <span>🔗 {stats.edges} edges</span>
          </div>
        </div>

        {/* Search */}
        <div style={{ padding: "12px", borderBottom: "1px solid #1e293b" }}>
          <div style={{ display: "flex", gap: "6px" }}>
            <input
              style={{ flex: 1, background: "#1e293b", fontSize: "13px", borderRadius: "8px", padding: "8px 12px", color: "#fff", border: "1px solid #334155", outline: "none" }}
              placeholder="Search nodes..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleSearch()}
            />
            <button
              onClick={handleSearch}
              style={{ background: "linear-gradient(135deg, #3b82f6, #6366f1)", border: "none", padding: "8px 14px", borderRadius: "8px", color: "#fff", fontSize: "13px", cursor: "pointer", fontWeight: "600" }}
            >
              ↵
            </button>
          </div>
          {searchResults.length > 0 && (
            <div style={{ marginTop: "6px", fontSize: "11px", color: "#64748b" }}>
              {searchResults.length} results found
              <button
                onClick={() => { setHighlightNodes(new Set()); setSearchResults([]); setSearchQuery(""); }}
                style={{ marginLeft: "8px", color: "#60a5fa", background: "none", border: "none", cursor: "pointer", fontSize: "11px" }}
              >
                Clear
              </button>
            </div>
          )}
        </div>

        {/* Filter by node type */}
        <div style={{ padding: "12px", borderBottom: "1px solid #1e293b" }}>
          <p style={{ fontSize: "10px", color: "#475569", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "8px", fontWeight: "600" }}>Filter by type</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
            {["all", ...Object.keys(NODE_COLORS)].map(type => (
              <button
                key={type}
                onClick={() => setActiveFilter(type)}
                style={{
                  fontSize: "11px",
                  padding: "4px 8px",
                  borderRadius: "6px",
                  cursor: "pointer",
                  border: "none",
                  transition: "all 0.15s",
                  background: activeFilter === type ? "linear-gradient(135deg, #3b82f6, #6366f1)" : "#1e293b",
                  color: activeFilter === type ? "#fff" : "#94a3b8",
                  borderLeft: type !== "all" ? `3px solid ${NODE_COLORS[type]}` : "none",
                }}
              >
                {type}
              </button>
            ))}
          </div>
        </div>

        {/* Communities list */}
        <div style={{ flex: 1, overflowY: "auto", padding: "12px" }}>
          <p style={{ fontSize: "10px", color: "#475569", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "8px", fontWeight: "600" }}>Communities</p>
          <button
            onClick={loadFullGraph}
            style={{ width: "100%", textAlign: "left", fontSize: "12px", background: "#1e293b", border: "1px solid #334155", borderRadius: "8px", padding: "10px 12px", marginBottom: "8px", color: "#e2e8f0", cursor: "pointer" }}
          >
            🌐 View full graph
          </button>
          {communities.map(c => (
            <button
              key={c.id}
              onClick={() => loadCommunitySubgraph(c.id)}
              style={{ width: "100%", textAlign: "left", background: "#1e293b", border: "1px solid #334155", borderRadius: "8px", padding: "10px 12px", marginBottom: "4px", cursor: "pointer", transition: "all 0.15s" }}
              onMouseEnter={e => e.currentTarget.style.borderColor = "#14b8a6"}
              onMouseLeave={e => e.currentTarget.style.borderColor = "#334155"}
            >
              <div style={{ fontSize: "13px", fontWeight: "600", color: "#14b8a6" }}>{c.name}</div>
              <div style={{ fontSize: "11px", color: "#64748b", marginTop: "2px" }}>{c.member_count} nodes</div>
            </button>
          ))}
        </div>
      </div>

      {/* Main Graph Canvas */}
      <div style={{ flex: 1, position: "relative" }}>
        {loading && (
          <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(3,7,18,0.85)", zIndex: 10 }}>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: "32px", marginBottom: "8px", animation: "spin 1s linear infinite" }}>⬡</div>
              <div style={{ color: "#94a3b8", fontSize: "13px" }}>Loading graph...</div>
            </div>
          </div>
        )}

        {/* Legend */}
        <div style={{ position: "absolute", top: "16px", left: "16px", zIndex: 10, background: "rgba(15,23,42,0.92)", borderRadius: "12px", padding: "12px 16px", fontSize: "11px", border: "1px solid #1e293b", backdropFilter: "blur(8px)" }}>
          {Object.entries(NODE_COLORS).slice(0, 7).map(([type, color]) => (
            <div key={type} style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
              <div style={{ width: "10px", height: "10px", borderRadius: "50%", background: color, boxShadow: `0 0 6px ${color}40` }} />
              <span style={{ color: "#94a3b8" }}>{type}</span>
            </div>
          ))}
        </div>

        <ForceGraph2D
          ref={graphRef}
          graphData={filteredData}
          nodeColor={nodeColor}
          nodeVal={nodeVal}
          nodeLabel={node => `[${node.type}] ${node.name}`}
          linkColor={() => "#374151"}
          linkWidth={0.5}
          linkDirectionalArrowLength={3}
          linkDirectionalArrowRelPos={1}
          backgroundColor="#030712"
          onNodeClick={handleNodeClick}
          cooldownTicks={100}
          nodeCanvasObject={(node, ctx, globalScale) => {
            const label = node.name;
            const fontSize = Math.max(8 / globalScale, 3);
            const r = NODE_SIZE[node.type] || 5;
            const color = nodeColor(node);

            // Glow effect
            ctx.beginPath();
            ctx.arc(node.x, node.y, r + 2, 0, 2 * Math.PI);
            ctx.fillStyle = color + "20";
            ctx.fill();

            // Draw node circle
            ctx.beginPath();
            ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
            ctx.fillStyle = color;
            ctx.fill();

            // Draw label when zoomed in
            if (globalScale > 1.5) {
              ctx.font = `${fontSize}px 'Inter', 'Segoe UI', sans-serif`;
              ctx.fillStyle = "#e2e8f0";
              ctx.textAlign = "center";
              ctx.fillText(label?.slice(0, 20), node.x, node.y + r + fontSize + 1);
            }
          }}
        />
      </div>

      {/* Right Panel — Node detail */}
      {selectedNode && (
        <div style={{ width: "340px", background: "#0f172a", borderLeft: "1px solid #1e293b", overflowY: "auto", flexShrink: 0 }}>
          <div style={{ padding: "16px", borderBottom: "1px solid #1e293b", display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <div style={{ fontSize: "10px", fontWeight: "700", textTransform: "uppercase", letterSpacing: "1.5px", marginBottom: "4px", color: NODE_COLORS[selectedNode.type] || "#999" }}>
                {selectedNode.type}
              </div>
              <h2 style={{ fontSize: "16px", fontWeight: "700", margin: 0, color: "#f1f5f9" }}>{selectedNode.name}</h2>
            </div>
            <button
              onClick={() => setSelectedNode(null)}
              style={{ color: "#475569", background: "none", border: "none", fontSize: "20px", cursor: "pointer", lineHeight: 1 }}
            >×</button>
          </div>

          {selectedNode.detail && (
            <div style={{ padding: "16px" }}>
              {selectedNode.description && (
                <div style={{ marginBottom: "16px" }}>
                  <p style={{ fontSize: "10px", color: "#475569", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "4px", fontWeight: "600" }}>Description</p>
                  <p style={{ fontSize: "13px", color: "#cbd5e1", lineHeight: 1.5 }}>{selectedNode.description}</p>
                </div>
              )}

              {selectedNode.detail?.node?.raw_code && (
                <div style={{ marginBottom: "16px" }}>
                  <p style={{ fontSize: "10px", color: "#475569", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "4px", fontWeight: "600" }}>Code</p>
                  <pre style={{ fontSize: "11px", background: "#1e293b", borderRadius: "8px", padding: "12px", overflowX: "auto", color: "#4ade80", whiteSpace: "pre-wrap", border: "1px solid #334155", maxHeight: "200px", overflowY: "auto" }}>
                    {selectedNode.detail.node.raw_code?.slice(0, 500)}
                  </pre>
                </div>
              )}

              {selectedNode.detail?.outgoing?.length > 0 && (
                <div style={{ marginBottom: "16px" }}>
                  <p style={{ fontSize: "10px", color: "#475569", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "6px", fontWeight: "600" }}>
                    Outgoing ({selectedNode.detail.outgoing.length})
                  </p>
                  {selectedNode.detail.outgoing.filter(r => r.target).slice(0, 8).map((rel, i) => (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "12px", color: "#94a3b8", marginBottom: "4px" }}>
                      <span style={{ color: "#60a5fa", fontWeight: "500" }}>{rel.type}</span>
                      <span>→</span>
                      <button
                        style={{ color: "#e2e8f0", background: "none", border: "none", cursor: "pointer", fontSize: "12px", textDecoration: "underline" }}
                        onClick={() => handleNodeClick({ name: rel.target, type: "?" })}
                      >
                        {rel.target}
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {selectedNode.detail?.incoming?.length > 0 && (
                <div style={{ marginBottom: "16px" }}>
                  <p style={{ fontSize: "10px", color: "#475569", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "6px", fontWeight: "600" }}>
                    Incoming ({selectedNode.detail.incoming.length})
                  </p>
                  {selectedNode.detail.incoming.filter(r => r.source).slice(0, 8).map((rel, i) => (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "12px", color: "#94a3b8", marginBottom: "4px" }}>
                      <button
                        style={{ color: "#e2e8f0", background: "none", border: "none", cursor: "pointer", fontSize: "12px", textDecoration: "underline" }}
                        onClick={() => handleNodeClick({ name: rel.source, type: "?" })}
                      >
                        {rel.source}
                      </button>
                      <span>→</span>
                      <span style={{ color: "#60a5fa", fontWeight: "500" }}>{rel.type}</span>
                    </div>
                  ))}
                </div>
              )}

              {selectedNode.detail?.node?.community_id !== undefined && selectedNode.detail?.node?.community_id !== null && (
                <div>
                  <p style={{ fontSize: "10px", color: "#475569", textTransform: "uppercase", letterSpacing: "1px", marginBottom: "4px", fontWeight: "600" }}>Community</p>
                  <button
                    onClick={() => loadCommunitySubgraph(selectedNode.detail.node.community_id)}
                    style={{ fontSize: "12px", color: "#14b8a6", background: "none", border: "none", cursor: "pointer", textDecoration: "underline" }}
                  >
                    View community #{selectedNode.detail.node.community_id}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: #0f172a; }
        ::-webkit-scrollbar-thumb { background: #334155; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #475569; }
      `}</style>
    </div>
  );
}
