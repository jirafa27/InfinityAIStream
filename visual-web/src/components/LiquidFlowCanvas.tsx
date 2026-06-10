import { useEffect, useRef } from "react";
import { createLiquidRenderer } from "../lib/liquidRenderer";
import type { VisualState } from "../hooks/useVisualState";
import type { ComplexitySettings } from "../lib/complexity";

interface Props {
  visual: VisualState;
  complexity: ComplexitySettings;
}

export function LiquidFlowCanvas({ visual, complexity }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rendererRef = useRef<ReturnType<typeof createLiquidRenderer> | null>(null);
  const visualRef = useRef(visual);
  visualRef.current = visual;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    let renderer: ReturnType<typeof createLiquidRenderer>;
    try {
      renderer = createLiquidRenderer(canvas, complexity.blobCount);
    } catch (err) {
      console.error(err);
      return;
    }
    rendererRef.current = renderer;

    const resize = () => {
      const dpr = complexity.dpr;
      renderer.resize(window.innerWidth * dpr, window.innerHeight * dpr);
      canvas.style.width = `${window.innerWidth}px`;
      canvas.style.height = `${window.innerHeight}px`;
    };
    resize();
    window.addEventListener("resize", resize);

    let raf = 0;
    const draw = () => {
      const v = visualRef.current;
      renderer.draw({
        time: v.time,
        hue: v.hue,
        volume: v.volume,
        activity: v.activity,
        swirl: v.swirl,
      });
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      renderer.destroy();
      rendererRef.current = null;
    };
  }, [complexity.blobCount, complexity.dpr]);

  return (
    <canvas
      ref={canvasRef}
      style={{ display: "block", width: "100%", height: "100%", background: "#030818" }}
    />
  );
}
