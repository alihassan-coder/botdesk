"""Plugins: what bots can do. `sdk.py` is the seam, `registry.py` collects the tools.

Built-in plugins are listed here by id. Each entry builds a fresh manifest, so every app
(and every test) gets its own plugin state. Entry points and the plugin SDK package replace
this list in build step 3 (ADR 0006).
"""

from collections.abc import Callable

from src.plugins.demo import demo_plugin
from src.plugins.sdk import PluginManifest

BUILTIN_PLUGINS: dict[str, Callable[[], PluginManifest]] = {"demo": demo_plugin}
