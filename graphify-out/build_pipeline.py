"""Build knowledge graph from merged extraction, cluster, label, and export."""
import json, sys
from pathlib import Path
import networkx as nx

GRAPHIFY_OUT = Path("D:/1989n/graphify-out")
EXTRACT_PATH = GRAPHIFY_OUT / ".graphify_extract.json"
GRAPH_JSON_PATH = GRAPHIFY_OUT / "graph.json"
GRAPH_HTML_PATH = GRAPHIFY_OUT / "graph.html"
GRAPHML_PATH = GRAPHIFY_OUT / "graph.graphml"
REPORT_PATH = GRAPHIFY_OUT / "GRAPH_REPORT.md"

# Step 1: Load merged extraction
print("Loading merged extraction...", file=sys.stderr)
extract = json.loads(EXTRACT_PATH.read_text(encoding="utf-8"))
nodes = extract.get("nodes", [])
edges = extract.get("edges", [])
hyperedges = extract.get("hyperedges", [])
print(f"  Nodes: {len(nodes)}", file=sys.stderr)
print(f"  Edges: {len(edges)}", file=sys.stderr)
print(f"  Hyperedges: {len(hyperedges)}", file=sys.stderr)

# Step 2: Build graph using graphify
print("\nBuilding graph...", file=sys.stderr)
from graphify.build import build
G = build([extract], directed=False)
print(f"  Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges", file=sys.stderr)

# Step 3: Cluster communities
print("\nClustering communities...", file=sys.stderr)
from graphify.cluster import cluster
communities = cluster(G)
num_comms = len(communities)
print(f"  Communities: {num_comms}", file=sys.stderr)

# Assign community_id to each node
node_to_community = {}
for cid, members in communities.items():
    for nid in members:
        node_to_community[nid] = cid

# Step 4: Generate community labels
print("\nGenerating community labels...", file=sys.stderr)
# Build a node lookup
node_map = {n.get("id", ""): n for n in nodes}

community_labels = {}
community_god_nodes = {}
for cid, members in communities.items():
    # Collect all node data for this community
    comm_nodes = [node_map.get(m, {}) for m in members if m in node_map]

    # Count node types
    type_counts = {}
    label_counts = {}
    for n in comm_nodes:
        t = n.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
        lbl = n.get("label", n.get("name", ""))
        if lbl:
            label_counts[lbl] = label_counts.get(lbl, 0) + 1

    # Dominant type
    dominant_type = max(type_counts, key=type_counts.get) if type_counts else "unknown"
    top_labels = sorted(label_counts, key=label_counts.get, reverse=True)[:5]

    # Build label
    if top_labels:
        label = f"{dominant_type}: {', '.join(top_labels[:3])}"
    else:
        label = f"Community {cid} ({dominant_type})"

    community_labels[cid] = label

    # God nodes = highest degree nodes in this community
    subgraph = G.subgraph(members)
    degree_dict = dict(subgraph.degree())
    god_nodes = sorted(degree_dict, key=degree_dict.get, reverse=True)[:5]
    community_god_nodes[cid] = [
        {"id": nid, "label": node_map.get(nid, {}).get("label", nid), "degree": degree_dict[nid]}
        for nid in god_nodes if nid in node_map
    ]

