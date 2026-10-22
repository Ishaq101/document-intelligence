"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { useAuth } from "@/lib/auth";
import { KiranaLogo } from "@/components/KiranaLogo";

export default function LoginPage() {
  const router = useRouter(); const { login } = useAuth(); const [error, setError] = useState("");
  const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const data = new FormData(event.currentTarget); if (login(String(data.get("username")), String(data.get("password")))) router.push("/knowledge"); else setError("Kredensial tidak valid."); };
  return <main className="grid min-h-screen place-items-center bg-kirana-mist p-5"><form onSubmit={submit} className="w-full max-w-sm rounded-2xl bg-white p-8 shadow-sm ring-1 ring-slate-200"><KiranaLogo/><div className="mt-8 border-l-2 border-kirana-gold pl-3"><p className="text-sm font-semibold text-kirana-teal">DOCUMENT INTELLIGENCE</p><h1 className="mt-1 text-2xl font-bold text-kirana-navy">Sign in</h1><p className="mt-2 text-sm text-slate-500">Access Kirana Logistic Group knowledge workspace.</p></div><label className="mt-6 block text-sm font-medium">Username<input name="username" defaultValue="admin" className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2"/></label><label className="mt-4 block text-sm font-medium">Password<input name="password" type="password" defaultValue="123456" className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2"/></label>{error && <p className="mt-3 text-sm text-red-600">{error}</p>}<button className="mt-6 w-full rounded-lg bg-kirana-teal py-2.5 font-medium text-white hover:bg-kirana-navy">Sign in</button></form></main>;
}
