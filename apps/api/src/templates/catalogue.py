"""The marketplace's templates, kept in `catalogue.json` beside this file so they're reviewed and
versioned like code, and so the web's demo can check it shows the same ones
(`apps/web/src/data/mock/templates.test.ts`). Add one by appending an entry; ids are stable (the
web and hires key on them).

`plugins` names the plugins a template works in by id ("gmail"); hiring switches the ones this
server loaded on in the bot's Tools. `securityLevel` is how careful the job needs the bot to be;
hiring uses it or the organization's default, whichever is stricter.
"""

from pathlib import Path

from pydantic import TypeAdapter

from src.schemas.template import TemplateOut

CATALOGUE = Path(__file__).with_name("catalogue.json")

TEMPLATES: tuple[TemplateOut, ...] = tuple(TypeAdapter(list[TemplateOut]).validate_json(CATALOGUE.read_bytes()))
