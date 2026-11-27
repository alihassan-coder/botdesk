import { useEffect, useSyncExternalStore } from "react";
import { Square, Volume2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { bestVoice, speakableText, speechChunks } from "@/lib/speech";

/*
 * Read aloud (ADR 0021 §3) with the browser's own voices: local, free, no key. One message at a
 * time: starting another stops the first. The message being read is kept here, outside React, so
 * every button knows whether it's the one speaking.
 */

let speaking: string | null = null;
const listeners = new Set<() => void>();

function setSpeaking(id: string | null) {
  speaking = id;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

const synth = () => (typeof window !== "undefined" && "speechSynthesis" in window ? window.speechSynthesis : null);

// Chrome lists its voices only after a first ask (then "voiceschanged" fires).
synth()?.getVoices();

export function speak(id: string, markdown: string): void {
  const speech = synth();
  if (!speech) return;
  speech.cancel();
  const chunks = speechChunks(speakableText(markdown));
  if (chunks.length === 0) return;
  const voice = bestVoice(speech.getVoices(), document.documentElement.lang || navigator.language || "en");
  setSpeaking(id);
  chunks.forEach((chunk, i) => {
    const utterance = new SpeechSynthesisUtterance(chunk);
    if (voice) {
      utterance.voice = voice;
      utterance.lang = voice.lang;
    }
    const ended = () => {
      if (speaking === id) setSpeaking(null);
    };
    if (i === chunks.length - 1) utterance.onend = ended;
    // "interrupted" and "canceled" come from stopping, which already cleared it.
    utterance.onerror = ended;
    speech.speak(utterance);
  });
}

export function stopSpeaking(): void {
  synth()?.cancel();
  setSpeaking(null);
}

const canSpeak = () => synth() !== null;

/** A bot message's Read aloud / Stop reading button. Hidden where the browser can't speak. */
export function ReadAloudButton({ id, text }: { id: string; text: string }) {
  const supported = useSyncExternalStore(subscribe, canSpeak, () => false);
  const active = useSyncExternalStore(subscribe, () => speaking === id, () => false);

  // Leaving the chat stops its message being read.
  useEffect(
    () => () => {
      if (speaking === id) stopSpeaking();
    },
    [id],
  );

  if (!supported) return null;
  return (
    <Button
      variant="ghost"
      size="icon-xs"
      aria-label={active ? "Stop reading" : "Read aloud"}
      aria-pressed={active}
      className="tap-target text-muted-foreground hover:text-foreground"
      onClick={() => (active ? stopSpeaking() : speak(id, text))}
    >
      {active ? <Square className="fill-current" /> : <Volume2 />}
    </Button>
  );
}
