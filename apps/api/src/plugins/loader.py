"""Finds plugins through Python entry points and loads only the allowlisted ones (ADR 0006).

Any installed package can declare a `botdesk.plugins` entry point, so being installed must
never be enough to run: the operator lists plugin ids in the `PLUGINS` setting, and only those
are imported. Importing a plugin runs its code, which is why the allowlist is checked first.

A plugin that fails to import, raises while building its manifest, or fails the SDK's checks
is skipped with one log line saying why. The API keeps running with the plugins that work.
"""

import logging
from collections import defaultdict
from importlib.metadata import EntryPoint, entry_points

from botdesk_plugin_sdk import ENTRY_POINT_GROUP, PluginError, PluginManifest, validate_manifest

logger = logging.getLogger(__name__)


def installed_plugins() -> dict[str, list[EntryPoint]]:
    """Every `botdesk.plugins` entry point by plugin id. Nothing is imported yet. More than one
    entry for an id means two packages claim it."""
    found: defaultdict[str, list[EntryPoint]] = defaultdict(list)
    for entry in entry_points(group=ENTRY_POINT_GROUP):
        found[entry.name].append(entry)
    return dict(found)


def load_plugin(plugin_id: str, entry: EntryPoint) -> PluginManifest:
    """Import one plugin and build its manifest. Raises `PluginError` if anything is wrong."""
    try:
        target = entry.load()
        # The entry point names a function that returns the manifest (so each app gets fresh
        # plugin state), or, for a stateless plugin, the manifest itself.
        manifest = target if isinstance(target, PluginManifest) else target()
    except (Exception, SystemExit) as error:  # a plugin calling sys.exit() must not stop the API
        raise PluginError(plugin_id, [f"loading {entry.value} failed: {type(error).__name__}: {error}"]) from error

    try:
        manifest = validate_manifest(manifest)
    except PluginError:
        raise
    except Exception as error:  # a manifest too broken to even inspect
        raise PluginError(plugin_id, [f"its manifest is malformed: {type(error).__name__}: {error}"]) from error
    if manifest.id != plugin_id:
        raise PluginError(plugin_id, [f"its manifest says id {manifest.id!r}, but the entry point is {plugin_id!r}"])
    return manifest


def load_plugins(allowlist: list[str]) -> list[PluginManifest]:
    """The manifests of the allowlisted plugins that load cleanly, in allowlist order.

    Raises `ValueError` for an allowlisted id that no installed package provides: that is a typo
    in the settings, and running without the plugin would be a confusing way to find out.
    """
    installed = installed_plugins()
    unknown = [plugin_id for plugin_id in allowlist if plugin_id not in installed]
    if unknown:
        names = ", ".join(sorted(installed)) or "none"
        raise ValueError(f"PLUGINS names {unknown[0]!r}, but there is no such plugin. Installed plugins: {names}.")

    manifests: list[PluginManifest] = []
    for plugin_id in dict.fromkeys(allowlist):  # keeps order, drops repeats
        entries = installed[plugin_id]
        if len(entries) > 1:
            sources = ", ".join(entry.value for entry in entries)
            logger.error("Plugin %r skipped: more than one installed package provides it (%s).", plugin_id, sources)
            continue
        try:
            manifests.append(load_plugin(plugin_id, entries[0]))
        except PluginError as error:
            logger.error("Plugin %r skipped: %s", plugin_id, "; ".join(error.problems))
            continue
        logger.info("Plugin %r loaded (%d tools).", plugin_id, len(manifests[-1].tools))
    return manifests
