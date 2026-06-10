export interface VisualConfig {
  mode: "demo" | "wav";
  complexity: "low" | "normal" | "high";
  volumeSmoothing: number;
  playAudio: boolean;
  targetFps: number;
}

const DEFAULT_CONFIG: VisualConfig = {
  mode: "demo",
  complexity: "low",
  volumeSmoothing: 0.18,
  playAudio: true,
  targetFps: 30,
};

export function modeFromQuery(): "demo" | "wav" | null {
  const params = new URLSearchParams(window.location.search);
  const mode = params.get("mode");
  if (mode === "demo" || mode === "wav") return mode;
  return null;
}

export async function fetchVisualConfig(): Promise<VisualConfig> {
  try {
    const res = await fetch("/api/config");
    if (!res.ok) return DEFAULT_CONFIG;
    const data = (await res.json()) as Partial<VisualConfig>;
    return {
      mode: data.mode === "wav" ? "wav" : "demo",
      complexity:
        data.complexity === "high" || data.complexity === "normal"
          ? data.complexity
          : "low",
      volumeSmoothing:
        typeof data.volumeSmoothing === "number" ? data.volumeSmoothing : 0.18,
      playAudio: data.playAudio !== false,
      targetFps: typeof data.targetFps === "number" ? data.targetFps : 30,
    };
  } catch {
    return DEFAULT_CONFIG;
  }
}
