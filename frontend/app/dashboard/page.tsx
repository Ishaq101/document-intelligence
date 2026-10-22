"use client";

import { useEffect, useState } from "react";
import { ProtectedPage } from "@/components/AppShell";
import { StatsCard } from "@/components/StatsCard";
import { api } from "@/lib/api";
import type { DashboardStats } from "@/types";

export default function DashboardPage() { const [stats, setStats] = useState<DashboardStats>(); const [error, setError] = useState(""); useEffect(() => { api.getStats().then(setStats).catch((value: Error) => setError(value.message)); }, []); const knowledge = stats?.knowledge; const agent = stats?.agent; return <ProtectedPage><h1 className="text-2xl font-bold">Dashboard</h1><p className="mt-1 text-slate-500">Knowledge base and assistant activity overview.</p>{error && <p className="mt-6 text-red-600">{error}</p>}<h2 className="mt-8 font-semibold">Knowledge base</h2><div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3"><StatsCard label="Total documents" value={knowledge?.total_files ?? "—"}/><StatsCard label="Processed" value={knowledge?.files_completed ?? "—"}/><StatsCard label="Total chunks" value={knowledge?.total_chunks ?? "—"}/></div><h2 className="mt-8 font-semibold">Assistant</h2><div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-4"><StatsCard label="Questions" value={agent?.total_questions ?? "—"}/><StatsCard label="Fastest" value={agent?.fastest_runtime_ms ? `${agent.fastest_runtime_ms} ms` : "—"}/><StatsCard label="Average" value={agent?.average_runtime_ms ? `${Math.round(agent.average_runtime_ms)} ms` : "—"}/><StatsCard label="Longest" value={agent?.longest_runtime_ms ? `${agent.longest_runtime_ms} ms` : "—"}/></div></ProtectedPage>; }
