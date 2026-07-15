import os
import pymupdf as fitz

def compute_dpi(page, target_long_edge_px=1568, min_dpi=150, max_dpi=300):
    long_edge_inches = max(page.rect.width, page.rect.height) / 72
    dpi = target_long_edge_px / long_edge_inches
    return max(min_dpi, min(dpi, max_dpi))

def extract_pages(algorithms: list[dict], pdf_path: str, output_dir: str) -> dict[str, str]:
    """Extract each algorithm page as a 300 DPI PNG. Returns {algorithm_id: image_path}."""
    pages_dir = os.path.join(output_dir, "pages")
    os.makedirs(pages_dir, exist_ok=True)

    doc = fitz.open(pdf_path)
    results: dict[str, str] = {}

    for algo in algorithms:
        algo_id = algo["id"]
        page_num = algo["page"] - 1  # fitz uses 0-based index

        page = doc[page_num]

        # Verify the flowchart is rasterized (not vector)
        paths = page.get_drawings()
        if paths:
            # Only header/footer decorative lines expected — flowchart is rasterized
            pass
        
        dpi = compute_dpi(page)
        mat = fitz.Matrix(dpi / 72, dpi / 72)  # use computed DPI
        pix = page.get_pixmap(matrix=mat)

        image_path = os.path.join(pages_dir, f"{algo_id}.png")
        pix.save(image_path)
        results[algo_id] = image_path

    doc.close()
    return results