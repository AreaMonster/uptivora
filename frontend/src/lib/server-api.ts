import "server-only";

const API_URL = process.env.UPTIVORA_API_INTERNAL_URL ?? "http://localhost:8000";

/** Fetch public API data from a Server Component (request time, never cached). */
export async function serverFetch<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_URL}${path}`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}
