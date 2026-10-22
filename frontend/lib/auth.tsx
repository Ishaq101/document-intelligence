"use client";

import { createContext, useContext, useEffect, useState } from "react";

type AuthContextValue = { authenticated: boolean; login: (username: string, password: string) => boolean; logout: () => void };
const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [authenticated, setAuthenticated] = useState(false);
  useEffect(() => setAuthenticated(sessionStorage.getItem("docintel-auth") === "true"), []);
  const login = (username: string, password: string) => {
    const valid = username === "admin" && password === "123456";
    if (valid) { sessionStorage.setItem("docintel-auth", "true"); setAuthenticated(true); }
    return valid;
  };
  const logout = () => { sessionStorage.removeItem("docintel-auth"); setAuthenticated(false); };
  return <AuthContext.Provider value={{ authenticated, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
