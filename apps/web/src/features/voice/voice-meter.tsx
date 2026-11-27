import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";

const BAR = 3;
const GAP = 2;

/** How loud a slice of audio is, 0 to 1 (speech sits around 0.2 to 0.8). */
export function levelOf(samples: Uint8Array): number {
  let sum = 0;
  for (const sample of samples) {
    const x = (sample - 128) / 128;
    sum += x * x;
  }
  return Math.min(1, Math.sqrt(sum / Math.max(1, samples.length)) * 4);
}

/**
 * Your voice as it's recorded: bars that scroll in from the right, as tall as you are loud, so you
 * can see the microphone hears you. Drawn on a canvas each frame; nothing re-renders.
 */
export function VoiceMeter({ analyser, className }: { analyser: AnalyserNode | null; className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context || !analyser) return;
    const samples = new Uint8Array(analyser.fftSize);
    const levels: number[] = [];
    const color = getComputedStyle(canvas).color;
    let frame = 0;

    const draw = () => {
      const scale = window.devicePixelRatio || 1;
      const width = Math.round(canvas.clientWidth * scale);
      const height = Math.round(canvas.clientHeight * scale);
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }
      analyser.getByteTimeDomainData(samples);
      const bar = BAR * scale;
      const step = (BAR + GAP) * scale;
      const fits = Math.max(1, Math.floor(width / step));
      levels.push(levelOf(samples));
      while (levels.length > fits) levels.shift();

      context.clearRect(0, 0, width, height);
      context.fillStyle = color;
      levels.forEach((level, i) => {
        const barHeight = Math.max(bar, level * height);
        const x = width - (levels.length - i) * step;
        context.globalAlpha = 0.35 + 0.65 * ((i + 1) / levels.length);
        context.beginPath();
        context.roundRect(x, (height - barHeight) / 2, bar, barHeight, bar / 2);
        context.fill();
      });
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [analyser]);

  return <canvas ref={ref} aria-hidden className={cn("h-8 w-full text-brand", className)} />;
}
