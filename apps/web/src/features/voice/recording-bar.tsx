import { useEffect, useRef } from "react";
import { Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { Spinner } from "@/components/ui/spinner";
import type { VoiceInput } from "./use-voice-input";
import { MAX_RECORDING_SECONDS } from "./use-voice-recorder";
import { VoiceMeter } from "./voice-meter";

export function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

/**
 * Takes the message box's place while you talk: a red light, the time, your voice as bars, and
 * Cancel / Done. Enter finishes, Escape cancels. Then, while the words are written down, a spinner.
 */
export function RecordingBar({ voice }: { voice: VoiceInput }) {
  const done = useRef<HTMLButtonElement>(null);
  const recording = voice.phase === "recording";
  const nearTheEnd = recording && voice.seconds >= MAX_RECORDING_SECONDS - 30;

  // Focus moves to Done, so Enter finishes and the keyboard stays in the bar.
  useEffect(() => {
    if (recording) done.current?.focus();
  }, [recording]);

  return (
    <div
      role="group"
      aria-label={voice.transcribing ? "Writing down what you said" : "Recording your voice"}
      className="flex min-h-12 items-center gap-2 px-2"
      onKeyDown={(e) => {
        if (e.key === "Escape" && recording) {
          e.preventDefault();
          voice.cancel();
        }
      }}
    >
      {voice.transcribing ? (
        <p className="flex flex-1 items-center gap-2 text-sm text-muted-foreground">
          <Spinner className="size-4" /> Writing down what you said…
        </p>
      ) : voice.phase === "starting" ? (
        <p className="flex flex-1 items-center gap-2 text-sm text-muted-foreground">
          <Spinner className="size-4" /> Allow the microphone if your browser asks…
        </p>
      ) : (
        <>
          <span aria-hidden className="size-2.5 shrink-0 rounded-full bg-red-500 motion-safe:animate-pulse" />
          <time className={`w-11 shrink-0 text-sm tabular-nums ${nearTheEnd ? "font-medium text-red-600 dark:text-red-400" : ""}`}>
            {clock(voice.seconds)}
          </time>
          <VoiceMeter analyser={voice.analyser} className="min-w-0 flex-1" />
          <span className="hidden shrink-0 items-center gap-1 text-xs text-muted-foreground md:flex">
            <Kbd>Enter</Kbd> done <Kbd>Esc</Kbd> cancel
          </span>
        </>
      )}
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="shrink-0 rounded-full"
        aria-label="Cancel recording"
        disabled={!recording}
        onClick={voice.cancel}
      >
        <X />
      </Button>
      <Button
        ref={done}
        type="button"
        size="icon"
        className="shrink-0 rounded-full"
        aria-label="Done: write down what I said"
        disabled={!recording}
        onClick={voice.stop}
      >
        <Check />
      </Button>
      <p role="status" className="sr-only">
        {recording ? "Recording. Press Enter when you're done, or Escape to cancel." : voice.transcribing ? "Writing down what you said." : ""}
      </p>
    </div>
  );
}
