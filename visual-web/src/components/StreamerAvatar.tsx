import { useEffect, useRef, useState } from "react";

interface Props {
  volume: number;
}

function clamp01(v: number): number {
  return Math.min(1, Math.max(0, v));
}

export function StreamerAvatar({ volume }: Props) {
  const smoothedRef = useRef(0);
  const [mouth, setMouth] = useState(0);
  const [blink, setBlink] = useState(false);

  useEffect(() => {
    let raf = 0;
    const tick = () => {
      smoothedRef.current += (volume - smoothedRef.current) * 0.28;
      setMouth(smoothedRef.current);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [volume]);

  useEffect(() => {
    let timeoutId = 0;
    const scheduleBlink = () => {
      const delay = 2800 + Math.random() * 3200;
      timeoutId = window.setTimeout(() => {
        setBlink(true);
        window.setTimeout(() => {
          setBlink(false);
          scheduleBlink();
        }, 120);
      }, delay);
    };
    scheduleBlink();
    return () => clearTimeout(timeoutId);
  }, []);

  const open = clamp01(mouth * 2.8);
  const mouthH = 3 + open * 26;
  const mouthW = 14 + open * 10;
  const jawY = open * 5;
  const glow = 0.35 + open * 0.45;

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        overflow: "hidden",
        background:
          "radial-gradient(ellipse 90% 70% at 50% 38%, #2a1848 0%, #0c0618 55%, #030208 100%)",
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "radial-gradient(circle at 50% 22%, rgba(255, 120, 200, 0.14) 0%, transparent 48%)",
          pointerEvents: "none",
        }}
      />

      <svg
        viewBox="0 0 480 720"
        preserveAspectRatio="xMidYMid slice"
        style={{
          width: "100%",
          height: "100%",
          display: "block",
        }}
        aria-hidden
      >
        <defs>
          <linearGradient id="hairGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#ff9ec8" />
            <stop offset="45%" stopColor="#e85aa0" />
            <stop offset="100%" stopColor="#8b2d6e" />
          </linearGradient>
          <linearGradient id="skinGrad" x1="30%" y1="0%" x2="70%" y2="100%">
            <stop offset="0%" stopColor="#ffe8dc" />
            <stop offset="100%" stopColor="#f5c4b0" />
          </linearGradient>
          <linearGradient id="lipGrad" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#f06a8a" />
            <stop offset="100%" stopColor="#c93d62" />
          </linearGradient>
          <radialGradient id="eyeGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#9ee7ff" />
            <stop offset="100%" stopColor="#3a8fb8" />
          </radialGradient>
          <filter id="softGlow" x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="8" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* плечи / одежда */}
        <ellipse cx="240" cy="640" rx="210" ry="120" fill="#1a1030" />
        <path
          d="M 70 520 Q 120 420 240 400 Q 360 420 410 520 L 410 720 L 70 720 Z"
          fill="url(#hairGrad)"
          opacity="0.35"
        />
        <path
          d="M 95 530 Q 150 460 240 445 Q 330 460 385 530 L 385 720 L 95 720 Z"
          fill="#2d1a42"
        />
        <ellipse cx="240" cy="555" rx="95" ry="28" fill="#3d2558" />

        {/* волосы за головой */}
        <ellipse cx="240" cy="250" rx="155" ry="175" fill="url(#hairGrad)" />
        <path
          d="M 95 260 C 60 360 75 480 120 560 C 160 500 150 350 130 240 Z"
          fill="#c94d88"
        />
        <path
          d="M 385 260 C 420 360 405 480 360 560 C 320 500 330 350 350 240 Z"
          fill="#c94d88"
        />

        {/* шея */}
        <rect x="205" y="360" width="70" height="90" rx="22" fill="#f0c0ad" />

        {/* лицо */}
        <ellipse cx="240" cy="300" rx="118" ry="132" fill="url(#skinGrad)" />

        {/* чёлка */}
        <path
          d="M 125 210 C 160 120 320 120 355 210 C 330 250 300 270 240 265 C 180 270 150 250 125 210 Z"
          fill="url(#hairGrad)"
        />
        <path
          d="M 155 195 C 190 155 290 155 325 195 C 300 225 270 240 240 238 C 210 240 180 225 155 195 Z"
          fill="#ff8fbe"
          opacity="0.55"
        />

        {/* уши (лёгкий намёк) */}
        <ellipse cx="118" cy="310" rx="14" ry="22" fill="#eec0ad" />
        <ellipse cx="362" cy="310" rx="14" ry="22" fill="#eec0ad" />

        {/* румянец */}
        <ellipse cx="175" cy="335" rx="28" ry="16" fill="#ff8aa8" opacity={0.22 + open * 0.08} />
        <ellipse cx="305" cy="335" rx="28" ry="16" fill="#ff8aa8" opacity={0.22 + open * 0.08} />

        {/* глаза */}
        <g transform="translate(0, 0)">
          <ellipse cx="188" cy="285" rx="34" ry={blink ? 3 : 26} fill="#fff" />
          <ellipse cx="292" cy="285" rx="34" ry={blink ? 3 : 26} fill="#fff" />
          {!blink && (
            <>
              <circle cx="196" cy="288" r="16" fill="url(#eyeGlow)" />
              <circle cx="300" cy="288" r="16" fill="url(#eyeGlow)" />
              <circle cx="202" cy="282" r="7" fill="#1a2040" />
              <circle cx="306" cy="282" r="7" fill="#1a2040" />
              <circle cx="205" cy="279" r="3" fill="#fff" opacity="0.9" />
              <circle cx="309" cy="279" r="3" fill="#fff" opacity="0.9" />
            </>
          )}
          <path
            d="M 154 255 Q 188 238 222 255"
            fill="none"
            stroke="#5a2848"
            strokeWidth="5"
            strokeLinecap="round"
          />
          <path
            d="M 258 255 Q 292 238 326 255"
            fill="none"
            stroke="#5a2848"
            strokeWidth="5"
            strokeLinecap="round"
          />
        </g>

        {/* нос */}
        <path
          d="M 240 300 Q 248 330 240 342 Q 232 330 240 300"
          fill="none"
          stroke="#d9a090"
          strokeWidth="3"
          strokeLinecap="round"
          opacity="0.7"
        />

        {/* рот — lip-sync */}
        <g transform={`translate(240 ${368 + jawY})`} filter="url(#softGlow)" opacity={glow}>
          <ellipse
            cx="0"
            cy="0"
            rx={mouthW}
            ry={mouthH}
            fill="#2a1020"
            opacity={0.85}
          />
          <ellipse cx="0" cy={-mouthH * 0.15} rx={mouthW * 0.92} ry={mouthH * 0.55} fill="url(#lipGrad)" />
          {open > 0.12 && (
            <ellipse
              cx="0"
              cy={mouthH * 0.25}
              rx={mouthW * 0.55}
              ry={mouthH * 0.35}
              fill="#ffb8c8"
              opacity={0.5}
            />
          )}
          {open > 0.35 && (
            <ellipse cx="0" cy={mouthH * 0.1} rx={mouthW * 0.35} ry={mouthH * 0.2} fill="#fff" opacity="0.12" />
          )}
        </g>

        {/* блики на волосах */}
        <path
          d="M 170 180 Q 210 150 250 175"
          fill="none"
          stroke="#ffd0e8"
          strokeWidth="6"
          strokeLinecap="round"
          opacity="0.35"
        />
      </svg>

      <div
        style={{
          position: "absolute",
          left: "50%",
          bottom: "18%",
          transform: "translateX(-50%)",
          width: "min(420px, 55vw)",
          height: 8,
          borderRadius: 999,
          background: `linear-gradient(90deg, transparent, rgba(255, 140, 200, ${0.15 + open * 0.5}), transparent)`,
          filter: "blur(2px)",
          pointerEvents: "none",
        }}
      />
    </div>
  );
}
