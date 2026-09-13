"""
Tests for the Model Backends.

Nothing here talks to a real model. A CLI backend is tested against a real
subprocess — this interpreter, running a one-line script — and the HTTP
backends against a real server on a real socket. So the transport, the argument
building, the error handling and the response parsing are all genuinely
exercised, while the suite stays offline, free and fast.

That matters more here than usual: this is the layer that decides whether the
app works on someone else's machine, and a mock would only prove that the mock
matches what we assumed.
"""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from src.backends.adapter import (
    ANTHROPIC,
    OLLAMA,
    OPENAI,
    BackendConfig,
    BackendError,
    create_backend,
    extract_text,
    first_available,
)
from src.backends.command import CommandBackend
from src.backends.http_api import HttpApiBackend
from src.backends.local import LocalBackend

# --- A FAKE CLI ---

# Echoes its stdin back, which is what a model backend does from our side of
# the pipe. Using this interpreter means the test needs nothing installed.
ECHO_STDIN = [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read())"]

# Prints its arguments, so argument building can be asserted rather than assumed
PRINT_ARGS = [sys.executable, "-c", "import sys; print('|'.join(sys.argv[1:]))"]

FAILING = [sys.executable, "-c", "import sys; sys.stderr.write('model unavailable\\n'); sys.exit(3)"]

SILENT = [sys.executable, "-c", "pass"]


def command_config(command, **extra) -> BackendConfig:
    return BackendConfig(kind="command", command=command, timeout_seconds=30, **extra)


# --- A STUB SERVER ---


