import { useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import type { VisualOverlayData } from "../hooks/useVisualOverlay";

interface Props {
  overlay: VisualOverlayData;
}

const MAX_FONT = 22;
const MIN_FONT = 11;

const HERO_TITLE =
  "ИИ-стример читает и комментирует цитаты известных людей";

const TOPIC_HINT =
  "Другой автор: !set_topic ИМЯ | случайные: !set_topic сброс";

function PagePortrait({ title, imageUrl }: { title: string; imageUrl: string }) {
  const [failed, setFailed] = useState(false);

  if (!imageUrl || failed) {
    return null;
  }

  return (
    <img
      src={imageUrl}
      alt={title}
      onError={() => setFailed(true)}
      style={{
        width: "clamp(300px, 37vw, 480px)",
        height: "clamp(300px, 37vw, 480px)",
        maxWidth: "100%",
        maxHeight: "100%",
        borderRadius: "50%",
        objectFit: "cover",
        flexShrink: 0,
        border: "4px solid rgba(255, 255, 255, 0.28)",
        boxShadow: "0 12px 32px rgba(0, 0, 0, 0.55)",
      }}
    />
  );
}

function AutoFitText({
  text,
  maxHeight,
  style,
}: {
  text: string;
  maxHeight: number;
  style?: CSSProperties;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const [fontSize, setFontSize] = useState(MAX_FONT);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;

    let size = MAX_FONT;
    el.style.fontSize = `${size}px`;
    while (size > MIN_FONT && el.scrollHeight > maxHeight) {
      size -= 1;
      el.style.fontSize = `${size}px`;
    }
    setFontSize(size);
  }, [text, maxHeight]);

  return (
    <span
      ref={ref}
      style={{
        fontSize,
        lineHeight: 1.35,
        wordBreak: "break-word",
        ...style,
      }}
    >
      {text}
    </span>
  );
}

export function VisualOverlay({ overlay }: Props) {
  const { topic, imageUrl, quote, chat } = overlay;
  const showChat = chat !== null && (chat.author.length > 0 || chat.content.length > 0);
  const showPerson = !showChat && topic.length > 0;
  const showQuote = showPerson && quote.length > 0;
  const showPortrait = showPerson && imageUrl.length > 0;

  return (
    <>
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: 0,
          zIndex: 2,
          padding: "28px 40px 32px",
          pointerEvents: "none",
          fontFamily: '"Segoe UI", system-ui, sans-serif',
          color: "#f5f7ff",
          textAlign: "center",
          textShadow: "0 2px 16px rgba(0, 0, 0, 0.9)",
          background:
            "linear-gradient(to bottom, rgba(3, 8, 24, 0.88) 0%, rgba(3, 8, 24, 0.55) 80%, transparent 100%)",
          boxSizing: "border-box",
        }}
      >
        <div
          style={{
            fontSize: "clamp(30px, 4.8vw, 56px)",
            fontWeight: 700,
            lineHeight: 1.2,
            letterSpacing: "-0.02em",
            maxWidth: 1100,
            margin: "0 auto",
          }}
        >
          {HERO_TITLE}
        </div>
        <div
          style={{
            marginTop: 20,
            fontSize: "clamp(24px, 3.4vw, 36px)",
            fontWeight: 600,
            lineHeight: 1.35,
            opacity: 0.92,
            maxWidth: 1000,
            marginLeft: "auto",
            marginRight: "auto",
          }}
        >
          {TOPIC_HINT}
        </div>
      </div>

      {showPortrait && (
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            top: "max(270px, 31%)",
            bottom: "27%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            pointerEvents: "none",
            zIndex: 1,
          }}
        >
          <PagePortrait title={topic} imageUrl={imageUrl} />
        </div>
      )}

      {(showPerson || showChat) && (
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            bottom: 0,
            zIndex: 2,
            padding: "24px 32px 36px",
            pointerEvents: "none",
            fontFamily: '"Segoe UI", system-ui, sans-serif',
            color: "#f0f4ff",
            textShadow: "0 1px 8px rgba(0, 0, 0, 0.85)",
            background:
              "linear-gradient(to top, rgba(3, 8, 24, 0.88) 0%, rgba(3, 8, 24, 0.5) 75%, transparent 100%)",
            boxSizing: "border-box",
          }}
        >
          {showPerson && (
            <div
              style={{
                fontSize: "clamp(26px, 3.2vw, 38px)",
                fontWeight: 600,
                lineHeight: 1.3,
                textAlign: "center",
              }}
            >
              <span style={{ opacity: 0.8, fontWeight: 700 }}>Автор: </span>
              {topic}
            </div>
          )}

          {showQuote && (
            <div
              style={{
                marginTop: 12,
                maxHeight: 120,
                overflow: "hidden",
                textAlign: "center",
              }}
            >
              <AutoFitText text={`«${quote}»`} maxHeight={88} />
            </div>
          )}

          {showChat && chat && (
            <div style={{ maxHeight: 120, overflow: "hidden" }}>
              <div style={{ fontSize: 17, fontWeight: 600, marginBottom: 6, opacity: 0.9 }}>
                Ответ на комментарий {chat.author}:
              </div>
              <AutoFitText text={chat.content} maxHeight={88} />
            </div>
          )}
        </div>
      )}
    </>
  );
}
