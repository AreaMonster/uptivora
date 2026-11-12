"use client";

import { useSyncExternalStore } from "react";

function subscribe(onChange: () => void) {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

/**
 * The URL fragment without "#". Returns null during server rendering, "" when absent.
 * Email tokens travel in the fragment so they never reach server logs or Referer headers.
 */
export function useUrlHash(): string | null {
  return useSyncExternalStore(
    subscribe,
    () => window.location.hash.slice(1),
    () => null,
  );
}
