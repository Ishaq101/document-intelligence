export type DocumentStatus = "pending" | "processing" | "completed" | "failed";

export interface DocumentRecord {
  file_id: string;
  filename: string;
  file_size_bytes: number;
  user_id: string;
  status: DocumentStatus;
  page_count: number;
  category: string | null;
  upload_timestamp: string;
  processed_timestamp: string | null;
  error_message: string | null;
}

export interface Citation {
  filename: string;
  page: number;
  chunk_id: string;
  excerpt?: string | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  runtimeMs?: number;
}

export interface DashboardStats {
  knowledge: {
    total_files: number;
    files_pending: number;
    files_processing: number;
    files_completed: number;
    files_failed: number;
    total_chunks: number;
  };
  agent: {
    total_questions: number;
    fastest_runtime_ms: number | null;
    average_runtime_ms: number | null;
    longest_runtime_ms: number | null;
  };
}

export interface AdminConfig {
  chunk_size: number;
  chunk_overlap: number;
  retrieval_method: "bm25" | "vector" | "hybrid_rrf";
  top_k: number;
}

export interface Category {
  category_id: number;
  name: string;
  description: string;
}
