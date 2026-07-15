# Claude Code Prompt — flowchart-to-rag

> **How to use this file:**
> Open Claude Code and say:
> *"Read this file and implement the project described in it. 
> Implement one module at a time and show it to me before moving to the next."*

---

## Objective

Build a Python tool called `flowchart-to-rag` that extracts decision
structures from rasterized flowcharts embedded in PDF files and converts
them into text chunks ready for ingestion into any RAG pipeline.
The chunking strategy must be configurable to accommodate different
embedding models with different context window limits.

## Context

Italian oncology clinical guidelines (AIOM 2024) contain multiple
flowcharts on known pages, each identified as "Algoritmo X" (Algorithm X).
Algorithms are interconnected: a terminal node of Algorithm 1 may reference
Algorithm 2 as the next step. Flowcharts are confirmed rasterized images
inside the PDF (verified via PyMuPDF get_drawings() which returns only
header/footer decorative lines, not flowchart vectors).

The RAG system is single-shot: the LLM receives one retrieved context
and responds without additional retrieval loops. This means chunks must
be self-contained and cross-references must be partially inlined.

---

## Project Structure

```
flowchart-to-rag/
├── main.py              # CLI entrypoint
├── config.py            # page numbers, algorithm list, pipeline settings
├── extractor.py         # PDF page → PNG image via PyMuPDF
├── vision.py            # Anthropic vision API calls + JSON validation
├── resolver.py          # cross-reference resolution between algorithms
├── chunker.py           # JSON → linearized text chunks for RAG
├── reviewer.py          # optional human-in-the-loop review step
├── output/
│   ├── json/            # raw JSON per algorithm
│   ├── json/merged.json # unified graph with resolved cross-references
│   └── chunks/          # .md files ready for RAG ingestion
└── requirements.txt
```

---

## config.py

```python
ALGORITHMS = [
    {"id": "algoritmo_1", "label": "Algoritmo 1", "page": 12},
    {"id": "algoritmo_2", "label": "Algoritmo 2", "page": 15},
    # extend as needed
]

MODE = "auto"
# "auto"   → fully automated pipeline, no human interaction
# "review" → after each vision extraction, show JSON and wait
#            for human approval before proceeding

CHUNK_MAX_TOKENS = 400
# Set this based on your embedding model's context window.
# Conservative examples:
# - IBM Granite Embedding 107M : 400  (hard limit: 512)
# - text-embedding-3-small      : 1600 (hard limit: 8191)
# - nomic-embed-text            : 700  (hard limit: 2048)
# Rule of thumb: set to ~80% of your model's hard limit

CROSS_REF_MODE = "inline"
# "inline"    → terminal nodes include first-level content of the
#               referenced algorithm (never recursive)
# "reference" → chunks remain separate with explicit pointer
#               "See: Algorithm X" at the end

PDF_PATH = "aiom2024.pdf"
OUTPUT_DIR = "./output"
```

---

## extractor.py

Use PyMuPDF to extract each algorithm page as a high-resolution PNG.

**Existing code to integrate (do not rewrite from scratch, extend it):**

```python
import fitz
doc = fitz.open("aiom2024.pdf")
page = doc[N]
paths = page.get_drawings()
# confirmed: returns only header/footer lines, not flowchart vectors
# therefore flowchart is rasterized → extract as image
```

For image extraction use:

```python
mat = fitz.Matrix(300/72, 300/72)  # 300 DPI
pix = page.get_pixmap(matrix=mat)
pix.save(output_path)
```

Save images to `/tmp/flowchart_pages/{algorithm_id}.png`
Return `dict`: `{algorithm_id: image_path}`

---

## vision.py

For each extracted image, call `claude-sonnet-4-6` with vision.
Use base64 encoding for the image.
Implement exponential backoff retry (max 3 attempts) on API errors.

`ANTHROPIC_API_KEY` must be loaded from environment variable via `python-dotenv`.

Use this exact system prompt — **do not modify its structure**, it is
calibrated for clinical output:

