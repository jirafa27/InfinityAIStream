import { useEffect, useRef } from "react";

interface Props {
  volume: number;
}

const SEGMENTS = 12;

function hsl(h: number, s: number, l: number, a = 1): string {
  return `hsla(${h % 360}, ${s}%, ${l}%, ${a})`;
}

function drawWedge(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  t: number,
  energy: number,
) {
  const maxR = Math.hypot(w, h) * 0.55;
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.arc(0, 0, maxR, -Math.PI / SEGMENTS, Math.PI / SEGMENTS);
  ctx.closePath();
  ctx.clip();

  const blobs = 7;
  for (let i = 0; i < blobs; i++) {
    const phase = t * (0.35 + i * 0.07) + i * 1.9;
    const bx = Math.cos(phase * 1.3) * maxR * (0.25 + 0.35 * Math.sin(t * 0.2 + i));
    const by = Math.sin(phase * 0.9 + i) * maxR * (0.2 + 0.4 * Math.cos(t * 0.17 + i * 0.5));
    const br = maxR * (0.18 + 0.12 * Math.sin(t * 0.5 + i * 2) + energy * 0.08);
    const hue = (t * 28 + i * 48 + energy * 40) % 360;

    const g = ctx.createRadialGradient(bx, by, 0, bx, by, br);
    g.addColorStop(0, hsl(hue, 92, 68, 0.95));
    g.addColorStop(0.45, hsl(hue + 35, 88, 52, 0.65));
    g.addColorStop(1, hsl(hue + 70, 80, 28, 0));

    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(bx, by, br, 0, Math.PI * 2);
    ctx.fill();
  }

  for (let i = 0; i < 5; i++) {
    const ringR = maxR * (0.15 + i * 0.14 + 0.04 * Math.sin(t * 0.8 + i));
    const hue = (t * 40 + i * 72) % 360;
    ctx.strokeStyle = hsl(hue, 100, 62, 0.22 + energy * 0.2);
    ctx.lineWidth = 2 + energy * 3;
    ctx.beginPath();
    ctx.arc(0, 0, ringR, -Math.PI / SEGMENTS, Math.PI / SEGMENTS);
    ctx.stroke();
  }

  const spark = maxR * 0.35;
  for (let i = 0; i < 8; i++) {
    const a = t * 0.6 + (i / 8) * (Math.PI / SEGMENTS) * 2;
    const sx = Math.cos(a) * spark;
    const sy = Math.sin(a) * spark;
    ctx.fillStyle = hsl((t * 50 + i * 40) % 360, 100, 78, 0.55);
    ctx.beginPath();
    ctx.arc(sx, sy, 3 + energy * 5, 0, Math.PI * 2);
    ctx.fill();
  }
}

export function KaleidoscopeCanvas({ volume }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const volumeRef = useRef(volume);
  volumeRef.current = volume;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    let start = performance.now();
    let smoothedEnergy = 0;

    const resize = () => {
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      canvas.width = window.innerWidth * dpr;
      canvas.height = window.innerHeight * dpr;
      canvas.style.width = `${window.innerWidth}px`;
      canvas.style.height = `${window.innerHeight}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener("resize", resize);

    const draw = (now: number) => {
      const w = window.innerWidth;
      const h = window.innerHeight;
      const t = (now - start) / 1000;

      smoothedEnergy += (volumeRef.current - smoothedEnergy) * 0.12;
      const energy = smoothedEnergy;

      const spin = t * (0.12 + energy * 0.35);
      const pulse = 1 + 0.04 * Math.sin(t * 1.7) + energy * 0.06;
      const cx = w / 2;
      const cy = h / 2;

      const bg = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.max(w, h) * 0.7);
      bg.addColorStop(0, hsl(t * 18 + 260, 55, 14 + energy * 8));
      bg.addColorStop(0.5, hsl(t * 14 + 220, 50, 8));
      bg.addColorStop(1, "#030108");
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, w, h);

      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(spin);
      ctx.scale(pulse, pulse);

      for (let i = 0; i < SEGMENTS; i++) {
        ctx.save();
        ctx.rotate((Math.PI * 2 * i) / SEGMENTS);
        if (i % 2 === 1) ctx.scale(1, -1);
        drawWedge(ctx, w, h, t + i * 0.15, energy);
        ctx.restore();
      }

      ctx.restore();

      const core = ctx.createRadialGradient(cx, cy, 0, cx, cy, 80 + energy * 60);
      core.addColorStop(0, hsl(t * 60, 100, 92, 0.35 + energy * 0.25));
      core.addColorStop(0.35, hsl(t * 60 + 40, 90, 60, 0.12));
      core.addColorStop(1, "transparent");
      ctx.fillStyle = core;
      ctx.fillRect(0, 0, w, h);

      raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
        display: "block",
      }}
    />
  );
}
