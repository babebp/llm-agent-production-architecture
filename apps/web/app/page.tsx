"use client";

import { useRef, useState } from "react";

type Msg = { role: "user" | "assistant"; text: string };

export default function Home() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const sessionId = useRef(
    typeof crypto !== "undefined" ? crypto.randomUUID() : "default"
  );

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text }]);
    setBusy(true);
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId.current }),
      });
      const data = await res.json();
      setMessages((m) => [
        ...m,
        { role: "assistant", text: data.reply ?? data.error ?? "error" },
      ]);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", text: `error: ${e}` }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={{ maxWidth: 720, margin: "0 auto", padding: 24, display: "flex", flexDirection: "column", minHeight: "100vh" }}>
      <h1 style={{ fontSize: 20 }}>Architecture Q&amp;A Agent</h1>
      <p style={{ color: "#8a93a5", fontSize: 14 }}>
        LangGraph agent → MCP (Qdrant RAG) → LiteLLM gateway → Claude. Ask about this repo&apos;s architecture.
      </p>
      <div style={{ flex: 1 }}>
        {messages.map((m, i) => (
          <div key={i} style={{ margin: "12px 0" }}>
            <b style={{ color: m.role === "user" ? "#7aa2f7" : "#9ece6a" }}>
              {m.role === "user" ? "you" : "agent"}
            </b>
            <div style={{ whiteSpace: "pre-wrap", marginTop: 4 }}>{m.text}</div>
          </div>
        ))}
        {busy && <div style={{ color: "#8a93a5" }}>thinking…</div>}
      </div>
      <div style={{ display: "flex", gap: 8, padding: "16px 0" }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Why LiteLLM instead of Kong?"
          style={{ flex: 1, padding: 10, borderRadius: 8, border: "1px solid #2a3040", background: "#131826", color: "inherit" }}
        />
        <button onClick={send} disabled={busy} style={{ padding: "10px 18px", borderRadius: 8, border: 0, background: "#7aa2f7", color: "#0b0f17", fontWeight: 600, cursor: "pointer" }}>
          Send
        </button>
      </div>
    </main>
  );
}
