"""Normalize all chunk JSONs to {nodes, edges, hyperedges} format and merge with AST."""
import json, os, sys, glob, re
from pathlib import Path

GRAPHIFY_OUT = Path("D:/1989n/graphify-out")


def _normalize_edges(edges: list) -> list:
    """Normalize edge dicts to {source, target, relation, confidence}."""
    out = []
    for r in edges:
        if not isinstance(r, dict):
            continue
        src = r.get("source") or r.get("from") or r.get("entity1") or r.get("subject")
        tgt = r.get("target") or r.get("to") or r.get("entity2") or r.get("object")
        if not src or not tgt:
            continue
        normalized = {"source": str(src), "target": str(tgt)}
        if "type" in r:
            normalized["relation"] = r.pop("type")
        elif "relation" in r:
            normalized["relation"] = r["relation"]
        else:
            normalized["relation"] = "related_to"
        if "confidence" in r:
            normalized["confidence"] = r["confidence"]
        elif "confidence_score" in r:
            normalized["confidence"] = r["confidence_score"]
        else:
            normalized["confidence"] = 0.75
        # Carry over any extra properties
        for k, v in r.items():
            if k not in ("source", "target", "type", "relation", "confidence", "confidence_score", "properties"):
                normalized[k] = v
        out.append(normalized)
    return out


def convert_chunk_031(d: dict) -> dict:
    """Convert chunk 031's custom schema to nodes/edges."""
    nodes = []
    edges = []
    seen_ids = set()

    # Stocks → nodes
    for stock_key, info in d.get("stocks", {}).items():
        nid = stock_key.replace("_", "_")
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid, "label": info.get("name", nid), "type": "stock",
                "code": info.get("code", ""), "sector": info.get("sector", ""),
            })
    # Indexes → nodes
    for idx_key, info in d.get("indexes", {}).items():
        nid = f"index_{idx_key}"
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid, "label": idx_key, "type": "index",
                "snapshots": len(info.get("snapshots", [])),
            })
    # Sectors → nodes
    for sec_name, info in d.get("sectors", {}).items():
        nid = f"sector_{sec_name}"
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid, "label": sec_name, "type": "sector",
                "dates": info.get("dates", []),
            })
    # Events → nodes
    for i, ev in enumerate(d.get("events", [])):
        nid = f"event_{i:03d}"
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid, "label": ev.get("content", f"Event {i}")[:80],
                "type": ev.get("type", "event"), "date": ev.get("date", ""),
            })
    # Trading decisions → nodes
    for i, td in enumerate(d.get("trading_decisions", [])):
        nid = f"decision_{i:03d}"
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid, "label": f"{td.get('type','decision')}: {td.get('reason','')[:80]}",
                "type": "trading_decision", "date": td.get("date", ""),
            })
    # Portfolio snapshots → nodes
    for snap in d.get("portfolio_evolution", []):
        date = snap.get("date", "unknown")
        nid = f"portfolio_{date}"
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid, "label": f"Portfolio {date}",
                "type": "portfolio_snapshot", "value": snap.get("total_value", 0),
                "pnl": snap.get("pnl", 0),
            })

    # Market indicator snapshots → nodes
    for mi_date, mi_data in d.get("market_indicators", {}).items():
        nid = f"market_{mi_date}"
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid, "label": f"Market {mi_date}", "type": "market_snapshot",
                "sh": mi_data.get("close", {}).get("sh", 0) if isinstance(mi_data.get("close"), dict) else 0,
                "portfolio_value": mi_data.get("portfolio_value", 0),
                "portfolio_pnl": mi_data.get("portfolio_pnl", 0),
            })

    return {"nodes": nodes, "edges": edges, "hyperedges": []}


def fix_chunk_061(text: str) -> dict:
    """Fix truncated JSON in chunk 061 (missing closing braces)."""
    # Count opening and closing braces/brackets
    text = text.strip()
    opens = text.count("{") + text.count("[")
    closes = text.count("}") + text.count("]")
    diff = opens - closes
    if diff > 0:
        # Add missing closing braces
        text += "}" * diff
    # Check for trailing comma before close
    text = re.sub(r",\s*}", "}", text)
    text = re.sub(r",\s*]", "]", text)
    return json.loads(text)


def normalize(d: dict) -> dict:
    """Convert any schema variant to {nodes, edges, hyperedges, input_tokens, output_tokens}."""
    out = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}

    # Direct standard format (nodes + edges and/or relationships)
    if "nodes" in d:
        out["nodes"] = d.get("nodes", [])
        edges_key = "edges" if "edges" in d else ("relationships" if "relationships" in d else None)
        if edges_key:
            out["edges"] = _normalize_edges(d.get(edges_key, []))
        else:
            out["edges"] = _normalize_edges(d.get("relationships", []))
        out["hyperedges"] = d.get("hyperedges", [])
        return out

    # entities → nodes, relationships/relations → edges
    if "entities" in d:
        entities = d.get("entities", [])
        for e in entities:
            if isinstance(e, str):
                out["nodes"].append({"id": e, "label": e, "type": "concept"})
            elif isinstance(e, dict):
                if "id" not in e and "name" in e:
                    e["id"] = e["name"]
                if "id" not in e and "title" in e:
                    e["id"] = e["title"]
                if "id" not in e:
                    continue
                e["id"] = str(e["id"]).lower().replace(" ", "_").replace("-", "_")
                if "type" not in e:
                    e["type"] = e.get("entity_type", "concept")
                out["nodes"].append(e)

    rels = d.get("relationships", d.get("relations", []))
    out["edges"] = _normalize_edges(rels)

    if "hyperedges" in d:
        out["hyperedges"] = d.get("hyperedges", [])

    return out