# Step 5: Save community labels
print("\nSaving community labels...", file=sys.stderr)
labels_path = GRAPHIFY_OUT / ".graphify_labels.json"
labels_path.write_text(json.dumps(community_labels, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"  Written: {labels_path}", file=sys.stderr)

# Step 6: Export graph.json
print("\nExporting graph.json...", file=sys.stderr)
from graphify.export import to_json
to_json(G, communities, str(GRAPH_JSON_PATH), force=True)
print(f"  Written: {GRAPH_JSON_PATH}", file=sys.stderr)

# Step 6: Export graph.html
print("\nExporting graph.html...", file=sys.stderr)
from graphify.export import to_html
# Build member counts for aggregated view
member_counts = {cid: len(members) for cid, members in communities.items()}
to_html(G, communities, str(GRAPH_HTML_PATH),
        community_labels=community_labels, member_counts=member_counts)
print(f"  Written: {GRAPH_HTML_PATH}", file=sys.stderr)

# Step 7: Export graph.graphml (with list→str conversion for GraphML compatibility)
print("\nExporting graph.graphml...", file=sys.stderr)
from graphify.export import to_graphml
# GraphML doesn't support list/dict values, convert them to strings
H = nx.Graph()
for n, data in G.nodes(data=True):
    clean = {}
    for k, v in data.items():
        if isinstance(v, (list, dict)):
            clean[k] = json.dumps(v, ensure_ascii=False)
        elif isinstance(v, bool):
            clean[k] = str(v)
        elif v is None:
            clean[k] = ""
        else:
            clean[k] = v
    H.add_node(n, **clean)
for u, v, data in G.edges(data=True):
    clean = {}
    for k, v in data.items():
        if isinstance(v, (list, dict)):
            clean[k] = json.dumps(v, ensure_ascii=False)
        elif isinstance(v, bool):
            clean[k] = str(v)
        elif v is None:
            clean[k] = ""
    H.add_edge(u, v, **clean)
try:
    to_graphml(H, communities, str(GRAPHML_PATH))
    print(f"  Written: {GRAPHML_PATH}", file=sys.stderr)
except Exception as e:
    print(f"  SKIP graphml: {e}", file=sys.stderr)

# Step 9: Generate GRAPH_REPORT.md
print("\nGenerating GRAPH_REPORT.md...", file=sys.stderr)
from collections import Counter

# Source breakdown
ast_nodes = [n for n in nodes if n.get("source") == "ast"]
semantic_nodes = [n for n in nodes if n.get("source") != "ast"]

# Global statistics from graph (post-dedup)
node_type_counts = Counter()
for nid, data in G.nodes(data=True):
    node_type_counts[data.get("type", "unknown")] += 1

edge_type_counts = Counter()
for u, v, data in G.edges(data=True):
    edge_type_counts[data.get("relation", "related_to")] += 1

# Community statistics
community_stats = []
for cid in sorted(communities.keys()):
    members = communities[cid]
    comm_node_data = [G.nodes[m] for m in members if m in G]
    type_counts = Counter(nd.get("type", "unknown") for nd in comm_node_data)
    dominant_type = type_counts.most_common(1)[0][0] if type_counts else "unknown"
    community_stats.append({
        "id": cid,
        "size": len(members),
        "dominant_type": dominant_type,
        "label": community_labels.get(cid, f"Community {cid}"),
        "type_distribution": dict(type_counts.most_common(5)),
        "god_nodes": community_god_nodes.get(cid, [])[:3],
    })

# Sort by size
community_stats.sort(key=lambda x: -x["size"])

# Top edges
top_edge_types = edge_type_counts.most_common(20)

# Find surprising cross-community connections
cross_comm_edges = []
for u, v, data in G.edges(data=True):
    cu = node_to_community.get(u)
    cv = node_to_community.get(v)
    if cu is not None and cv is not None and cu != cv:
        cross_comm_edges.append({
            "source": u, "target": v,
            "source_community": community_labels.get(cu, f"C{cu}"),
            "target_community": community_labels.get(cv, f"C{cv}"),
            "relation": data.get("relation", "related_to"),
            "confidence": data.get("confidence", "N/A"),
        })

cross_comm_edges.sort(key=lambda x: float(x.get("confidence", 0)) if isinstance(x.get("confidence"), (int, float)) else 0, reverse=True)

# Generate report
lines = []
lines.append("# Knowledge Graph Report")
lines.append("")
lines.append(f"**Generated:** 2026-05-28")
lines.append(f"**Source:** D:/1989n (trading system)")

# Section 1: Overview
lines.append("")
lines.append("## 1. Overview")
lines.append("")
lines.append(f"| Metric | Value |")
lines.append(f"|--------|-------|")
lines.append(f"| Total Nodes | {G.number_of_nodes()} |")
lines.append(f"| Total Edges | {G.number_of_edges()} |")
lines.append(f"| Communities | {num_comms} |")
lines.append(f"| Hyperedges | {len(hyperedges)} |")
lines.append(f"| From AST (code) | {len(ast_nodes)} extracted |")
lines.append(f"| From Semantic (docs) | {len(semantic_nodes)} extracted |")

# Section 2: Node Type Distribution
lines.append("")
lines.append("## 2. Node Type Distribution (graph)")
lines.append("")
lines.append(f"| Type | Count |")
lines.append(f"|------|-------|")
for t, c in node_type_counts.most_common(20):
    lines.append(f"| {t} | {c} |")

# Section 3: Edge Type Distribution
lines.append("")
lines.append("## 3. Edge Type Distribution")
lines.append("")
lines.append(f"| Relation | Count |")
lines.append(f"|----------|-------|")
for rel, c in top_edge_types[:20]:
    lines.append(f"| {rel} | {c} |")

# Section 4: Communities (top 30)
lines.append("")
lines.append("## 4. Communities (top 30 by size)")
lines.append("")
for cs in community_stats[:30]:
    lines.append(f"### Community {cs['id']}: {cs['label']}")
    lines.append("")
    lines.append(f"- **Size:** {cs['size']} nodes")
    lines.append(f"- **Dominant type:** {cs['dominant_type']}")
    lines.append(f"- **Type distribution:** {json.dumps(cs['type_distribution'], ensure_ascii=False)}")
    if cs["god_nodes"]:
        god_str = "; ".join([f"{g['label']} (deg={g['degree']})" for g in cs["god_nodes"]])
        lines.append(f"- **Central nodes:** {god_str}")
    lines.append("")

# Section 5: Surprising Cross-Community Connections
lines.append("## 5. Cross-Community Connections")
lines.append("")
lines.append(f"Total cross-community edges: {len(cross_comm_edges)}")
lines.append("")
if cross_comm_edges:
    lines.append("| Source | Target | Relation | Source Community | Target Community |")
    lines.append("|--------|--------|----------|-----------------|-----------------|")
    for ce in cross_comm_edges[:30]:
        s_label = G.nodes[ce['source']].get('label', ce['source']) if ce['source'] in G else ce['source']
        t_label = G.nodes[ce['target']].get('label', ce['target']) if ce['target'] in G else ce['target']
        lines.append(f"| {s_label} | {t_label} | {ce['relation']} | {ce['source_community']} | {ce['target_community']} |")

# Section 6: Suggested Questions
lines.append("")
lines.append("## 6. Suggested Questions")
lines.append("")
for cs in community_stats[:5]:
    label = cs["label"]
    lines.append(f"- What is the structure of \"{label}\"?")
if cross_comm_edges:
    ce = cross_comm_edges[0]
    lines.append(f"- How does {ce['source_community']} connect to {ce['target_community']}?")
lines.append("- Which communities are growing in influence?")
lines.append("- What are the highest-confidence relationships across domains?")
lines.append("- Are there isolated knowledge domains with few external connections?")

# Write report
REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
print(f"  Written: {REPORT_PATH}", file=sys.stderr)

# Summary
print(f"\n{'='*60}", file=sys.stderr)
print(f"Pipeline complete!", file=sys.stderr)
print(f"  Nodes: {G.number_of_nodes()}", file=sys.stderr)
print(f"  Edges: {G.number_of_edges()}", file=sys.stderr)
print(f"  Communities: {num_comms}", file=sys.stderr)
print(f"  Outputs:", file=sys.stderr)
print(f"    - {GRAPH_JSON_PATH}", file=sys.stderr)
print(f"    - {GRAPH_HTML_PATH}", file=sys.stderr)
print(f"    - {GRAPHML_PATH}", file=sys.stderr)
print(f"    - {REPORT_PATH}", file=sys.stderr)
print(f"{'='*60}", file=sys.stderr)
