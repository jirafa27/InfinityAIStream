export type SceneMood = "idle" | "speaking" | "thinking" | "surprised" | "creative_trace";

export interface MoodParams {
  timeScale: number;
  flowSpeed: number;
  blobPulse: number;
  wobble: number;
  hueSpeed: number;
  swirl: number;
}

const BASE: MoodParams = {
  timeScale: 0.42,
  flowSpeed: 0.38,
  blobPulse: 0.09,
  wobble: 1.1,
  hueSpeed: 0.035,
  swirl: 0.045,
};

export const MOOD_PARAMS: Record<SceneMood, MoodParams> = {
  idle: { ...BASE },
  speaking: {
    ...BASE,
    timeScale: 0.52,
    flowSpeed: 0.48,
    blobPulse: 0.11,
    hueSpeed: 0.045,
    swirl: 0.055,
  },
  thinking: {
    ...BASE,
    timeScale: 0.32,
    flowSpeed: 0.28,
    blobPulse: 0.06,
    wobble: 0.95,
    hueSpeed: 0.025,
    swirl: 0.03,
  },
  surprised: {
    ...BASE,
    timeScale: 0.58,
    flowSpeed: 0.55,
    blobPulse: 0.14,
    wobble: 1.2,
    hueSpeed: 0.055,
    swirl: 0.07,
  },
  creative_trace: {
    ...BASE,
    timeScale: 0.55,
    flowSpeed: 0.52,
    wobble: 1.25,
    hueSpeed: 0.05,
    swirl: 0.065,
  },
};

export function moodFromVolume(volume: number, override: SceneMood | null): SceneMood {
  if (override) return override;
  return volume > 0.1 ? "speaking" : "idle";
}

export function activityFromMood(mood: SceneMood, volume: number, pulse: number): number {
  const base: Record<SceneMood, number> = {
    idle: 0.55,
    speaking: 0.65,
    thinking: 0.45,
    surprised: 0.75,
    creative_trace: 0.7,
  };
  const breath = 1 + pulse * 0.08;
  return (base[mood] + volume * 0.35) * breath;
}
