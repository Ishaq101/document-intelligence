"use client";

import { useRef, useState } from "react";
import { Upload } from "lucide-react";

export function UploadZone({ disabled, onUpload }: { disabled?: boolean; onUpload: (file: File) => Promise<void> }) {
  const input = useRef<HTMLInputElement>(null); const [dragging, setDragging] = useState(false); const [error, setError] = useState("");
  const pick = async (file?: File) => {
    if (!file) return;
    if (file.type !== "application/pdf" || file.size > 50_000_000) { setError("Choose a PDF smaller than 50 MB."); return; }
    setError(""); await onUpload(file);
  };
  return <div onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); void pick(event.dataTransfer.files[0]); }} className={`rounded-xl border-2 border-dashed p-8 text-center ${dragging ? "border-kirana-teal bg-kirana-mist" : "border-teal-100 bg-white"}`}>
    <Upload className="mx-auto mb-3 text-kirana-teal"/><p className="font-medium">Drop a PDF here</p><p className="mt-1 text-sm text-slate-500">or select a file, maximum 50 MB</p>
    <button disabled={disabled} onClick={() => input.current?.click()} className="mt-4 rounded-lg bg-kirana-teal px-4 py-2 text-sm font-medium text-white disabled:opacity-50">Choose PDF</button>
    <input ref={input} className="hidden" type="file" accept="application/pdf" onChange={(event) => void pick(event.target.files?.[0])}/>{error && <p className="mt-3 text-sm text-red-600">{error}</p>}
  </div>;
}
