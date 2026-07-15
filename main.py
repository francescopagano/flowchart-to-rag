import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()

import config
from extractor import extract_pages
from vision import extract_flowchart
from resolver import resolve
from chunker import generate_chunks
from reviewer import HumanReviewer


def parse_args():
    parser = argparse.ArgumentParser(description="flowchart-to-rag: Extract flowcharts from PDF into RAG chunks")
    parser.add_argument("--pdf", default=config.PDF_PATH, help="Path to PDF file")
    parser.add_argument("--mode", choices=["auto", "review"], default=config.MODE)
    parser.add_argument("--cross-ref", choices=["inline", "reference"], default=config.CROSS_REF_MODE, dest="cross_ref")
    parser.add_argument("--output", default=config.OUTPUT_DIR, help="Output directory")
    parser.add_argument("--algorithms", default=None, help="Comma-separated algorithm numbers to process (e.g. 1,2,3). Default: all")
    parser.add_argument("--chunk-tokens", type=int, default=config.CHUNK_MAX_TOKENS, dest="chunk_tokens", help="Max tokens per chunk")
    return parser.parse_args()


def main():
    args = parse_args()
    output_dir = args.output
    os.makedirs(output_dir, exist_ok=True)

    # Filter algorithms if requested
    algorithms = config.ALGORITHMS
    if args.algorithms:
        requested = {int(n.strip()) for n in args.algorithms.split(",") if n.strip().isdigit()}
        algorithms = [
            a for a in algorithms
            if any(a["id"] == f"algoritmo_{n}" for n in requested)
        ]
        if not algorithms:
            print(f"No matching algorithms found for: {args.algorithms}")
            sys.exit(1)

    total_steps = len(algorithms) * 2 + 2
    step = 0
    total_input_tokens = 0
    total_output_tokens = 0
    extracted_json: dict[str, dict] = {}

    def next_step(label: str) -> int:
        nonlocal step
        step += 1
        return step

    # Set up reviewer
    def regenerate_fn(algo_id, algo_label, img_path):
        return extract_flowchart(algo_id, algo_label, img_path, output_dir)

    reviewer = HumanReviewer(
        mode=args.mode,
        regenerate_fn=regenerate_fn,
    )

    image_paths: dict[str, str] = {}

    for algo in algorithms:
        algo_id = algo["id"]
        algo_label = algo["label"]
        page_num = algo["page"]

        # Step: extract image
        s = next_step(f"Extracting {algo_label}")
        print(f"[{s}/{total_steps}] Extracting {algo_label} (page {page_num})...", end=" ", flush=True)
        try:
            result = extract_pages([algo], args.pdf, output_dir)
            image_paths.update(result)
            print("✓")
        except Exception as e:
            print(f"✗ ERROR: {e}")
            continue

        # Step: vision extraction
        s = next_step(f"Vision {algo_label}")
        print(f"[{s}/{total_steps}] Vision extraction {algo_label}...", end=" ", flush=True)
        img_path = image_paths.get(algo_id)
        if not img_path or not os.path.exists(img_path):
            print(f"✗ ERROR: image not found for {algo_id}")
            continue
        try:
            json_dict, inp_tok, out_tok = extract_flowchart(algo_id, algo_label, img_path, output_dir)
            total_input_tokens += inp_tok
            total_output_tokens += out_tok
            print(f"✓ (input: {inp_tok} tokens, output: {out_tok} tokens)")
        except Exception as e:
            print(f"✗ ERROR: {e}")
            continue

        # Human review step (if mode=review)
        reviewed = reviewer.review(algo_id, json_dict, image_path=img_path, algorithm_label=algo_label)
        if reviewed is None:
            print(f"    Skipped {algo_id} by reviewer.")
            continue
        extracted_json[algo_id] = reviewed

    if not extracted_json:
        print("No algorithms were successfully extracted. Exiting.")
        sys.exit(1)

    # Step: resolve cross-references
    s = next_step("Resolving cross-references")
    print(f"[{s}/{total_steps}] Resolving cross-references...", end=" ", flush=True)
    try:
        merged = resolve(output_dir)
        ref_count = len(merged.get("meta", {}).get("cross_references", []))
        print(f"✓ ({ref_count} references resolved)")
    except Exception as e:
        print(f"✗ ERROR: {e}")
        sys.exit(1)

    # Step: generate chunks
    s = next_step("Generating chunks")
    print(f"[{s}/{total_steps}] Generating chunks...", end=" ", flush=True)
    try:
        chunk_index = generate_chunks(merged, output_dir, args.chunk_tokens, args.cross_ref)
        print(f"✓ ({len(chunk_index)} chunks generated)")
    except Exception as e:
        print(f"✗ ERROR: {e}")
        sys.exit(1)

    # Cost calculation at claude-sonnet-4-6 rates
    input_cost = (total_input_tokens / 1_000_000) * 3.00
    output_cost = (total_output_tokens / 1_000_000) * 15.00
    total_cost = input_cost + output_cost

    json_count = len(list(
        f for f in os.listdir(os.path.join(output_dir, "json"))
        if f.endswith("_raw.json")
    ))

    print(f"""
Pipeline complete.
Intermediate JSON : {os.path.join(output_dir, 'json')}/ ({json_count} files)
Unified graph     : {os.path.join(output_dir, 'json', 'merged.json')}
RAG chunks        : {os.path.join(output_dir, 'chunks')}/ ({len(chunk_index)} files)
Total API tokens  : {total_input_tokens} input / {total_output_tokens} output
Estimated cost    : ${total_cost:.4f} (at current claude-sonnet-4-6 pricing)
""")


if __name__ == "__main__":
    main()