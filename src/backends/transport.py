"""
HTTP Transport.

How bytes actually move for the two HTTP backends. Separated from the adapter
so that `adapter.py` stays what it says it is — the interface and the shapes —
and this stays the one place a socket is opened.

Standard library only, for the same reason the splitter shells out to ffmpeg
rather than importing a binding: one fewer dependency to pin, and nothing that
reorganises itself under us. What happens here is a POST with a JSON body;
there is nothing a package would do better.
"""

import json
from typing import Any, Dict

from src.backends.adapter import BackendError


def post_json(
    url: str,
    body: Dict[str, Any],
    headers: Dict[str, str],
    timeout: int,
) -> Dict[str, Any]:
    """
    Posts JSON and returns the decoded reply.

    Uses the standard library rather than an HTTP package, for the same reason
    the splitter shells out to ffmpeg instead of importing a binding: one fewer
    dependency to pin, and nothing that reorganises itself under us. The
    requests here are a POST with a JSON body — there is nothing a library
    would do better.

    Raises:
        BackendError: On a transport failure, a non-success status, or a body
            that is not JSON. Never quotes the headers, because one of them is
            a credential.
    """
    # Imported here rather than at module level: a config using only the
    # command backend should not pay to import the HTTP stack
    import urllib.request

    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = _http_error_detail(error)
        raise BackendError(f"{url} returned {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise BackendError(f"Could not reach {url}: {error.reason}") from error
    except TimeoutError as error:
        raise BackendError(f"{url} did not answer within {timeout}s") from error

    try:
        return json.loads(payload)
    except json.JSONDecodeError as error:
        raise BackendError(f"{url} returned something that is not JSON: {payload[:200]}") from error


def _http_error_detail(error: Any) -> str:
    """
    The useful part of an error body.

    APIs explain refusals — a wrong key, a model that does not exist, an image
    too large — in the body rather than the status line. Surfacing it is the
    difference between "400" and "your key does not have access to this model".
    """
    try:
        body = error.read().decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - an unreadable body must not mask the status
        return error.reason or "no detail"

    try:
        import json

        decoded = json.loads(body)
        message = decoded.get("error")
        if isinstance(message, dict):
            message = message.get("message")
        return str(message or body)[:300]
    except Exception:  # noqa: BLE001 - a non-JSON body is still worth quoting
        return body[:300] or (error.reason or "no detail")
