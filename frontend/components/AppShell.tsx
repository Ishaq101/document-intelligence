"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { BookOpen, Bot, BarChart3, LogOut, Settings } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { KiranaLogo } from "@/components/KiranaLogo";

const links = [
  ["/knowledge", "Knowledge", BookOpen], ["/agent", "Assistant", Bot], ["/dashboard", "Dashboard", BarChart3], ["/admin", "Administration", Settings],
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname(); const router = useRouter(); const { logout } = useAuth();
  return <div className="min-h-screen md:grid md:grid-cols-[240px_1fr]">
    <aside className="flex items-center justify-between border-b border-slate-200 bg-white px-5 py-4 md:block md:border-b-0 md:border-r">
      <Link href="/knowledge"><KiranaLogo /></Link>
      <p className="mt-4 hidden border-l-2 border-kirana-gold pl-3 text-xs leading-5 text-slate-500 md:block">Document Intelligence<br/>Knowledge Workspace</p>
      <nav className="mt-0 flex gap-2 md:mt-10 md:block md:space-y-2">{links.map(([href, label, Icon]) => <Link key={href} href={href} className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium ${pathname === href ? "bg-kirana-mist text-kirana-teal" : "text-slate-600 hover:bg-kirana-mist"}`}><Icon size={18}/><span className="hidden md:inline">{label}</span></Link>)}</nav>
      <button onClick={() => { logout(); router.push("/login"); }} className="mt-0 flex items-center gap-2 text-sm text-slate-500 md:mt-10"><LogOut size={17}/><span className="hidden md:inline">Sign out</span></button>
    </aside>
    <main className="p-5 md:p-10">{children}</main>
  </div>;
}

export function ProtectedPage({ children }: { children: React.ReactNode }) { return <AppShell>{children}</AppShell>; }
