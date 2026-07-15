import json
import os
import re


def _token_estimate(text: str) -> int:
    return max(1, len(text) // 4)


def _slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")[:60]


def _get_first_level_summary(algo_data: dict) -> str:
    """Return a brief summary of the root node and its direct children."""
    root = algo_data.get("nodo_radice", {})
    label = root.get("label", "")
    componenti = root.get("componenti", [])
    children = root.get("figli", [])

    parts = [label]
    if componenti:
        parts.append(f"({', '.join(componenti)})")
    child_labels = [c["nodo"]["label"] for c in children if "nodo" in c]
    if child_labels:
        parts.append("-> " + " | ".join(child_labels))
    return " ".join(parts)


def _write_chunk(
    chunk_text: str,
    frontmatter: dict,
    chunks_dir: str,
    algo_id: str,
    path_slug: str,
    index: int,
    chunk_index_list: list,
) -> None:
    fm_lines = ["---"]
    for k, v in frontmatter.items():
        if v is None:
            fm_lines.append(f"{k}:")
        else:
            fm_lines.append(f"{k}: {v}")
    fm_lines.append("---")
    full_text = "\n".join(fm_lines) + "\n" + chunk_text

    filename = f"{algo_id}_{path_slug}_{index}.md"
    filepath = os.path.join(chunks_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(full_text)

    chunk_index_list.append(
        {
            "chunk_id": frontmatter.get("chunk_id", ""),
            "file": filename,
            "algoritmo": frontmatter.get("algoritmo", ""),
            "percorso": frontmatter.get("percorso", ""),
            "token_estimate": _token_estimate(full_text),
            "cross_ref": frontmatter.get("cross_ref"),
        }
    )


def _linearize_paths(
    node: dict,
    current_path: list[str],
    current_conditions: list[str],
    visited: set[str],
) -> list[dict]:
    """
    DFS through the node tree. Returns list of complete root-to-terminal paths.
    Each path is a dict with keys: path_labels, conditions, terminal_node.
    """
    node_id = node.get("id", "")
    if node_id in visited:
        print(f"    [WARNING] Circular reference detected at node '{node_id}', stopping branch.")
        return []
    visited = visited | {node_id}

    path_labels = current_path + [node.get("label", node_id)]
    children = node.get("figli", [])

    if not children:
        # Terminal node
        return [
            {
                "path_labels": path_labels,
                "conditions": current_conditions,
                "terminal_node": node,
            }
        ]

    results = []
    for child_entry in children:
        condition = child_entry.get("condizione")
        child_node = child_entry.get("nodo", {})
        new_conditions = current_conditions + ([condition] if condition else [])
        results.extend(
            _linearize_paths(child_node, path_labels, new_conditions, visited)
        )
    return results


def _build_chunk_text(
    path_info: dict,
    algo_label: str,
    fonte: str,
    algoritmi: dict,
    cross_ref_mode: str,
    chunk_max_tokens: int,
) -> tuple[str, str | None]:
    """
    Build chunk prose text and return (text, cross_ref_algo_id).
    Handles inline expansion at first level only.
    """
    path_labels = path_info["path_labels"]
    conditions = path_info["conditions"]
    terminal = path_info["terminal_node"]
    next_algo_label = terminal.get("next_algoritmo")
    next_algo_id = terminal.get("next_algoritmo_id")

    path_str = " > ".join(path_labels)
    header = f"{fonte}, {algo_label} — {path_str}:\n"

    # Build path description
    steps = []
    for i, label in enumerate(path_labels):
        if i < len(conditions) and conditions[i]:
            steps.append(f"[If: {conditions[i]}] {label}")
        else:
            steps.append(label)

    componenti = terminal.get("componenti", [])
    body_parts = [" -> ".join(steps)]
    if componenti:
        body_parts.append("Components: " + ", ".join(componenti))

    body = "\n".join(body_parts)
    cross_ref: str | None = None

    if next_algo_label:
        cross_ref = next_algo_id

        if cross_ref_mode == "inline" and next_algo_id and next_algo_id in algoritmi:
            ref_data = algoritmi[next_algo_id]
            summary = _get_first_level_summary(ref_data)
            inline_text = f"\nNext step ({next_algo_label}): {summary}\nFor complete details see: {next_algo_label}."
            candidate = header + body + inline_text

            if _token_estimate(candidate) <= chunk_max_tokens:
                return candidate, cross_ref
            else:
                # Inline would exceed limit — fall back to pointer only
                body += f"\nFor complete details see: {next_algo_label}."
                return header + body, cross_ref
        else:
            body += f"\nSee: {next_algo_label}."

    return header + body, cross_ref


def generate_chunks(
    merged: dict,
    output_dir: str,
    chunk_max_tokens: int,
    cross_ref_mode: str,
) -> list[dict]:
    """Linearize all algorithms into .md chunks. Returns the chunk index list."""
    chunks_dir = os.path.join(output_dir, "chunks")
    os.makedirs(chunks_dir, exist_ok=True)

    algoritmi = merged.get("algoritmi", {})
    fonte = merged.get("meta", {}).get("fonte", "AIOM 2024")
    chunk_index: list[dict] = []

    for algo_id, algo_data in algoritmi.items():
        algo_label = algo_data.get("label", algo_id)
        root = algo_data.get("nodo_radice")
        if not root:
            print(f"    [WARNING] {algo_id} has no nodo_radice, skipping.")
            continue

        paths = _linearize_paths(root, [], [], set())
        if not paths:
            print(f"    [WARNING] {algo_id}: no paths found.")
            continue

        for idx, path_info in enumerate(paths):
            path_labels = path_info["path_labels"]
            path_str = " > ".join(path_labels)
            path_slug = _slugify(path_str)
            chunk_id = f"{_slugify(algo_id)}_{path_slug}"

            chunk_text, cross_ref = _build_chunk_text(
                path_info, algo_label, fonte, algoritmi, cross_ref_mode, chunk_max_tokens
            )

            # Split if too long: carry root label into continuation chunk
            if _token_estimate(chunk_text) > chunk_max_tokens:
                lines = chunk_text.splitlines()
                half = len(lines) // 2
                part1 = "\n".join(lines[:half]) + "\n[continued...]"
                part2 = f"{fonte}, {algo_label} — continued:\n" + "\n".join(lines[half:])

                for part_idx, part_text in enumerate([part1, part2]):
                    frontmatter = {
                        "fonte": fonte,
                        "algoritmo": algo_label,
                        "percorso": path_str,
                        "chunk_id": f"{chunk_id}_p{part_idx}",
                        "algoritmo_id": algo_id,
                        "cross_ref": cross_ref,
                    }
                    _write_chunk(
                        part_text, frontmatter, chunks_dir,
                        algo_id, path_slug, idx * 10 + part_idx, chunk_index
                    )
            else:
                frontmatter = {
                    "fonte": fonte,
                    "algoritmo": algo_label,
                    "percorso": path_str,
                    "chunk_id": chunk_id,
                    "algoritmo_id": algo_id,
                    "cross_ref": cross_ref,
                }
                _write_chunk(
                    chunk_text, frontmatter, chunks_dir,
                    algo_id, path_slug, idx, chunk_index
                )

    index_path = os.path.join(chunks_dir, "index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"total_chunks": len(chunk_index), "chunks": chunk_index}, f, ensure_ascii=False, indent=2)

    return chunk_index