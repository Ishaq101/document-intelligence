import type { ChatMessage as Message } from "@/types";

const excerptStyle = { borderLeft: "2px solid #0b5f5a", paddingLeft: "0.625rem", color: "#475569" } as const;

export function ChatMessage({ message, streaming }: { message: Message; streaming?: boolean }) {
  const citations = message.citations ?? [];
  return (
    <article className={`w-fit max-w-[min(42rem,88%)] rounded-xl px-4 py-3 ${message.role === "user" ? "ml-auto bg-kirana-teal text-white" : "bg-white ring-1 ring-slate-100"}`}>
      <p className="whitespace-pre-wrap break-words leading-7">
        {message.content}
        {streaming && <span className="ml-1 inline-block h-4 w-1.5 animate-pulse bg-kirana-teal align-middle" />}
      </p>
      {streaming && !message.content && <span className="text-sm text-slate-400">Generating answer…</span>}
      {citations.length > 0 && (
        <details className="mt-3 border-t border-slate-100 pt-2">
          <summary className="cursor-pointer text-[11px] font-semibold uppercase tracking-wide text-slate-400 hover:text-kirana-teal">
            References ({citations.length})
          </summary>
          <ol className="mt-2 space-y-1.5">
            {citations.map((citation, index) => (
              <li key={citation.chunk_id} className="text-xs text-kirana-teal">
                <span className="font-mono">[{index + 1}]</span> {citation.filename}, p. {citation.page}
                {citation.excerpt && <blockquote className="mt-1 text-[11px] italic" style={excerptStyle}>{citation.excerpt}</blockquote>}
              </li>
            ))}
          </ol>
        </details>
      )}
      {message.runtimeMs !== undefined && <p className="mt-2 text-xs text-slate-400">{message.runtimeMs} ms</p>}
    </article>
  );
}
