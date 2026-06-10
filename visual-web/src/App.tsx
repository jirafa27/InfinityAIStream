import { useEffect, useMemo, useState } from "react";
import { LiquidFlowCanvas } from "./components/LiquidFlowCanvas";
import { VisualOverlay } from "./components/VisualOverlay";
import { useAudioSync } from "./hooks/useAudioSync";
import { useVisualOverlay } from "./hooks/useVisualOverlay";
import { useVisualState } from "./hooks/useVisualState";
import { fetchVisualConfig, modeFromQuery } from "./lib/config";
import { getComplexitySettings, parseComplexity } from "./lib/complexity";

export default function App() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [config, setConfig] = useState<Awaited<ReturnType<typeof fetchVisualConfig>> | null>(
    null,
  );

  useEffect(() => {
    fetchVisualConfig()
      .then((cfg) => {
        const queryMode = modeFromQuery();
        if (queryMode) cfg.mode = queryMode;
        setConfig(cfg);
        setReady(true);
      })
      .catch(() => {
        setError("Не удалось загрузить конфигурацию");
      });
  }, []);

  const mode = config?.mode ?? "demo";
  const playAudio = config?.playAudio ?? true;
  const targetFps = config?.targetFps ?? 30;
  const smoothing = config?.volumeSmoothing ?? 0.18;
  const complexity = useMemo(
    () => getComplexitySettings(parseComplexity(config?.complexity)),
    [config?.complexity],
  );

  const { volume, moodOverride } = useAudioSync(mode, playAudio, targetFps);
  const visual = useVisualState(volume, moodOverride, smoothing);
  const overlay = useVisualOverlay();

  if (error) {
    return (
      <div style={{ color: "#ccc", padding: 24, fontFamily: "sans-serif" }}>{error}</div>
    );
  }

  if (!ready) {
    return null;
  }

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <LiquidFlowCanvas visual={visual} complexity={complexity} />
      <VisualOverlay overlay={overlay} />
    </div>
  );
}
