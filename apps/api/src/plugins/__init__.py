"""Plugins: what bots can do.

The plugin contract (manifests, tools, risk classes) lives in the separate `botdesk_plugin_sdk`
package (packages/plugin-sdk); this app only knows that contract, never a specific plugin.
`loader.py` finds allowlisted plugins through `botdesk.plugins` entry points, and
`registry.py` collects their tools under full names. Built-in plugins live in `plugins/` at the
repo root, each its own package (ADR 0006).
"""
