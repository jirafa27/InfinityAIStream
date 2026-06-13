import { useEffect, useState } from "react";

export interface ChatOverlay {
  author: string;
  content: string;
}

export interface VisualOverlayData {
  topic: string;
  imageUrl: string;
  quote: string;
  chat: ChatOverlay | null;
}

const EMPTY: VisualOverlayData = { topic: "", imageUrl: "", quote: "", chat: null };

export function useVisualOverlay(pollMs = 800): VisualOverlayData {
  const [data, setData] = useState<VisualOverlayData>(EMPTY);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const res = await fetch("/api/overlay");
        if (!res.ok || cancelled) return;
        const raw = (await res.json()) as Partial<VisualOverlayData>;
        const topic = typeof raw.topic === "string" ? raw.topic.trim() : "";
        const imageUrl =
          typeof raw.imageUrl === "string" ? raw.imageUrl.trim() : "";
        const quote = typeof raw.quote === "string" ? raw.quote.trim() : "";
        let chat: ChatOverlay | null = null;
        if (
          raw.chat &&
          typeof raw.chat === "object" &&
          typeof raw.chat.author === "string" &&
          typeof raw.chat.content === "string"
        ) {
          const author = raw.chat.author.trim();
          const content = raw.chat.content.trim();
          if (author || content) {
            chat = { author, content };
          }
        }
        setData({ topic, imageUrl, quote, chat });
      } catch {
        /* ignore */
      }
    };

    poll();
    const id = window.setInterval(poll, pollMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [pollMs]);

  return data;
}
