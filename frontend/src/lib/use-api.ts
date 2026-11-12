"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "@/lib/api";

/** Minimal data hook: fetch on mount / path change, optional polling, manual reload. */
export function useApi<T>(path: string | null, { refreshMs }: { refreshMs?: number } = {}) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const latest = useRef(0);

  const fetchInto = useCallback(
    (target: string) => {
      const ticket = ++latest.current;
      return api<T>(target).then(
        (result) => {
          if (ticket !== latest.current) return;
          setData(result);
          setError(null);
        },
        (err: unknown) => {
          if (ticket === latest.current && err instanceof ApiError) setError(err);
        },
      );
    },
    [],
  );

  const reload = useCallback(async () => {
    if (path) await fetchInto(path);
  }, [fetchInto, path]);

  useEffect(() => {
    if (!path) return;
    void fetchInto(path);
    if (!refreshMs) return;
    const id = setInterval(() => {
      if (document.visibilityState === "visible") void fetchInto(path);
    }, refreshMs);
    return () => clearInterval(id);
  }, [fetchInto, path, refreshMs]);

  const loading = Boolean(path) && data === null && error === null;
  return { data, error, loading, reload, setData };
}
