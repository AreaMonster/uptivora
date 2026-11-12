"use client";

import { createContext, type ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { ApiError, api, type Me, setCsrfToken } from "@/lib/api";

type AuthState = {
  me: Me | null;
  loading: boolean;
  error: ApiError | null;
  refresh: () => Promise<Me | null>;
  setMe: (me: Me | null) => void;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMeState] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

  const setMe = useCallback((value: Me | null) => {
    setCsrfToken(value?.csrf_token ?? null);
    setMeState(value);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const data = await api<Me>("/api/auth/me");
      setMe(data);
      setError(null);
      return data;
    } catch (err) {
      setMe(null);
      setError(err instanceof ApiError ? err : null);
      return null;
    } finally {
      setLoading(false);
    }
  }, [setMe]);

  const logout = useCallback(async () => {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } finally {
      setMe(null);
    }
  }, [setMe]);

  useEffect(() => {
    api<Me>("/api/auth/me")
      .then(
        (data) => {
          setMe(data);
          setError(null);
        },
        (err: unknown) => {
          setMe(null);
          setError(err instanceof ApiError ? err : null);
        },
      )
      .finally(() => setLoading(false));
  }, [setMe]);

  return (
    <AuthContext.Provider value={{ me, loading, error, refresh, setMe, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

/** Signed-in user (only valid inside the authenticated app shell). */
export function useMe(): Me {
  const { me } = useAuth();
  if (!me) throw new Error("useMe called without a session");
  return me;
}
