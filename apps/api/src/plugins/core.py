"""Core plugins: always loaded (never named in `PLUGINS`), their ids reserved, and not apps people
connect (left out of `GET /plugins`). Team hands tasks to teammates (ADR 0014); Files keeps a
bot's files and Browser opens web pages for it (ADR 0017); Computer works on its cloud computer
(ADR 0020)."""

from src.plugins.browser import BROWSER_PLUGIN_ID
from src.plugins.computer import COMPUTER_PLUGIN_ID
from src.plugins.files import FILES_PLUGIN_ID
from src.plugins.team import TEAM_PLUGIN_ID

CORE_PLUGIN_IDS = frozenset({TEAM_PLUGIN_ID, FILES_PLUGIN_ID, BROWSER_PLUGIN_ID, COMPUTER_PLUGIN_ID})
