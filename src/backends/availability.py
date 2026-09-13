"""
Backend Rows for the Dependency Panel.

Turns the configured backends into the same `Check` rows every other dependency
uses, so the panel reads as one list rather than as two systems.

Lives here rather than in `core/environment.py` because of the dependency
direction: `core` may not import a domain package. The checker assembles the
rows it owns and takes these as extras, which keeps the arrow pointing one way.

**Nothing here gates the app.** The splitter needs no model at all, so every
row is marked `advisory`: reported in the panel, left out of its headline
status. An unconfigured backend is a limitation of the Identifier tab, not a
fault, and letting one turn a working Splitter amber is the same mistake that
took the output directory off the panel.

When the Identifier tab is built, a user standing in it does want to be
blocked — but that is a question for that tab's own view, not for the panel
everyone sees on launch.
"""

import logging
from typing import List

from src.backends.adapter import BackendError, create_backend
from src.core.config import BACKEND_API, BACKEND_LOCAL, Settings
from src.core.environment import DEGRADED, OK, Check

# --- LABELS ---

# Named for the pass they serve rather than the technology, because that is how
# someone reading the panel thinks about them: one looks at pictures, one reads
# text, and they are configured separately because they are routinely different.
PASS_LABELS = {
    "vision": "Vision model (Identifier)",
    "text": "Text model (Identifier)",
}

# What to do about an unconfigured pass. Points at the file rather than naming
# a command, because there is no one command — it depends entirely on which of
# the three kinds of backend the user has available.
CONFIGURE_FIX = "Set it in settings.json — copy settings.example.json to start"


def backend_checks(settings: Settings, advisory: bool = False) -> List[Check]:
    """
    One row per model pass, reporting whether it can be used.

    Args:
        settings: The saved backend configuration.
        advisory: Report the rows without letting them set the panel's headline
            status. True where a missing model does not stop the user doing
            what they came to do.

    Returns:
        A check for the vision pass and one for the text pass, in that order.

    Notes:
        Never worse than degraded, and never green when nothing is configured —
        both halves of that matter.

        Whether these gate depends on who is asking, which is why it is an
        argument rather than a property of the row. In the Identifier tab a
        missing model means the tab cannot work, so it gates. Anywhere else it
        is a limitation of a feature the user may never open, and gating would
        paint a working app amber — the mistake that took the output directory
        off the panel.
    """
    checks = [_check_pass(name, settings) for name in ("vision", "text")]

    # Set here rather than on each branch of _check_pass: four places to
    # remember a flag is three places to forget it, and forgetting it once
    # already put a false warning in front of the user.
    for check in checks:
        check.advisory = advisory

    return checks


def _check_pass(name: str, settings: Settings) -> Check:
    """
    Whether one pass has a usable backend behind it.

    Notes:
        Availability is asked of the backend itself, which is cheap by
        contract: no prompt is sent, nothing is charged, and a local runtime
        that is not running answers by refusing the connection immediately.
    """
    config = getattr(settings, name)
    label = PASS_LABELS[name]

    if not _is_configured(config):
        return Check(
            key=f"backend_{name}",
            label=label,
            status=DEGRADED,
            detail="Not configured — needed for the Identifier tab, not the Splitter",
            fix=CONFIGURE_FIX,
        )

    try:
        backend = create_backend(config)
    except BackendError as error:
        return Check(
            key=f"backend_{name}", label=label, status=DEGRADED,
            detail=str(error), fix=CONFIGURE_FIX,
        )

    if backend.available():
        return Check(
            key=f"backend_{name}", label=label, status=OK,
            detail=backend.describe(),
        )

    logging.debug(f"The {name} backend is configured but unavailable: {backend.describe()}")

    return Check(
        key=f"backend_{name}",
        label=label,
        status=DEGRADED,
        detail=f"{backend.describe()} — configured, but not answering",
        fix=_unavailable_fix(config),
    )


def _is_configured(config) -> bool:
    """
    Whether a pass has been set up at all, as opposed to left at its defaults.

    A fresh `BackendConfig` names a command backend with no command, which is
    the honest "nothing chosen yet" state rather than something broken.

    Notes:
        Each kind is configured by a different field, so this cannot be one
        test for all three. A local backend needs only a model — its endpoint
        defaults to where runtimes conventionally listen — and asking for one
        anyway reported a perfectly good setup as "not configured", sending the
        user to fix a file that was already right.
    """
    if config.kind == BACKEND_LOCAL:
        return bool(config.model)

    if config.kind == BACKEND_API:
        return bool(config.endpoint)

    return bool(config.command)


def _unavailable_fix(config) -> str:
    """
    What to do about a backend that is configured but not answering.

    Each kind fails its own way, so a single "check your settings" would be
    true and useless. A local runtime is usually not started; a command is
    usually not on PATH; an API is usually missing its key.
    """
    if config.kind == BACKEND_LOCAL:
        return f"Start the local runtime, or pull the model: ollama pull {config.model or '<model>'}"

    if config.api_key_env:
        return f"Set the {config.api_key_env} environment variable to your API key"

    return CONFIGURE_FIX
