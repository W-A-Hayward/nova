#!/usr/bin/env python3
"""Preprocessing: extract PNG captions once with Ollama vision, store in data/manual/captures.json"""
import json
import base64
from pathlib import Path
import sys

def extract_png_captions():
    """Extract all PNG captures once with vision model, save to data/manual/captures.json"""
    try:
        from langchain_ollama import ChatOllama
        from langchain_core.messages import HumanMessage
    except ImportError:
        print("langchain_ollama not available; skipping vision extraction", file=sys.stderr)
        return {}

    root = Path(__file__).resolve().parent.parent / "data" / "starter" / "Projet360_NOVA_ETUDIANTS"
    captures_out = {}

    # Find all PNG files
    pngs = sorted(root.rglob("*.png"))
    if not pngs:
        print("No PNG files found", file=sys.stderr)
        return {}

    # Try to get vision model
    llm = None
    for model in ["qwen2.5-vl:7b", "llama3.2-vision:11b"]:
        try:
            llm = ChatOllama(model=model, base_url="http://localhost:11434", temperature=0)
            print(f"Using vision model: {model}", file=sys.stderr)
            break
        except:
            pass

    if not llm:
        print("No vision model available (qwen2.5-vl or llama3.2-vision)", file=sys.stderr)
        return {}

    for png_path in pngs:
        rel_path = str(png_path.relative_to(root))
        print(f"Extracting {rel_path}...", file=sys.stderr)

        try:
            # Read image and encode as base64 data URL
            img_data = base64.standard_b64encode(png_path.read_bytes()).decode()
            img_url = f"data:image/png;base64,{img_data}"

            # Send to vision model with proper image_url format
            msg = HumanMessage(
                content=[
                    {
                        "type": "image_url",
                        "image_url": img_url,
                    },
                    {
                        "type": "text",
                        "text": "Décris précisément le contenu de cette capture d'écran. Reproduis le texte visible, les structures, les tableaux et les diagrammes. Sois factuel et complet. N'invente rien."
                    }
                ]
            )

            response = llm.invoke([msg]).content
            captures_out[rel_path] = response.strip()
            print(f"  ✓ {len(response)} chars", file=sys.stderr)
        except Exception as e:
            print(f"  ✗ ERROR: {e}", file=sys.stderr)
            captures_out[rel_path] = f"[Extraction failed: {e}]"

    return captures_out

if __name__ == "__main__":
    result = extract_png_captions()
    out_path = Path(__file__).resolve().parent.parent / "data" / "manual" / "captures.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nSaved {len(result)} capture descriptions to {out_path}")
