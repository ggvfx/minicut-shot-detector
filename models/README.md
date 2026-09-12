# Models

The TransNetV2 ONNX export lives here as `transnetv2.onnx`.

It is **not** in the repository yet — it is produced once as a build step and
then committed, so the app needs neither torch nor tensorflow at runtime:

```bash
python scripts/export_transnetv2.py
```

That script prints a SHA-256 checksum. Paste it into `MODEL_SHA256` in
`src/core/config.py` so the environment check can verify the file has not been
truncated or swapped — a corrupt model produces plausible-looking boundaries
that are quietly wrong.

Until the export exists, the dependency panel reports detection as unavailable
and the rest of the app runs normally.
