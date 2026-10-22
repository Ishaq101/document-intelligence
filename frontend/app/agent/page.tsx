"use client";

import { FormEvent, useState } from "react";
import { Send } from "lucide-react";
import { ProtectedPage } from "@/components/AppShell";
import { ChatMessage } from "@/components/ChatMessage";
import { baseUrl } from "@/lib/api";
import type { ChatMessage as Message } from "@/types";

export default function AgentPage() {
  const [messages, setMessages] = useState<Message[]>([]); const [question, setQuestion] = useState(""); const [sessionId, setSessionId] = useState<string>(); const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => { event.preventDefault(); const text = question.trim(); if (!text || busy) return; setQuestion(""); setMessages((items) => [...items, { id: crypto.randomUUID(), role: "user", content: text }, { id: "stream", role: "assistant", content: "" }]); setBusy(true);
    try { const response = await fetch(`${baseUrl}/chat/stream`, { method: "POST", headers: { "Content-Type": "application/json", "X-Request-Id": crypto.randomUUID() }, body: JSON.stringify({ question: text, session_id: sessionId }) }); if (!response.ok || !response.body) throw new Error("Unable to start chat."); const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = "";
      while (true) { const { done, value } = await reader.read(); if (done) break; buffer += decoder.decode(value, { stream: true }); const events = buffer.split("\n\n"); buffer = events.pop() ?? ""; for (const eventText of events) { const data = eventText.split("\n").find((line) => line.startsWith("data: "))?.slice(6); if (!data) continue; const dataEvent = JSON.parse(data) as { type: string; content?: string; session_id?: string; runtime_ms?: number; message?: string }; if (dataEvent.type === "session") setSessionId(dataEvent.session_id); if (dataEvent.type === "token") setMessages((items) => items.map((item) => item.id === "stream" ? { ...item, content: item.content + dataEvent.content } : item)); if (dataEvent.type === "done") setMessages((items) => items.map((item) => item.id === "stream" ? { ...item, runtimeMs: dataEvent.runtime_ms } : item)); if (dataEvent.type === "error") throw new Error(dataEvent.message); } }
    } catch (error) { setMessages((items) => items.map((item) => item.id === "stream" ? { ...item, content: error instanceof Error ? error.message : "Chat failed." } : item)); } finally { setBusy(false); }
  };
  return <ProtectedPage><div className="flex min-h-[calc(100vh-5rem)] flex-col"><header><h1 className="text-2xl font-bold">Document Assistant</h1><p className="mt-1 text-slate-500">Ask questions about processed documents.</p></header><div className="mt-8 flex-1 space-y-4 pb-28">{messages.length ? messages.map((message) => <ChatMessage key={message.id} message={message}/>) : <p className="rounded-xl bg-white p-8 text-center text-slate-500">Start with a question about your documents.</p>}</div><form onSubmit={submit} className="sticky bottom-0 flex gap-2 border-t border-slate-200 bg-[#f2f6f5] py-4"><input value={question} maxLength={4000} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask a question..." className="min-w-0 flex-1 rounded-lg bg-white px-4 py-3 shadow-sm ring-1 ring-slate-200 outline-none focus:ring-2 focus:ring-kirana-teal"/><button disabled={busy} className="rounded-lg bg-kirana-teal p-3 text-white disabled:opacity-50"><Send size={20}/></button></form></div></ProtectedPage>;
}
