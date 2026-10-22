import type { AdminConfig, Category, DashboardStats, DocumentRecord } from "@/types";

const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8010";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: { ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? "Permintaan gagal.");
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export const api = {
  listDocuments: () => request<{ documents: DocumentRecord[]; total: number }>("/documents"),
  listCategories: () => request<Category[]>("/admin/categories"),
  createCategory: (name: string, description: string) => request<Category>("/admin/categories", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, description }),
  }),
  uploadDocument: (file: File, category: string) => {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentRecord>(`/documents/upload?category=${encodeURIComponent(category)}`, { method: "POST", body: form });
  },
  processDocument: (id: string) => request<DocumentRecord>(`/documents/${id}/process`, { method: "POST" }),
  deleteDocument: (id: string) => request<void>(`/documents/${id}`, { method: "DELETE" }),
  getStats: () => request<DashboardStats>("/dashboard/stats"),
  getConfig: () => request<AdminConfig>("/admin/config"),
  updateConfig: (config: AdminConfig) => request<AdminConfig>("/admin/config", {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(config),
  }),
};

export { baseUrl };
