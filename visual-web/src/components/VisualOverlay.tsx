import { useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import type { VisualOverlayData } from "../hooks/useVisualOverlay";

interface Props {
  overlay: VisualOverlayData;
}

const MAX_FONT = 22;
const MIN_FONT = 11;

const HERO_TITLE =
  "ИИ-философ-стендапер рассуждает на разные темы и реагирует на чат";

const TOPIC_HINT =
  "Задай тему стендапа в комментариях с помощью команды !set_topic";

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
  const { topic, chat } = overlay;
  const showChat = chat !== null && (chat.author.length > 0 || chat.content.length > 0);
  const showTopic = !showChat && topic.length > 0;

  return (
    <>
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: 0,
          padding: "28px 40px 48px",
          pointerEvents: "none",
          fontFamily: '"Segoe UI", system-ui, sans-serif',
          color: "#f5f7ff",
          textAlign: "center",
          textShadow: "0 2px 16px rgba(0, 0, 0, 0.9)",
          background:
            "linear-gradient(to bottom, rgba(3, 8, 24, 0.78) 0%, rgba(3, 8, 24, 0.35) 65%, transparent 100%)",
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

      {(showTopic || showChat) && (
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            bottom: 0,
            padding: "24px 32px 36px",
            pointerEvents: "none",
            fontFamily: '"Segoe UI", system-ui, sans-serif',
            color: "#f0f4ff",
            textShadow: "0 1px 8px rgba(0, 0, 0, 0.85)",
            background:
              "linear-gradient(to top, rgba(3, 8, 24, 0.82) 0%, rgba(3, 8, 24, 0.45) 70%, transparent 100%)",
            boxSizing: "border-box",
          }}
        >
          {showTopic && (
            <div
              style={{
                fontSize: "clamp(26px, 3.2vw, 38px)",
                fontWeight: 600,
                lineHeight: 1.3,
              }}
            >
              <span style={{ opacity: 0.8, fontWeight: 700 }}>Тема: </span>
              {topic}
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
