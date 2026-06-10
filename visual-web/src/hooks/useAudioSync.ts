import { useCallback, useEffect, useRef, useState } from "react";
import type { SceneMood } from "../lib/mood";
import type { MoodOverride } from "./useVisualState";

function idleLevel(t: number): number {
  return 0.04 + 0.03 * Math.sin(t * 0.9) + 0.02 * Math.sin(t * 1.7 + 1.2);
}

function buildDemoEnvelope(durationS: number, fps: number): Float32Array {
  const n = Math.floor(durationS * fps);
  const envelope = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const phase = i / fps;
    let v = 0.25 + 0.75 * Math.abs(Math.sin(phase * 3)) ** 0.7;
    v *= 0.4 + 0.6 * Math.sin((i / n) * Math.PI) ** 0.5;
    envelope[i] = Math.min(1, Math.max(0.05, v));
  }
  return envelope;
}

function rmsEnvelope(samples: Float32Array, sampleRate: number, fps: number): Float32Array {
  const frameSamples = Math.max(1, Math.floor(sampleRate / fps));
  const nFrames = Math.ceil(samples.length / frameSamples);
  const out = new Float32Array(nFrames);
  for (let f = 0; f < nFrames; f++) {
    const start = f * frameSamples;
    const end = Math.min(samples.length, start + frameSamples);
    let sum = 0;
    for (let i = start; i < end; i++) sum += samples[i] * samples[i];
    out[f] = Math.sqrt(sum / (end - start));
  }
  let peak = 0;
  for (let i = 0; i < out.length; i++) peak = Math.max(peak, out[i]);
  if (peak > 0) {
    for (let i = 0; i < out.length; i++) out[i] = Math.min(1, out[i] / peak);
  }
  return out;
}

async function decodeMonoSamples(url: string): Promise<{ samples: Float32Array; sampleRate: number }> {
  const res = await fetch(url);
  const buf = await res.arrayBuffer();
  const ctx = new AudioContext();
  try {
    const audio = await ctx.decodeAudioData(buf.slice(0));
    const ch = audio.numberOfChannels > 1 ? 1 : 0;
    const data = audio.getChannelData(ch);
    if (audio.numberOfChannels > 1) {
      const mixed = new Float32Array(audio.length);
      for (let c = 0; c < audio.numberOfChannels; c++) {
        const channel = audio.getChannelData(c);
        for (let i = 0; i < audio.length; i++) mixed[i] += channel[i];
      }
      for (let i = 0; i < mixed.length; i++) mixed[i] /= audio.numberOfChannels;
      return { samples: mixed, sampleRate: audio.sampleRate };
    }
    return { samples: new Float32Array(data), sampleRate: audio.sampleRate };
  } finally {
    await ctx.close();
  }
}

export interface AudioSyncResult {
  volume: number;
  moodOverride: MoodOverride | null;
}