def fix_node_attrs(nodes: list) -> list:
    """Fix common node attribute issues: rename list-typed 'source' to 'source_file'."""
    for n in nodes:
        s = n.get("source")
        if s is not None and not isinstance(s, str):
            if isinstance(s, list):
                n["source_file"] = s
            n["source"] = "semantic"
        # Ensure id is always a string
        if "id" in n and not isinstance(n["id"], str):
            n["id"] = str(n["id"])
    return nodes


def unwrap_graph(d: dict) -> dict:
    """If the top-level key is 'graph', unwrap it."""
    if "graph" in d and isinstance(d["graph"], dict):
        return d["graph"]
    return d


# Step 1: Collect and normalize ALL chunk files
all_chunks = sorted(glob.glob(str(GRAPHIFY_OUT / ".graphify_chunk_*.json")))
print(f"Found {len(all_chunks)} chunk files", file=sys.stderr)

semantic_nodes = {}
semantic_edges = []
semantic_hyperedges = []
seen_edge_keys = set()

for fpath in all_chunks:
    fname = os.path.basename(fpath)
    try:
        raw_text = Path(fpath).read_text(encoding="utf-8")
        try:
            raw = json.loads(raw_text)
        except json.JSONDecodeError:
            # Try fixing truncated JSON
            raw = fix_chunk_061(raw_text)
            print(f"  FIXED {fname}: recovered from parse error", file=sys.stderr)
    except Exception as e:
        print(f"  SKIP {fname}: {e}", file=sys.stderr)
        continue

    # Check for custom chunk 031 schema
    has_custom = any(k in raw and isinstance(raw[k], dict) and len(raw[k]) > 0
                     for k in ("stocks", "indexes", "events", "sectors", "trading_decisions", "portfolio_evolution"))
    if "nodes" not in raw and "entities" not in raw and "graph" not in raw and has_custom:
        norm = convert_chunk_031(raw)
        print(f"  CONV {fname}: {len(norm['nodes'])}N {len(norm['edges'])}E (custom schema)", file=sys.stderr)
    else:
        raw = unwrap_graph(raw)
        norm = normalize(raw)

    node_count = len(norm["nodes"])
    edge_count = len(norm["edges"])

    if node_count == 0 and edge_count == 0:
        print(f"  EMPTY {fname}", file=sys.stderr)
        continue

    # Deduplicate nodes by ID (merge attributes)
    for n in norm["nodes"]:
        nid = n.get("id", "")
        if nid:
            if nid in semantic_nodes:
                existing = semantic_nodes[nid]
                for k, v in n.items():
                    if k != "id" and (k not in existing or existing[k] is None or existing[k] == ""):
                        existing[k] = v
            else:
                semantic_nodes[nid] = n

    # Deduplicate edges by source+target+relation
    for e in norm["edges"]:
        key = (e.get("source", ""), e.get("target", ""), e.get("relation", ""))
        if key not in seen_edge_keys:
            seen_edge_keys.add(key)
            semantic_edges.append(e)

    semantic_hyperedges.extend(norm.get("hyperedges", []))
    print(f"  {fname}: {node_count}N {edge_count}E", file=sys.stderr)

print(f"\nTotal semantic: {len(semantic_nodes)} nodes, {len(semantic_edges)} edges, {len(semantic_hyperedges)} hyperedges", file=sys.stderr)

# Step 2: Load AST
ast_path = GRAPHIFY_OUT / ".graphify_ast.json"
if ast_path.exists():
    ast = json.loads(ast_path.read_text(encoding="utf-8"))
    ast_nodes = ast.get("nodes", [])
    ast_edges = ast.get("edges", [])
    print(f"\nAST: {len(ast_nodes)} nodes, {len(ast_edges)} edges", file=sys.stderr)
else:
    ast_nodes = []
    ast_edges = []
    print("\nAST file not found", file=sys.stderr)

# Step 3: Merge — semantic nodes first (richer labels), AST nodes fill gaps
all_nodes = fix_node_attrs(list(semantic_nodes.values()))

ast_node_ids = set(n["id"] for n in all_nodes if n.get("id"))
for n in ast_nodes:
    nid = n.get("id", "")
    if nid and nid not in ast_node_ids:
        ast_node_ids.add(nid)
        all_nodes.append(n)

# Merge edges: semantic edges first, then AST edges not overlapping
all_edges = list(semantic_edges)
for e in ast_edges:
    key = (e.get("source", ""), e.get("target", ""), e.get("relation", ""))
    if key not in seen_edge_keys:
        seen_edge_keys.add(key)
        all_edges.append(e)

merged = {
    "nodes": all_nodes,
    "edges": all_edges,
    "hyperedges": semantic_hyperedges,
    "input_tokens": ast.get("input_tokens", 0) if ast_nodes else 0,
    "output_tokens": ast.get("output_tokens", 0) if ast_nodes else 0,
}

# Step 4: Write merged extraction
out_path = GRAPHIFY_OUT / ".graphify_extract.json"
out_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nMerged extraction: {len(all_nodes)} nodes, {len(all_edges)} edges", file=sys.stderr)
print(f"Written to: {out_path}", file=sys.stderr)
