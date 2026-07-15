###
# ALGORITHMS = [
#    {"id": "algoritmo_1", "label": "Algoritmo 1", "page": 12},
#    {"id": "algoritmo_2", "label": "Algoritmo 2", "page": 13},
#    {"id": "algoritmo_3", "label": "Algoritmo 3", "page": 14},
#    {"id": "algoritmo_4", "label": "Algoritmo 4", "page": 15},
#    {"id": "algoritmo_5", "label": "Algoritmo 5", "page": 16},
#    {"id": "algoritmo_6", "label": "Algoritmo 2", "page": 17},
#    {"id": "algoritmo_7", "label": "Algoritmo 2", "page": 7},
#    # extend as needed
###

ALGORITHMS = [
    {"id": "algoritmo_1", "label": "Algoritmo 1", "page": 1},
    {"id": "algoritmo_2", "label": "Algoritmo 2", "page": 2},
    {"id": "algoritmo_3", "label": "Algoritmo 3", "page": 3},
    {"id": "algoritmo_4", "label": "Algoritmo 4", "page": 4},
    {"id": "algoritmo_5", "label": "Algoritmo 5", "page": 5},
    {"id": "algoritmo_6", "label": "Algoritmo 2", "page": 6},
    {"id": "algoritmo_7", "label": "Algoritmo 2", "page": 7}
    # extend as needed
]

MODE = "auto"
# "auto"   -> fully automated pipeline, no human interaction
# "review" -> after each vision extraction, show JSON and wait
#             for human approval before proceeding

CHUNK_MAX_TOKENS = 400
# Set this based on your embedding model's context window.
# Conservative examples:
# - IBM Granite Embedding 107M : 400  (hard limit: 512)
# - text-embedding-3-small      : 1600 (hard limit: 8191)
# - nomic-embed-text            : 700  (hard limit: 2048)
# Rule of thumb: set to ~80% of your model's hard limit

CROSS_REF_MODE = "inline"
# "inline"    -> terminal nodes include first-level content of the
#                referenced algorithm (never recursive)
# "reference" -> chunks remain separate with explicit pointer
#                "See: Algorithm X" at the end

#PDF_PATH = r"C:\Users\ad50633\OneDrive - SAS\Documents\Projects\Oncology\documentation\LG149_Polmone_agg2024.pdf"
#OUTPUT_DIR = "./output"

PDF_PATH = r"C:\Users\ad50633\Downloads\AIOM_2024_PDTA_Tumore.pdf"
OUTPUT_DIR = "./output2"