class StubHandler(BaseHTTPRequestHandler):
    """Answers with whatever the test put in `replies`, recording what it got."""

    replies: list = []
    received: list = []

    def _respond(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"

        StubHandler.received.append(
            {
                "path": self.path,
                "body": json.loads(raw) if raw else {},
                # Lowercased because HTTP header names are case-insensitive and
                # clients normalise them differently — asserting on the exact
                # case sent would be testing urllib, not us
                "headers": {name.lower(): value for name, value in self.headers.items()},
            }
        )

        status, payload = StubHandler.replies.pop(0) if StubHandler.replies else (200, {})
        body = json.dumps(payload).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802 - the name http.server requires
        self._respond()

    def do_GET(self):  # noqa: N802 - the name http.server requires
        self._respond()

    def log_message(self, *args):
        """Silences the per-request logging, which would bury the test output."""


@pytest.fixture
def stub_server():
    """A real HTTP server on a free port, torn down after the test."""
    StubHandler.replies = []
    StubHandler.received = []

    server = HTTPServer(("127.0.0.1", 0), StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield f"http://127.0.0.1:{server.server_port}", StubHandler

    server.shutdown()
    server.server_close()


# --- THE COMMAND BACKEND ---


def test_a_command_returns_what_it_prints():
    """The prompt goes in on stdin and the reply comes back on stdout."""
    backend = CommandBackend(command_config(ECHO_STDIN))

    reply = backend.send("describe this shot")

    assert reply.text == "describe this shot"
    assert reply.backend.startswith("command:")


def test_the_prompt_can_go_in_the_arguments_instead():
    """
    Some tools take the prompt as an argument rather than on stdin.

    Passed through the argument list rather than a shell, so quotes and
    newlines in a description survive — that is the bug that would only appear
    on someone else's machine.
    """
    backend = CommandBackend(command_config([*PRINT_ARGS, "{prompt}"]))

    reply = backend.send('a shot with "quotes" in it')

    assert 'a shot with "quotes" in it' in reply.text


def test_images_expand_to_one_argument_each(tmp_path):
    """`{images}` becomes one argument per frame, in the order given."""
    frames = []
    for index in range(3):
        frame = tmp_path / f"frame_{index}.jpg"
        frame.write_bytes(b"\xff\xd8\xff")
        frames.append(frame)

    backend = CommandBackend(command_config([*PRINT_ARGS, "{images}"]))
    reply = backend.send("prompt", images=frames)

    printed = reply.text.strip().split("|")
    assert printed == [str(frame) for frame in frames], "order is the only motion information"


def test_a_repeated_image_flag_is_expanded_per_frame(tmp_path):
    """`--image={image}` becomes one flag per frame, for tools that want that."""
    frames = [tmp_path / "a.jpg", tmp_path / "b.jpg"]
    for frame in frames:
        frame.write_bytes(b"\xff\xd8\xff")

    backend = CommandBackend(command_config([*PRINT_ARGS, "--image={image}"]))
    reply = backend.send("prompt", images=frames)

    assert reply.text.strip().split("|") == [f"--image={frames[0]}", f"--image={frames[1]}"]


def test_no_images_leaves_no_empty_argument():
    """
    An empty frame list must not leave a stray empty argument.

    Some tools read one of those as a filename and fail in a way that says
    nothing about what went wrong.
    """
    backend = CommandBackend(command_config([*PRINT_ARGS, "{images}", "end"]))

    assert backend.send("prompt").text.strip() == "end"


def test_a_missing_executable_says_so_rather_than_crashing():
    """One of the three failures 6.3 has to report clearly."""
    backend = CommandBackend(command_config(["definitely-not-a-real-command-xyz"]))

    with pytest.raises(BackendError, match="was not found"):
        backend.send("prompt")


def test_a_failing_command_quotes_its_stderr():
    """The tool's own message is what tells the user what to fix."""
    backend = CommandBackend(command_config(FAILING))

    with pytest.raises(BackendError, match="model unavailable"):
        backend.send("prompt")


def test_a_command_that_prints_nothing_is_an_error():
    """
    Empty output is a failure, not an empty description.

    A blank observation reads downstream as an unidentifiable shot, which hides
    a broken backend behind what looks like an ordinary result.
    """
    backend = CommandBackend(command_config(SILENT))

    with pytest.raises(BackendError, match="printed nothing"):
        backend.send("prompt")


def test_a_command_is_available_when_it_exists():
    """Availability resolves the executable without running it."""
    assert CommandBackend(command_config(ECHO_STDIN)).available()
    assert not CommandBackend(command_config(["not-a-real-command-xyz"])).available()
    assert not CommandBackend(command_config([])).available()


# --- THE HTTP API BACKEND ---


def test_an_api_call_returns_the_text(stub_server, monkeypatch):
    url, handler = stub_server
    handler.replies.append((200, {"content": [{"type": "text", "text": "a wide shot"}]}))
    monkeypatch.setenv("TEST_MODEL_KEY", "secret-value")

    backend = HttpApiBackend(
        BackendConfig(
            kind="api", endpoint=url, api_style=ANTHROPIC,
            api_key_env="TEST_MODEL_KEY", model="test-model",
        )
    )

    assert backend.send("describe this").text == "a wide shot"
    assert handler.received[0]["body"]["model"] == "test-model"


def test_the_key_is_sent_but_never_stored(stub_server, monkeypatch):
    """
    The key is read from the environment at call time and nowhere else.

    A config object that carried it would end up in a settings file, and a
    settings file is the sort of thing that gets copied between machines and
    committed by accident.
    """
    url, handler = stub_server
    handler.replies.append((200, {"content": [{"type": "text", "text": "ok"}]}))
    monkeypatch.setenv("TEST_MODEL_KEY", "secret-value")

    config = BackendConfig(
        kind="api", endpoint=url, api_key_env="TEST_MODEL_KEY", model="test-model"
    )
    HttpApiBackend(config).send("prompt")

    assert handler.received[0]["headers"]["x-api-key"] == "secret-value"
    assert "secret-value" not in config.model_dump_json()


def test_a_missing_key_names_the_variable_not_the_value(monkeypatch):
    """The second of the three failures 6.3 has to report clearly."""
    monkeypatch.delenv("TEST_MODEL_KEY", raising=False)

    backend = HttpApiBackend(
        BackendConfig(kind="api", endpoint="http://127.0.0.1:1", api_key_env="TEST_MODEL_KEY")
    )

    with pytest.raises(BackendError, match="TEST_MODEL_KEY is not set"):
        backend.send("prompt")


def test_a_refusal_carries_the_api_s_own_explanation(stub_server, monkeypatch):
    """
    APIs explain refusals in the body, not the status line.

    Surfacing it is the difference between "400" and "your key does not have
    access to this model".
    """
    url, handler = stub_server
    handler.replies.append((400, {"error": {"message": "model not found for this key"}}))
    monkeypatch.setenv("TEST_MODEL_KEY", "secret-value")

    backend = HttpApiBackend(
        BackendConfig(kind="api", endpoint=url, api_key_env="TEST_MODEL_KEY")
    )

    with pytest.raises(BackendError, match="model not found for this key"):
        backend.send("prompt")


def test_an_unreachable_endpoint_is_reported_not_raised_raw(monkeypatch):
    monkeypatch.setenv("TEST_MODEL_KEY", "secret-value")

    backend = HttpApiBackend(
        BackendConfig(
            kind="api", endpoint="http://127.0.0.1:1/none",
            api_key_env="TEST_MODEL_KEY", timeout_seconds=2,
        )
    )

    with pytest.raises(BackendError, match="Could not reach"):
        backend.send("prompt")


def test_api_availability_does_not_call_the_endpoint(monkeypatch):
    """
    A panel that spent a token per refresh would be a running charge for
    looking at a status light.
    """
    monkeypatch.setenv("TEST_MODEL_KEY", "secret-value")
    config = BackendConfig(
        kind="api", endpoint="http://127.0.0.1:1/none", api_key_env="TEST_MODEL_KEY"
    )

    assert HttpApiBackend(config).available(), "unreachable, but configured and keyed"

    monkeypatch.delenv("TEST_MODEL_KEY")
    assert not HttpApiBackend(config).available()


# --- THE LOCAL BACKEND ---


def test_a_local_call_returns_the_text(stub_server):
    url, handler = stub_server
    handler.replies.append((200, {"response": "two people on a beach"}))

    backend = LocalBackend(BackendConfig(kind="local", endpoint=url, model="test-vlm"))

    assert backend.send("describe this").text == "two people on a beach"
    assert handler.received[0]["path"] == "/api/generate"


def test_an_unreachable_runtime_says_how_to_start_it():
    """
    The third of the three failures 6.3 has to report clearly.

    Both ways this fails are one command from fixed, so the message carries the
    command — the same approach as the splitter's dependency panel.
    """
    backend = LocalBackend(
        BackendConfig(
            kind="local", endpoint="http://127.0.0.1:1", model="test-vlm", timeout_seconds=2
        )
    )

    with pytest.raises(BackendError, match="ollama serve"):
        backend.send("prompt")


def test_a_missing_model_says_how_to_pull_it(stub_server):
    url, handler = stub_server
    handler.replies.append((404, {"error": "model 'test-vlm' not found"}))

    backend = LocalBackend(BackendConfig(kind="local", endpoint=url, model="test-vlm"))

    with pytest.raises(BackendError, match="ollama pull test-vlm"):
        backend.send("prompt")


def test_local_availability_needs_the_model_to_be_installed(stub_server):
    url, handler = stub_server
    handler.replies.append((200, {"models": [{"name": "qwen2.5vl:latest"}]}))

    assert LocalBackend(BackendConfig(kind="local", endpoint=url, model="qwen2.5vl")).available(), (
        "a config naming the model without its tag is the same model"
    )

    handler.replies.append((200, {"models": [{"name": "qwen2.5vl:latest"}]}))
    assert not LocalBackend(
        BackendConfig(kind="local", endpoint=url, model="something-else")
    ).available()


def test_an_absent_runtime_is_not_a_fault():
    """
    Nothing listening is the common case on a machine that uses a CLI.

    It must report as unavailable rather than raise: a missing local option is
    not an error, and the panel has to stay green.
    """
    backend = LocalBackend(BackendConfig(kind="local", endpoint="http://127.0.0.1:1", model="x"))

    assert backend.available() is False


# --- ALL THREE, THE SAME WAY ---


def test_the_same_prompt_returns_text_through_all_three(stub_server, monkeypatch):
    """
    The point of the whole layer: one interface, three implementations.

    This is what lets a studio run its text passes through a CLI it already
    licenses and point image work somewhere else, without a line of identifier
    code knowing which is which.
    """
    url, handler = stub_server
    monkeypatch.setenv("TEST_MODEL_KEY", "secret-value")
    handler.replies = [
        (200, {"content": [{"type": "text", "text": "from the api"}]}),
        (200, {"response": "from the local runtime"}),
    ]

    backends = [
        create_backend(command_config(ECHO_STDIN)),
        create_backend(
            BackendConfig(kind="api", endpoint=url, api_key_env="TEST_MODEL_KEY", model="m")
        ),
        create_backend(BackendConfig(kind="local", endpoint=url, model="m")),
    ]

    replies = [backend.send("a prompt") for backend in backends]

    assert [reply.text for reply in replies] == [
        "a prompt",
        "from the api",
        "from the local runtime",
    ]
    assert all(reply.backend for reply in replies), "each reply records what produced it"


def test_an_unknown_backend_kind_is_refused():
    with pytest.raises(BackendError, match="Unknown backend kind"):
        create_backend(BackendConfig(kind="telepathy"))


def test_first_available_picks_the_first_that_works(monkeypatch):
    """
    How the panel chooses without the user having to.

    A local runtime that is not there is skipped rather than failing the whole
    thing — that is the difference between "no GPU" and "no backend".
    """
    monkeypatch.delenv("TEST_MODEL_KEY", raising=False)

    chosen = first_available(
        [
            BackendConfig(kind="local", endpoint="http://127.0.0.1:1", model="absent"),
            BackendConfig(kind="api", endpoint="http://x", api_key_env="TEST_MODEL_KEY"),
            command_config(ECHO_STDIN),
        ]
    )

    assert chosen is not None
    assert chosen.config.kind == "command"


def test_nothing_configured_gives_nothing():
    """The honest answer on a machine where nothing has been set up."""
    assert first_available([]) is None


# --- READING REPLIES ---


@pytest.mark.parametrize(
    "style, payload, expected",
    [
        (ANTHROPIC, {"content": [{"text": "one"}, {"text": " two"}]}, "one two"),
        (OPENAI, {"choices": [{"message": {"content": "answer"}}]}, "answer"),
        (OLLAMA, {"response": "answer"}, "answer"),
    ],
)
def test_each_dialect_is_read_from_where_it_puts_the_text(style, payload, expected):
    assert extract_text(payload, style) == expected


def test_a_reply_in_the_wrong_dialect_says_what_was_there():
    """
    The usual cause is an endpoint speaking a different dialect than
    configured, which is a one-line fix once you can see it.
    """
    with pytest.raises(BackendError, match="choices"):
        extract_text({"choices": [{"message": {"content": "hello"}}]}, ANTHROPIC)


def test_an_empty_reply_is_an_error_not_an_empty_description():
    with pytest.raises(BackendError, match="returned no text"):
        extract_text({"content": []}, ANTHROPIC)
