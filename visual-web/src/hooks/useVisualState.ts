import { useEffect, useRef, useState } from "react";
import type { SceneMood } from "../lib/mood";
import { MOOD_PARAMS, activityFromMood, moodFromVolume } from "../lib/mood";

export interface VisualState {
  time: number;
  mood: SceneMood;
  volume: number;
  hue: number;
  activity: number;
  swirl: number;
}

export interface MoodOverride {
  mood: SceneMood;
  until: number;
}

export function useVisualState(
  rawVolume: number,
  moodOverride: MoodOverride | null,
  smoothing: number,
): VisualState {
  const [state, setState] = useState<VisualState>({
    time: 0,
    mood: "idle",
    volume: 0,
    hue: 0,
    activity: 1,
    swirl: 0,
  });

  const smoothedRef = useRef(0);
  const hueRef = useRef(0);
  const swirlRef = useRef(0);
  const timeRef = useRef(0);
  const rafRef = useRef(0);
  const lastTsRef = useRef<number | null>(null);
  const overrideRef = useRef(moodOverride);
  overrideRef.current = moodOverride;

  useEffect(() => {
    const tick = (ts: number) => {
      if (lastTsRef.current === null) lastTsRef.current = ts;
      const dt = Math.min(0.05, (ts - lastTsRef.current) / 1000);
      lastTsRef.current = ts;

      smoothedRef.current += (rawVolume - smoothedRef.current) * smoothing;

      const override =
        overrideRef.current && overrideRef.current.until > performance.now()
          ? overrideRef.current.mood
          : null;
      const mood = moodFromVolume(smoothedRef.current, override);
      const params = MOOD_PARAMS[mood];
      const vol = smoothedRef.current;

      timeRef.current += dt * params.timeScale * params.flowSpeed;

      const pulse =
        params.blobPulse * Math.sin(timeRef.current * 0.55)
        + params.wobble * 0.02 * Math.sin(timeRef.current * 1.15);

      hueRef.current =
        (hueRef.current
          + dt * params.hueSpeed
          + dt * params.swirl * 0.35
          + dt * vol * 0.05) % 1;

      swirlRef.current += dt * params.swirl * (2.0 + vol * 1.2);
      if (mood === "creative_trace") {
        swirlRef.current += dt * 0.35 * Math.sin(timeRef.current * 2.1);
      }

      const activity = activityFromMood(mood, vol, pulse);

      setState({
        time: timeRef.current,
        mood,
        volume: vol,
        hue: hueRef.current,
        activity,
        swirl: swirlRef.current,
      });

      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [rawVolume, smoothing]);

  return state;
}
