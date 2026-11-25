# 0018: Bots see images

- Status: proposed (2026-11-25; needs the owner's OK before any code)
- Date: 2026-11-25
- Based on: [ADR 0004](0004-agent-runtime-and-safety.md) (runs, taint), [ADR 0017](0017-bot-browsers-and-file-storage.md) (files, browser)

## Context

Bots now keep files (images among them), take screenshots of web pages, and get files attached in chat. But they can't look at any of it: `files.read` says "This isn't a text file", and a screenshot is only a file name. Most models people connect today can read images (Claude, GPT-4o and later, Gemini; some Groq and OpenRouter models), so a bot that could look would read charts, receipts, scanned pages, and whatever a web page shows but doesn't say in text.

Two things make this more than "return the image from the tool":

1. **Where images live.** A run's turns are saved in its LangGraph checkpoint on every step. A screenshot is ~100 KB, ~140 KB as base64, so a run that looks at ten pictures would add megabytes to every checkpoint write, kept until checkpoints are cleaned up.
2. **Providers differ.** Anthropic accepts an image inside a tool result. OpenAI's Chat Completions API only takes text in a tool message, so an image must go in a following user message. Some models can't read images at all.

## Decision (proposed)

1. **A `look` tool per source:** `files.look(path, shared?)` and `browser.look()` (the page as it is now). Risk `read`; the result is outside content, so it taints the run like reading a page.
2. **References in the run, images at the call.** The tool result saved in the checkpoint is text plus a reference (`{"image": {"fileId": …}}`; a browser look is first saved to the bot's files as `screenshots/…`). When the graph builds the messages for the next model call, it replaces each reference in the **last few turns** (at most 3 images per call) with the image itself, read from storage, scaled down to at most 1568 px on the long side (Pillow, MIT-CMU licence) and sent as JPEG. Older references stay text ("[image: screenshots/x.png]"). Checkpoints stay small, and a run carries on after a restart because the files are still there.
3. **Per provider, one adapter function:** Anthropic gets the image inside the tool result; OpenAI-compatible providers (OpenAI, Gemini, OpenRouter, Groq, custom) get the tool's text result, then a user message "Here is the image the tool returned:" with the image. The model adapters (`src/model_providers/`) own this, so the graph stays provider-blind.
4. **Can this model see?** The model catalog gets a `vision` flag: from the provider's model list where it says (OpenRouter's `input_modalities`, Anthropic's models), else a short built-in list of known families. A bot on a model without vision doesn't get the `look` tools, so it never tries.
5. **Cost.** Images are tokens (roughly 1,000–1,600 per scaled image). Usage already counts input tokens, so budgets cover it; the cap of 3 images per call keeps a long browsing run from sending every screenshot again on each step.

## Trade-offs

- Images are re-read from storage on each model call that includes them (a few hundred KB per call). Cheaper than keeping them in every checkpoint.
- A model without vision simply doesn't get the tools; people may wonder why. The bot's Tools tab says "needs a model that can see images".
- Video and audio stay out of scope.

## Owner decisions

1. Build this now (recommended), or later?
2. At most **3 images per model call**, scaled to **1568 px** (recommended), or other limits?
