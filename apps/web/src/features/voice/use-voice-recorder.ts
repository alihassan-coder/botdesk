import { useCallback, useEffect, useRef, useState } from "react";

/** A recording stops by itself after this long (ADR 0021): the providers take about 25 MB. */
export const MAX_RECORDING_SECONDS = 600;

export type RecorderPhase = "idle" | "starting" | "recording";

// Opus in WebM where the browser has it (Chrome, Edge, Firefox), MP4 on Safari.
const MIME_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];

/** The first recording format the browser supports, or undefined to let it choose. */
export function pickMimeType(isSupported: (type: string) => boolean): string | undefined {
  return MIME_TYPES.find((type) => isSupported(type));
}

/** What to tell someone whose microphone didn't start, by the browser's error. */
export function microphoneError(error: unknown): string {
  const name = error instanceof DOMException ? error.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") {
    return "Your browser blocked the microphone. Allow it with the icon in the address bar, then try again.";
  }
  if (name === "NotFoundError" || name === "OverconstrainedError") return "No microphone found. Plug one in and try again.";
  if (name === "NotReadableError") return "Another app is using the microphone. Close it and try again.";
  return "The microphone didn't start. Try again.";
}

export const CANT_RECORD = "This browser can't record audio. Try a recent Chrome, Edge, Firefox or Safari.";

interface Recording {
  recorder: MediaRecorder;
  stream: MediaStream;
  context: AudioContext;
  chunks: Blob[];
  keep: boolean;
  timer: number;
}

/**
 * Records your voice: `start` asks for the microphone, `stop` hands the recording to `onRecorded`,
 * `cancel` throws it away. `analyser` feeds the level meter while it records. The microphone is
 * released as soon as it stops (the browser's recording light goes off), and on unmount.
 */
export function useVoiceRecorder({
  onRecorded,
  onError,
}: {
  onRecorded: (audio: Blob, seconds: number) => void;
  onError: (message: string) => void;
}) {
  const [phase, setPhase] = useState<RecorderPhase>("idle");
  const [seconds, setSeconds] = useState(0);
  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null);
  const current = useRef<Recording | null>(null);
  const starting = useRef(false);
  const mounted = useRef(true);
  const callbacks = useRef({ onRecorded, onError });
  useEffect(() => {
    callbacks.current = { onRecorded, onError };
  });

  const release = useCallback(() => {
    const recording = current.current;
    if (!recording) return;
    window.clearInterval(recording.timer);
    recording.stream.getTracks().forEach((track) => track.stop());
    void recording.context.close().catch(() => {});
    current.current = null;
    setAnalyser(null);
  }, []);

  const finish = useCallback(
    (keep: boolean) => {
      const recording = current.current;
      if (!recording) return;
      recording.keep = keep;
      // Its `onstop` hands the recording over (or throws it away) and releases the microphone.
      if (recording.recorder.state !== "inactive") recording.recorder.stop();
      else release();
      setPhase("idle");
    },
    [release],
  );

  const start = useCallback(async () => {
    if (current.current || starting.current) return;
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      callbacks.current.onError(CANT_RECORD);
      return;
    }
    starting.current = true;
    setPhase("starting");
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch (error) {
      starting.current = false;
      if (!mounted.current) return;
      setPhase("idle");
      callbacks.current.onError(microphoneError(error));
      return;
    }
    // Left the chat while the browser asked: let the microphone go at once.
    if (!mounted.current) {
      stream.getTracks().forEach((track) => track.stop());
      starting.current = false;
      return;
    }
    const mimeType = pickMimeType((type) => MediaRecorder.isTypeSupported(type));
    let recorder: MediaRecorder;
    let context: AudioContext;
    let node: AnalyserNode;
    try {
      recorder = new MediaRecorder(stream, mimeType ? { mimeType, audioBitsPerSecond: 48_000 } : undefined);
      context = new AudioContext();
      node = context.createAnalyser();
      node.fftSize = 1024;
      context.createMediaStreamSource(stream).connect(node);
    } catch {
      stream.getTracks().forEach((track) => track.stop());
      starting.current = false;
      setPhase("idle");
      callbacks.current.onError(CANT_RECORD);
      return;
    }
    const startedAt = performance.now();
    const recording: Recording = { recorder, stream, context, chunks: [], keep: true, timer: 0 };
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) recording.chunks.push(event.data);
    };
    recorder.onstop = () => {
      const length = (performance.now() - startedAt) / 1000;
      const type = recorder.mimeType || mimeType || "audio/webm";
      release();
      if (recording.keep && recording.chunks.length > 0) callbacks.current.onRecorded(new Blob(recording.chunks, { type }), length);
    };
    recording.timer = window.setInterval(() => {
      const elapsed = Math.floor((performance.now() - startedAt) / 1000);
      setSeconds(elapsed);
      if (elapsed >= MAX_RECORDING_SECONDS) finish(true);
    }, 250);
    current.current = recording;
    starting.current = false;
    setSeconds(0);
    setAnalyser(node);
    recorder.start(1000);
    setPhase("recording");
  }, [finish, release]);

  // Leaving the chat mid-recording throws the recording away and frees the microphone.
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(
    () => () => {
      const recording = current.current;
      if (!recording) return;
      recording.keep = false;
      if (recording.recorder.state !== "inactive") recording.recorder.stop();
      release();
    },
    [release],
  );

  return {
    phase,
    seconds,
    analyser,
    start,
    stop: useCallback(() => finish(true), [finish]),
    cancel: useCallback(() => finish(false), [finish]),
  };
}
