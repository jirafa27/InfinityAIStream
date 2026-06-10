export type ComplexityProfile = "low" | "normal" | "high";

export interface ComplexitySettings {
  blobCount: number;
  dpr: number;
}

const PROFILES: Record<ComplexityProfile, ComplexitySettings> = {
  low: { blobCount: 22, dpr: 1 },
  normal: { blobCount: 28, dpr: 1 },
  high: {
    blobCount: 32,
    dpr: Math.min(typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1, 2),
  },
};

export function parseComplexity(value: string | undefined): ComplexityProfile {
  if (value === "normal" || value === "high") return value;
  return "low";
}

export function getComplexitySettings(profile: ComplexityProfile): ComplexitySettings {
  return PROFILES[profile];
}
