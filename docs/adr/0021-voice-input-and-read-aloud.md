# 0021: Voice input, and reading replies aloud

- Status: accepted (owner asked for a voice mode on 2026-11-27; the choices below are mine)
- Date: 2026-11-27
- Based on: [ADR 0008](0008-free-and-open-source.md) (free, bring your own keys)

## Context

The owner wants to explain a task by talking instead of typing ("voice mode… use the best model a person has"). BotDesk is free and runs on the keys people bring (ADR 0008), so speech-to-text has to use those keys too, and pick the best speech model those keys reach.

## Decisions

### 1. Voice input: record in the browser, write it down on the API

- The composer gets a **microphone button**. Click it to record and click again (or press Enter) to stop. Esc cancels. While it records, it shows the time and a live level meter. It stops on its own at **10 minutes**.
- The browser records with `MediaRecorder` (WebM/Opus, or MP4 on Safari) and sends the audio to `POST /api/v1/orgs/{org}/voice/transcriptions`. The API sends it to the speech model and returns the text, which goes **into the message box at the caret**. Nothing is sent to a bot until you press Send, so you can fix a misheard word first.
- **Why not the browser's own speech recognition:** Chrome's sends your voice to Google with no key or choice, other browsers lack it, and it's weaker than Whisper-class models. A key you chose is consistent with ADR 0008.
- **The audio is never stored or logged.** It passes through memory only, at most **25 MB** (the providers' limit).
- **Names:** the client sends a short hint (the chat's title and the names of the bots and people in it, at most 300 characters), passed to the model as its `prompt`, so names like "BotDesk" or a bot's name are spelled right.

### 2. Which model: the best one your keys reach

- Providers with a speech-to-text API: **OpenAI** (`/audio/transcriptions`: the `gpt-4o-transcribe` family and `whisper-1`) and **Groq** (the same API: `whisper-large-v3`, `whisper-large-v3-turbo`). Anthropic, Gemini and OpenRouter have none we can use the same way. Custom servers vary, so they aren't tried.
- **OpenAI first** (most accurate), then **Groq** (fast, has a free tier). Each provider's key is found the same way a run's is: **your own key first, then the organization's, then the server's**.
- **Within a provider, the model comes from its live model list** (cached 10 minutes), so newer models are picked up without a release:
  - OpenAI: a full `…transcribe` model before a `mini` one, then `whisper-1`. Diarize, realtime and preview models are skipped.
  - Groq: `whisper-large-v3` before `whisper-large-v3-turbo`, then any other `whisper` model.
- `GET /api/v1/orgs/{org}/voice` tells the composer whether voice is available, and with which provider and model. With no speech-capable key, the button is shown off, with a hint: "Voice needs an OpenAI or Groq key. Add one in Settings → Models & keys."
- Usage is **not recorded yet**: no bot is involved, and the cost is small (about $0.006 a minute on OpenAI, less on Groq). The provider bills the key's owner. Showing it on the Usage page is a follow-up.

### 3. Read aloud

- Every bot message gets a **Read aloud** action. It uses the browser's own speech synthesis (`speechSynthesis`): local, free, no key. Click it again to stop. Markdown is read as plain text, and code blocks are skipped ("code block").
- A provider's text-to-speech (for example OpenAI's voices) can come later behind the same button.

## Trade-offs

- Dictation, not a live voice conversation. Talking back and forth hands-free (record → send → read the reply aloud) can be built on these two pieces later.
- The browser asks for microphone permission once per site. If it's refused, the button says how to allow it.
