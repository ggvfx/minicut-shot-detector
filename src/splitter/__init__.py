"""
The Splitter: one mini cut in, one file per shot out.

Detection, reconciliation, validation, and the pipeline that orders them.
Everything here is deterministic — the same source produces byte-identical
boundaries on every run, and no judgement enters the path.

Shared foundations live in `src.core` and `src.media`. Nothing in this package
is imported by the identifier, and nothing here imports from it.
"""
