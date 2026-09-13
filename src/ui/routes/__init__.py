"""
HTTP Routes.

One module per tab, mirroring `src/splitter/` and `src/identifier/` so that a
reader who has learned where the splitter's code lives already knows where its
routes live.

Split out of a single `server.py` when it reached 537 lines across six areas,
with Phase 7 due to add six more routes. `server.py` is now what its docstring
always claimed: the app, the page, the static mount, and the wiring.

No processing logic lives in any of them. A route translates a request into a
call into a pipeline or a core module and translates the result back to JSON —
if one grows a decision, that decision belongs in a stage module instead.
"""
