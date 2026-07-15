import glob
import json
import os
from datetime import datetime, timezone


def _build_label_index(algoritmi: dict[str, dict]) -> dict[str, str]:
    """Build {algorithm_label: algorithm_id} index."""
    index: dict[str, str] = {}
    for algo_id, algo_data in algoritmi.items():
        label = algo_data.get("label", "")
        if label:
            index[label] = algo_id
    return index


def _walk_nodes(node: dict, label_index: dict[str, str], cross_refs: list[dict], path: str) -> None:
    """Recursively walk nodes, add next_algoritmo_id where resolvable, collect cross-refs."""
    next_label = node.get("next_algoritmo")
    if next_label:
        resolved_id = label_index.get(next_label)
        node["next_algoritmo_id"] = resolved_id  # None if not found
        if resolved_id:
            cross_refs.append({"from": path, "to": resolved_id})

    for child_entry in node.get("figli", []):
        child_node = child_entry.get("nodo", {})
        child_path = f"{path}/{child_node.get('id', 'unknown')}"
        _walk_nodes(child_node, label_index, cross_refs, child_path)


def resolve(output_dir: str) -> dict:
    """
    Load all *_raw.json files, resolve cross-references, save merged.json.
    Returns the merged dict.
    """
    json_dir = os.path.join(output_dir, "json")
    raw_files = glob.glob(os.path.join(json_dir, "*_raw.json"))

    algoritmi: dict[str, dict] = {}
    for raw_file in sorted(raw_files):
        with open(raw_file, encoding="utf-8") as f:
            data = json.load(f)
        algo_id = data.get("algoritmo_id")
        if algo_id:
            algoritmi[algo_id] = data

    label_index = _build_label_index(algoritmi)
    cross_refs: list[dict] = []

    for algo_id, algo_data in algoritmi.items():
        root = algo_data.get("nodo_radice")
        if root:
            root_path = f"{algo_id}/{root.get('id', 'root')}"
            _walk_nodes(root, label_index, cross_refs, root_path)

    merged = {
        "meta": {
            "fonte": "AIOM 2024",
            "algoritmi_totali": len(algoritmi),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "cross_references": cross_refs,
        },
        "algoritmi": algoritmi,
    }

    merged_path = os.path.join(json_dir, "merged.json")
    with open(merged_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    return merged