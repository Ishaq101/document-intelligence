import type { ChatMessage as Message } from "@/types";

export function ChatMessage({ message }: { message: Message }) {
  return <article className={`w-fit max-w-[min(42rem,88%)] rounded-xl px-4 py-3 ${message.role === "user" ? "ml-auto bg-kirana-teal text-white" : "bg-white ring-1 ring-slate-100"}`}><p className="whitespace-pre-wrap break-words leading-7">{message.content}</p>{message.citations?.map((citation) => <p key={citation.chunk_id} className="mt-3 text-xs text-kirana-teal">Source: {citation.filename}, page {citation.page}</p>)}{message.runtimeMs !== undefined && <p className="mt-2 text-xs text-slate-400">{message.runtimeMs} ms</p>}</article>;
}
