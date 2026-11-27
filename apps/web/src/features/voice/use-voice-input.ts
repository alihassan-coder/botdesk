import { useCallback, useState } from "react";
import { toast } from "sonner";
import { actions, useVoice } from "@/data/store";
import { useVoiceRecorder } from "./use-voice-recorder";

export const TOO_SHORT = "That was too short to hear. Hold the recording a little longer.";
export const NOTHING_HEARD = "We didn't catch anything. Try again closer to the microphone.";

/**
 * Talk instead of typing (ADR 0021): record, then the best speech model your keys reach writes it
 * down and `onText` gets the words. Nothing is sent to a bot; the words go into the message box.
 * `hint` gives the names in the chat, so the model spells them right.
 */
export function useVoiceInput({ hint, onText }: { hint: () => string; onText: (text: string) => void }) {
  const voice = useVoice();
  const [transcribing, setTranscribing] = useState(false);

  const onRecorded = useCallback(
    async (audio: Blob, seconds: number) => {
      if (seconds < 0.6) {
        toast(TOO_SHORT);
        return;
      }
      setTranscribing(true);
      const result = await actions.transcribe(audio, hint());
      setTranscribing(false);
      if (!result.ok) toast.error(result.error);
      else if (!result.text) toast(NOTHING_HEARD);
      else onText(result.text);
    },
    [hint, onText],
  );
  const recorder = useVoiceRecorder({ onRecorded, onError: (message) => toast.error(message) });

  return {
    ...recorder,
    transcribing,
    /** The microphone works: a speech model is reachable with your keys. */
    available: voice.current?.available ?? false,
    /** When it doesn't: how to turn it on. */
    unavailable: voice.current?.message ?? (voice.status === "loading" ? "Checking whether voice is available…" : undefined),
    /** Who writes it down, for the button's tooltip ("Groq · whisper-large-v3"). */
    writtenBy: voice.current?.available ? [voice.current.provider, voice.current.model].filter(Boolean).join(", ") : undefined,
  };
}

export type VoiceInput = ReturnType<typeof useVoiceInput>;
