import { Mic } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { VoiceInput } from "./use-voice-input";

/**
 * The composer's microphone. Off (but still explaining why) when no key reaches a speech model:
 * clicking it then says how to turn voice on.
 */
export function VoiceButton({ voice, onStart }: { voice: VoiceInput; onStart?: () => void }) {
  const busy = voice.phase !== "idle" || voice.transcribing;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className={cn("shrink-0 rounded-full", !voice.available && "text-muted-foreground/60")}
          aria-label="Talk instead of typing"
          aria-disabled={!voice.available || busy}
          onClick={() => {
            if (busy) return;
            if (!voice.available) {
              toast(voice.unavailable ?? "Voice isn't available.");
              return;
            }
            onStart?.();
            void voice.start();
          }}
        >
          <Mic />
        </Button>
      </TooltipTrigger>
      <TooltipContent side="top">
        {voice.available ? `Talk instead of typing. Written down by ${voice.writtenBy}.` : (voice.unavailable ?? "Voice isn't available.")}
      </TooltipContent>
    </Tooltip>
  );
}
