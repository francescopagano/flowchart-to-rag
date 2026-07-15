import base64
import json
import os
import time

import anthropic
from dotenv import load_dotenv

load_dotenv()

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

MODEL = "claude-sonnet-4-6"
MAX_RETRIES = 3


def _encode_image(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def extract_flowchart(
    algorithm_id: str,
    algorithm_label: str,
    image_path: str,
    output_dir: str,
) -> tuple[dict, int, int]:
    """
    Call Claude vision API to extract the flowchart JSON from image_path.
    Returns (json_dict, input_tokens, output_tokens).
    Raises RuntimeError after MAX_RETRIES failed attempts.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    image_data = _encode_image(image_path)

    user_message = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": image_data,
            },
        },
        {
            "type": "text",
            "text": (
                f'Extract the flowchart for "{algorithm_label}" '
                f'(id: "{algorithm_id}") from this image. '
                "Return only valid JSON following the schema in the system prompt."
            ),
        },
    ]

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )

            raw_text = response.content[0].text.strip()

            # Strip accidental markdown fences
            if raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]
                raw_text = raw_text.strip()

            json_dict = json.loads(raw_text)

            json_dir = os.path.join(output_dir, "json")
            os.makedirs(json_dir, exist_ok=True)
            raw_path = os.path.join(json_dir, f"{algorithm_id}_raw.json")
            with open(raw_path, "w", encoding="utf-8") as f:
                json.dump(json_dict, f, ensure_ascii=False, indent=2)

            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            return json_dict, input_tokens, output_tokens

        except json.JSONDecodeError as e:
            last_error = e
            print(f"    [attempt {attempt}/{MAX_RETRIES}] Invalid JSON from API: {e}")
        except anthropic.APIError as e:
            last_error = e
            print(f"    [attempt {attempt}/{MAX_RETRIES}] API error: {e}")

        if attempt < MAX_RETRIES:
            time.sleep(2 ** attempt)

    raise RuntimeError(
        f"Failed to extract {algorithm_id} after {MAX_RETRIES} attempts: {last_error}"
    )