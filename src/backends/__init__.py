"""
Model Backends.

Everything that sends a prompt somewhere and gets text back. Nothing else in
the project talks to a model directly.

Three implementations behind one interface: a configured CLI command, an HTTP
API, and a local runtime. **The command and API paths are the product; local is
the option.** This is built to be handed to people whose machines are nothing
like the one it was written on, so no caller may assume local inference — not
its speed, not its context size, not that a failed call can simply be repeated.

Vision and text are configured separately. A studio may run every text pass
through an agentic CLI it already licenses, and have to point image work
somewhere else entirely.
"""