export function useAudioSync(
  mode: "demo" | "wav",
  playAudio: boolean,
  targetFps: number,
): AudioSyncResult {
  const [volume, setVolume] = useState(0);
  const [moodOverride, setMoodOverride] = useState<MoodOverride | null>(null);

  const demoEnvelopeRef = useRef<Float32Array | null>(null);
  const demoStartRef = useRef(0);
  const demoUntilRef = useRef(0);

  const wavEnvelopeRef = useRef<Float32Array | null>(null);
  const wavStartRef = useRef(0);
  const wavDurationRef = useRef(0);
  const wavActiveRef = useRef(false);
  const playedRef = useRef<Set<string>>(new Set());
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const sourceRef = useRef<AudioBufferSourceNode | null>(null);

  const startDemoSpeech = useCallback(() => {
    const durationS = 2.8;
    demoEnvelopeRef.current = buildDemoEnvelope(durationS, targetFps);
    demoStartRef.current = performance.now();
    demoUntilRef.current = demoStartRef.current + durationS * 1000 + 300;
  }, [targetFps]);

  const applyMood = useCallback((mood: SceneMood, durationS: number) => {
    setMoodOverride({ mood, until: performance.now() + durationS * 1000 });
  }, []);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (mode !== "demo") return;
      if (e.code === "Space" && performance.now() > demoUntilRef.current) {
        e.preventDefault();
        startDemoSpeech();
      } else if (e.key === "t" || e.key === "T") {
        applyMood("thinking", 5);
      } else if (e.key === "y" || e.key === "Y") {
        applyMood("surprised", 2.5);
      } else if (e.key === "g" || e.key === "G") {
        applyMood("creative_trace", 6);
      } else if (e.key === "1") {
        setMoodOverride(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mode, startDemoSpeech, applyMood]);

  const playWav = useCallback(
    async (filename: string) => {
      if (wavActiveRef.current) return;
      const url = `/api/wav/${encodeURIComponent(filename)}`;
      try {
        const { samples, sampleRate } = await decodeMonoSamples(url);
        wavEnvelopeRef.current = rmsEnvelope(samples, sampleRate, targetFps);
        wavDurationRef.current = (samples.length / sampleRate) * 1000;
        wavStartRef.current = performance.now();
        wavActiveRef.current = true;
        playedRef.current.add(filename);

        if (playAudio) {
          if (!audioCtxRef.current) {
            audioCtxRef.current = new AudioContext();
            analyserRef.current = audioCtxRef.current.createAnalyser();
            analyserRef.current.fftSize = 256;
            analyserRef.current.connect(audioCtxRef.current.destination);
          }
          const ctx = audioCtxRef.current;
          if (ctx.state === "suspended") await ctx.resume();

          sourceRef.current?.stop();
          const res = await fetch(url);
          const buf = await res.arrayBuffer();
          const audioBuffer = await ctx.decodeAudioData(buf.slice(0));
          const source = ctx.createBufferSource();
          source.buffer = audioBuffer;
          source.connect(analyserRef.current!);
          source.onended = () => {
            wavActiveRef.current = false;
            wavEnvelopeRef.current = null;
          };
          source.start(0);
          sourceRef.current = source;
        } else {
          window.setTimeout(() => {
            wavActiveRef.current = false;
            wavEnvelopeRef.current = null;
          }, wavDurationRef.current);
        }
      } catch {
        wavActiveRef.current = false;
        wavEnvelopeRef.current = null;
      }
    },
    [playAudio, targetFps],
  );

  useEffect(() => {
    if (mode !== "wav") return;

    let cancelled = false;

    const poll = async () => {
      try {
        const res = await fetch("/api/wav/list");
        if (!res.ok || cancelled) return;
        const files = (await res.json()) as string[];
        if (wavActiveRef.current) return;
        for (const name of files) {
          if (!playedRef.current.has(name)) {
            await playWav(name);
            break;
          }
        }
      } catch {
        /* ignore */
      }
    };

    poll();
    const id = window.setInterval(poll, 400);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [mode, playWav]);

  useEffect(() => {
    let raf = 0;
    const tick = () => {
      const now = performance.now();
      const t = now / 1000;

      if (demoEnvelopeRef.current && now <= demoUntilRef.current) {
        const frame = Math.floor(((now - demoStartRef.current) / 1000) * targetFps);
        if (frame >= 0 && frame < demoEnvelopeRef.current.length) {
          setVolume(demoEnvelopeRef.current[frame]);
          raf = requestAnimationFrame(tick);
          return;
        }
        demoEnvelopeRef.current = null;
      }

      if (wavActiveRef.current && wavEnvelopeRef.current) {
        let frame: number;
        if (playAudio && analyserRef.current && audioCtxRef.current) {
          const data = new Uint8Array(analyserRef.current.frequencyBinCount);
          analyserRef.current.getByteFrequencyData(data);
          let sum = 0;
          for (let i = 0; i < data.length; i++) sum += data[i];
          const analyserVol = sum / (data.length * 255);
          frame = Math.floor(((now - wavStartRef.current) / 1000) * targetFps);
          const env =
            frame >= 0 && frame < wavEnvelopeRef.current.length
              ? wavEnvelopeRef.current[frame]
              : 0;
          setVolume(Math.min(1, env * 0.6 + analyserVol * 0.8));
        } else {
          frame = Math.floor(((now - wavStartRef.current) / 1000) * targetFps);
          if (frame >= 0 && frame < wavEnvelopeRef.current.length) {
            setVolume(wavEnvelopeRef.current[frame]);
          } else if (now - wavStartRef.current >= wavDurationRef.current) {
            wavActiveRef.current = false;
            wavEnvelopeRef.current = null;
            setVolume(idleLevel(t));
          }
        }
        raf = requestAnimationFrame(tick);
        return;
      }

      setVolume(idleLevel(t));
      raf = requestAnimationFrame(tick);
    };

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playAudio, targetFps]);

  useEffect(() => {
    return () => {
      sourceRef.current?.stop();
      void audioCtxRef.current?.close();
    };
  }, []);

  return { volume, moodOverride };
}
