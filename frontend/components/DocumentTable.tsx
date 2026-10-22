"use client";

import type { DocumentRecord } from "@/types";

const statusStyle = { pending: "bg-amber-100 text-amber-800", processing: "bg-sky-100 text-sky-800", completed: "bg-emerald-100 text-emerald-800", failed: "bg-red-100 text-red-800" };
export function DocumentTable({ documents, busyId, onProcess, onDelete }: { documents: DocumentRecord[]; busyId?: string; onProcess: (id: string) => void; onDelete: (id: string) => void }) {
  if (!documents.length) return <p className="rounded-xl bg-white p-8 text-center text-slate-500">No documents yet.</p>;
  return <div className="overflow-x-auto rounded-xl border border-slate-100 bg-white"><table className="w-full text-left text-sm"><thead className="border-b bg-slate-50 text-slate-500"><tr><th className="p-4">Document</th><th className="p-4">Category</th><th className="p-4">Status</th><th className="p-4">Pages</th><th className="p-4"/></tr></thead><tbody>{documents.map((doc) => <tr key={doc.file_id} className="border-b last:border-0"><td className="p-4 font-medium">{doc.filename}{doc.error_message && <p className="mt-1 text-xs text-red-600">{doc.error_message}</p>}</td><td className="p-4">{doc.category ?? "—"}</td><td className="p-4"><span className={`rounded-full px-2 py-1 text-xs ${statusStyle[doc.status]}`}>{doc.status}</span></td><td className="p-4">{doc.page_count}</td><td className="p-4 text-right">{doc.status === "pending" && <button disabled={busyId === doc.file_id} onClick={() => onProcess(doc.file_id)} className="mr-3 text-kirana-teal disabled:opacity-50">Process</button>}<button disabled={busyId === doc.file_id} onClick={() => onDelete(doc.file_id)} className="text-red-600 disabled:opacity-50">Delete</button></td></tr>)}</tbody></table></div>;
}
