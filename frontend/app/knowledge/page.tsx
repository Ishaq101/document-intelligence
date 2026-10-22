"use client";

import { useEffect, useState } from "react";
import { ProtectedPage } from "@/components/AppShell";
import { DocumentTable } from "@/components/DocumentTable";
import { UploadZone } from "@/components/UploadZone";
import { api } from "@/lib/api";
import type { Category, DocumentRecord } from "@/types";

export default function KnowledgePage() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]); const [categories, setCategories] = useState<Category[]>([]); const [category, setCategory] = useState(""); const [busyId, setBusyId] = useState<string>(); const [message, setMessage] = useState("");
  const load = async () => { try { const [docs, cats] = await Promise.all([api.listDocuments(), api.listCategories()]); setDocuments(docs.documents); setCategories(cats); setCategory((current) => current || cats[0]?.name || ""); } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to load data."); } };
  useEffect(() => { void load(); }, []);
  const upload = async (file: File) => { if (!category) { setMessage("Create a category first."); return; } setBusyId("upload"); try { await api.uploadDocument(file, category); setMessage("Document uploaded."); await load(); } catch (error) { setMessage(error instanceof Error ? error.message : "Upload failed."); } finally { setBusyId(undefined); } };
  const createCategory = async () => { const name = prompt("Category name:")?.trim(); if (!name) return; const description = prompt("Describe which documents and questions belong to this category:")?.trim(); if (!description) { setMessage("Category description is required."); return; } try { const added = await api.createCategory(name, description); setCategories((items) => [...items, added]); setCategory(added.name); } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to create category."); } };
  const process = async (id: string) => { setBusyId(id); try { await api.processDocument(id); setMessage("Document processed."); await load(); } catch (error) { setMessage(error instanceof Error ? error.message : "Processing failed."); } finally { setBusyId(undefined); } };
  const remove = async (id: string) => { if (!confirm("Delete this document?")) return; setBusyId(id); try { await api.deleteDocument(id); setDocuments((items) => items.filter((item) => item.file_id !== id)); } catch (error) { setMessage(error instanceof Error ? error.message : "Delete failed."); } finally { setBusyId(undefined); } };
  return <ProtectedPage><h1 className="text-2xl font-bold">Knowledge</h1><p className="mt-1 text-slate-500">Upload and process PDFs for your assistant.</p><section className="mt-8 grid gap-5 lg:grid-cols-[1fr_1.5fr]"><div><div className="mb-3 flex gap-2"><select value={category} onChange={(event) => setCategory(event.target.value)} className="min-w-0 flex-1 rounded-lg border border-slate-200 px-3 py-2"><option value="">Select category</option>{categories.map((item) => <option key={item.category_id}>{item.name}</option>)}</select><button onClick={() => void createCategory()} className="rounded-lg border border-kirana-teal px-3 text-kirana-teal">Add</button></div><UploadZone disabled={busyId === "upload"} onUpload={upload}/>{message && <p className="mt-3 text-sm text-slate-600">{message}</p>}</div><div><h2 className="mb-3 font-semibold">Documents ({documents.length})</h2><DocumentTable documents={documents} busyId={busyId} onProcess={(id) => void process(id)} onDelete={(id) => void remove(id)}/></div></section></ProtectedPage>;
}