```
SYSTEM_PROMPT = """
You are a clinical oncology expert. You analyze flowcharts from AIOM 2024
Italian clinical guidelines and serialize them into structured JSON.

Mandatory rules:
1. Do NOT infer logic that is not explicitly visible in the diagram
2. Do NOT add clinical knowledge from your own training
3. Nodes with ambiguous text must be marked with "ambiguita": true
4. Conditional arrows must have an explicit label in the "condizione" field
5. References to other algorithms must be preserved exactly as they
   appear in the diagram text (e.g. "Algoritmo 2")

Required JSON schema:
{
  "algoritmo_id": "string",
  "label": "string",
  "fonte": "AIOM 2024",
  "nodo_radice": {
    "id": "string",
    "label": "string",
    "tipo": "string",
    // allowed values: procedura_diagnostica | diagnosi | stadiazione |
    //                 presentazione | esito_negativo | riferimento_esterno
    "componenti": ["string"],  // optional: for list-type nodes
    "ambiguita": false,
    "figli": [
      {
        "condizione": "string | null",  // arrow label if conditional
        "nodo": { /* recursive, same structure */ }
      }
    ],
    "next_algoritmo": "string | null"
    // populate if this node is a terminal that references another algorithm
  }
}

Respond ONLY with valid JSON. No markdown, no code fences, no comments.
"""
```

**Expected output example (use this for validation):**

```json
{
  "algoritmo_id": "algoritmo_1",
  "label": "Algoritmo 1 - Diagnosi e Stadiazione Tumore Polmonare",
  "fonte": "AIOM 2024",
  "nodo_radice": {
    "id": "esami_diagnostici",
    "label": "Esami diagnostici",
    "tipo": "procedura_diagnostica",
    "componenti": [
      "Esame obiettivo",
      "Rx torace",
      "TC torace",
      "Fibrobroncoscopia",
      "Esame citologico escreato (opzionale)",
      "Agoaspirato transtoracico (opzionale)"
    ],
    "ambiguita": false,
    "figli": [
      {
        "condizione": null,
        "nodo": {
          "id": "no_neoplasia",
          "label": "No neoplasia primitiva polmonare",
          "tipo": "esito_negativo",
          "ambiguita": false,
          "figli": [],
          "next_algoritmo": null
        }
      },
      {
        "condizione": null,
        "nodo": {
          "id": "nsclc",
          "label": "NSCLC",
          "tipo": "diagnosi",
          "ambiguita": false,
          "figli": [
            {
              "condizione": "Malattia localizzata",
              "nodo": {
                "id": "nsclc_localizzata",
                "label": "Malattia localizzata",
                "tipo": "presentazione",
                "ambiguita": false,
                "figli": [],
                "next_algoritmo": "Algoritmo 2"
              }
            }
          ],
          "next_algoritmo": null
        }
      }
    ],
    "next_algoritmo": null
  }
}
```

After receiving the API response:
- Validate it is parseable JSON before returning
- Save raw JSON to `output/json/{algorithm_id}_raw.json`
- Track and return token usage (`input_tokens + output_tokens`)
  from the API response for cost reporting

---

## resolver.py

After all algorithms have been extracted:

1. Load all JSONs from `output/json/*_raw.json`
2. Build index: `{algorithm_label: algorithm_id}`
   e.g. `{"Algoritmo 2": "algoritmo_2"}`
3. Walk all nodes recursively, find `next_algoritmo` fields that are not null
4. Add `next_algoritmo_id` field to each resolved node
5. Handle diamond dependencies (two algorithms referencing the same third)
   without duplicating content — use the index reference only
6. Save unified graph to `output/json/merged.json`

`merged.json` structure:

```json
{
  "meta": {
    "fonte": "AIOM 2024",
    "algoritmi_totali": 3,
    "generated_at": "2024-01-01T00:00:00Z",
    "cross_references": [
      {"from": "algoritmo_1/nsclc_localizzata", "to": "algoritmo_2"}
    ]
  },
  "algoritmi": {
    "algoritmo_1": {},
    "algoritmo_2": {}
  }
}
```

---

## chunker.py

Linearize each decision path into self-contained text chunks.
**One chunk = one complete path from root to terminal node.**

### Chunking rules

- Every chunk must be fully self-contained (understandable without
  reading other chunks)
- Always include: fonte, algoritmo label, full path from root
- Never exceed `CHUNK_MAX_TOKENS` (estimate: 1 token ≈ 4 characters).
  Verify length before writing each file.
- If a single path exceeds the token limit, split at the staging node,
  carrying forward the root context into the next chunk header

### Cross-reference handling (CROSS_REF_MODE = "inline")

When a terminal node has `next_algoritmo` set:
- Expand **ONLY** the root node + direct children (first level) of the
  referenced algorithm
- **NEVER expand recursively** (Algorithm 2 may itself reference Algorithm 3)
- Always end the chunk with:
  `"For complete details see: [Algorithm X]"`
- Verify the resulting chunk does not exceed `CHUNK_MAX_TOKENS` after
  inlining. If it does, truncate the inlined content and keep the pointer.

