import json
import os
import subprocess
import tempfile


class HumanReviewer:
    def __init__(self, mode: str, regenerate_fn=None):
        """
        mode: "auto" | "review"
        regenerate_fn: callable(algorithm_id, algorithm_label, image_path) -> (json_dict, int, int)
                       Required only in "review" mode for the R option.
        """
        self.mode = mode
        self.regenerate_fn = regenerate_fn

    def review(self, algorithm_id: str, json_dict: dict, image_path: str = None, algorithm_label: str = None) -> dict | None:
        if self.mode == "auto":
            return json_dict

        while True:
            print(f"\n--- Review: {algorithm_id} ---")
            print(json.dumps(json_dict, ensure_ascii=False, indent=2))
            print("\n[A]ccept  [E]dit  [R]egenerate  [S]kip")
            choice = input("Choice: ").strip().upper()

            if choice == "A":
                return json_dict

            elif choice == "E":
                editor = os.environ.get("EDITOR", "nano")
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".json", delete=False, encoding="utf-8"
                ) as tmp:
                    json.dump(json_dict, tmp, ensure_ascii=False, indent=2)
                    tmp_path = tmp.name
                try:
                    subprocess.run([editor, tmp_path], check=True)
                    with open(tmp_path, encoding="utf-8") as f:
                        modified = json.load(f)
                    return modified
                except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
                    print(f"Error during edit: {e}. Returning original.")
                    return json_dict
                finally:
                    os.unlink(tmp_path)

            elif choice == "R":
                if self.regenerate_fn is None or image_path is None:
                    print("Regeneration not available (no regenerate function or image path).")
                    continue
                print(f"Regenerating {algorithm_id}...")
                try:
                    new_json, _, _ = self.regenerate_fn(algorithm_id, algorithm_label or algorithm_id, image_path)
                    json_dict = new_json
                except Exception as e:
                    print(f"Regeneration failed: {e}")

            elif choice == "S":
                return None

            else:
                print("Invalid choice. Enter A, E, R, or S.")