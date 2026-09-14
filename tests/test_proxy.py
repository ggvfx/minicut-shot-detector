"""
Tests for the Review Proxy's Filter Chain.

The frame counter is a convenience; the proxy is not. What is tested here is
that the convenience can never take the proxy down with it.

This is not hypothetical. Homebrew's ffmpeg bottle is built without
libfreetype and so has no `drawtext` filter at all, and ffmpeg does not skip a
filter it does not recognise — it rejects the entire output with "Filter not
found". The result on a Mac was a splitter that could not build a proxy, could
not therefore run, and said only that a filter was missing.
"""

from typing import Set

import pytest

from src.core import config
from src.core.ffmpeg_tools import MediaToolchain
from src.media.proxy import PROXY_WIDTH, ProxyBuilder

# --- HELPERS ---


class FakeToolchain(MediaToolchain):
    """A toolchain with a chosen set of filters and no ffmpeg to ask."""

    def __init__(self, filters: Set[str]):
        super().__init__(discover=False)
        self._filters = filters


@pytest.fixture
def font(monkeypatch):
    """Pins a font, so the two reasons the counter can vanish stay separable."""
    monkeypatch.setattr(ProxyBuilder, "font_path", lambda _builder: "/fonts/mono.ttf")


# --- WHEN DRAWTEXT IS THERE ---


def test_the_counter_is_burned_in_when_the_filter_exists(font):  # noqa: ARG001
    builder = ProxyBuilder(FakeToolchain({config.DRAWTEXT_FILTER, "scale"}))

    chain = builder.video_filter()

    assert chain.startswith(f"scale={PROXY_WIDTH}:-2")
    assert "drawtext" in chain
    assert "%{n}" in chain, "the counter shows the frame number"


def test_a_windows_font_path_is_escaped_for_ffmpegs_parser(monkeypatch):
    """
    ffmpeg reads a colon as an argument separator, so "C:/..." has to be
    written "C\\:/..." or the filter is parsed as nonsense.
    """
    monkeypatch.setattr(ProxyBuilder, "font_path", lambda _builder: "C:/Windows/Fonts/consola.ttf")
    builder = ProxyBuilder(FakeToolchain({config.DRAWTEXT_FILTER}))

    assert r"C\:/Windows/Fonts/consola.ttf" in builder.video_filter()


# --- WHEN IT IS NOT ---


def test_an_ffmpeg_without_drawtext_still_gets_a_usable_chain(font):  # noqa: ARG001
    """
    The Homebrew case, and the one that stopped a real machine working.

    Asking for a filter this build does not have makes ffmpeg reject the whole
    output, so the proxy never gets written and the splitter cannot run at all.
    Dropping the counter costs the burned-in numbers; asking anyway costs the
    job.
    """
    builder = ProxyBuilder(FakeToolchain({"scale", "crop"}))

    chain = builder.video_filter()

    assert chain == f"scale={PROXY_WIDTH}:-2"
    assert "drawtext" not in chain


def test_the_scaling_survives_the_counter_being_dropped(font):  # noqa: ARG001
    """
    The proxy's size is why it seeks instantly in a browser. Losing that along
    with the counter would turn a cosmetic degradation into a slow player.
    """
    builder = ProxyBuilder(FakeToolchain(set()))

    assert f"scale={PROXY_WIDTH}:-2" in builder.video_filter()


def test_a_machine_with_no_font_also_degrades(monkeypatch):
    """
    The other way the counter can vanish, and it must behave the same way.

    Tested separately from the missing filter because they are independent
    causes with one shared outcome, and a fix for either could quietly break
    the other.
    """
    monkeypatch.setattr(ProxyBuilder, "font_path", lambda _builder: None)
    builder = ProxyBuilder(FakeToolchain({config.DRAWTEXT_FILTER}))

    assert builder.video_filter() == f"scale={PROXY_WIDTH}:-2"