### Chunk output format (.md with YAML frontmatter)

```markdown
---
fonte: AIOM 2024
algoritmo: Algoritmo 1
percorso: NSCLC > Malattia localizzata
chunk_id: algo1_nsclc_localizzata
algoritmo_id: algoritmo_1
cross_ref: algoritmo_2
---
Diagnostic pathway NSCLC - Localized Disease (AIOM 2024, Algorithm 1):
If diagnostic workup (Esame obiettivo, Rx torace, TC torace,
Fibrobroncoscopia) identifies NSCLC, perform staging: [staging exams].
If presentation = localized disease → [first-level content of Algorithm 2].
For complete details see: Algorithm 2.
```

Save each chunk as:
`output/chunks/{algorithm_id}_{path_slug}_{index}.md`

Save chunk index as `output/chunks/index.json`:

```json
{
  "total_chunks": 7,
  "chunks": [
    {
      "chunk_id": "algo1_nsclc_localizzata",
      "file": "algoritmo_1_nsclc_localizzata_0.md",
      "algoritmo": "Algoritmo 1",
      "percorso": "NSCLC > Malattia localizzata",
      "token_estimate": 312,
      "cross_ref": "algoritmo_2"
    }
  ]
}
```

---

## reviewer.py

Implement a `HumanReviewer` class with method `review(algorithm_id, json_dict)`:

**If MODE = "auto":**
Return `json_dict` unchanged, no console output.

**If MODE = "review":**
- Print formatted JSON to console
- Prompt user: `[A]ccept / [E]dit / [R]egenerate / [S]kip`

| Choice | Behavior |
|--------|----------|
| A | Return `json_dict` as-is |
| E | Write JSON to temp file, open in `$EDITOR` (fallback: `nano`), reload after editor closes, return modified JSON |
| R | Call `vision.py` to regenerate from scratch for this algorithm, then show result again (loop until A or S) |
| S | Return `None` — this algorithm will be excluded from output |

---

## main.py — CLI

Implement with `argparse`:

```bash
python main.py \
  --pdf path/to/aiom2024.pdf \
  --mode auto \           # auto | review
  --cross-ref inline \    # inline | reference
  --output ./output \
  --algorithms 1,2,3      # which algorithms to process (default: all)
```

Console output during execution:

```
[1/4] Extracting Algorithm 1 (page 12)... ✓
[2/4] Vision extraction Algorithm 1... ✓ (input: 1842 tokens, output: 310 tokens)
[3/4] Resolving cross-references... ✓ (3 references resolved)
[4/4] Generating chunks... ✓ (7 chunks generated)

Pipeline complete.
Intermediate JSON : output/json/ (N files)
Unified graph     : output/json/merged.json
RAG chunks        : output/chunks/ (M files)
Total API tokens  : X input / Y output
Estimated cost    : $Z (at current claude-sonnet-4-6 pricing)
```

---

## requirements.txt

```
pymupdf
anthropic
python-dotenv
```

---

## Critical Implementation Notes

1. **Token counting** must use real values from Anthropic API response
   (`usage.input_tokens + usage.output_tokens`), never estimated.

2. **YAML frontmatter** in `.md` chunks must be valid and parseable —
   downstream RAG systems use metadata fields for filtered retrieval.

3. **All file paths** must be relative or derived from `--output` argument.
   No hardcoded absolute paths anywhere in the codebase.

4. **Pipeline must be synchronous and linear** — no threading, no async.
   This is a diagnostic/clinical tool where readability and debuggability
   take priority over performance.

5. **Error handling**: on any unrecoverable error (API failure after 3
   retries, invalid JSON after extraction), log the error with algorithm
   ID and continue processing remaining algorithms rather than crashing.

6. **Cycle detection**: the chunker must handle the case where a path in
   the JSON tree has no terminal node (circular reference or missing
   `next_algoritmo`) — detect and log a warning, do not infinite loop.

7. **Language neutrality**: do not hardcode Italian or English in chunker
   text templates — output language must follow the source JSON label
   language (Italian for AIOM guidelines).

---

## Implementation Order

Implement modules **one at a time** in this order, showing the complete
file before moving to the next:

1. `config.py`
2. `extractor.py` ← integrate existing PyMuPDF code provided above
3. `vision.py` ← use JSON example above for output validation
4. `resolver.py`
5. `chunker.py` ← inline cross-ref at first level only, never recursive
6. `reviewer.py`
7. `main.py`
8. `requirements.txt`
