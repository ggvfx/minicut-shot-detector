"""
TransNetV2 ONNX Export (Build Step).

Converts the upstream TransNetV2 weights into the single .onnx file the app
ships with, then prints its checksum for pinning in src/core/config.py.

Run once, commit the result. This is why the app does not depend on torch or
tensorflow at runtime — only this script does, and only when the model is
regenerated.

Run from the repo root as a module, so it can import from src:
    python -m scripts.export_transnetv2 [--force]
"""

import argparse
import logging
from pathlib import Path

from src.core.utils import file_sha256

# --- PATHS ---

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = REPO_ROOT / "models" / "transnetv2.onnx"

# The network takes a window of 100 frames at 48x27 RGB.
EXPORT_INPUT_SHAPE = (1, 100, 27, 48, 3)


# --- EXPORT ---


def export_model(output_path: Path, force: bool = False) -> Path:
    """
    Writes the ONNX export.

    Args:
        output_path: Destination .onnx file.
        force: Overwrite an existing export.

    Returns:
        Path to the written model.
    """
    # PSEUDOCODE
    # 1. Bail out early if output_path exists and force is False.
    # 2. Load the upstream TransNetV2 weights (torch, imported here only).
    # 3. torch.onnx.export() with a dummy input of EXPORT_INPUT_SHAPE.
    # 4. Mark the batch dimension dynamic so windows can be batched later.
    # 5. Re-open the result with onnxruntime and run one dummy window, to prove
    #    the file loads before it gets committed.
    raise NotImplementedError


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Export TransNetV2 to ONNX")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing export")
    args = parser.parse_args()

    model_path = export_model(OUTPUT_PATH, force=args.force)

    logging.info(f"Wrote {model_path}")
    logging.info(f"Set MODEL_SHA256 = \"{file_sha256(model_path)}\" in src/core/config.py")


if __name__ == "__main__":
    main()
