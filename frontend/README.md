# Uptivora web app

Next.js 16 (App Router, Cache Components), TypeScript, Tailwind CSS 4, Recharts.

- `src/app/(marketing)` — public site: home, pricing, self-hosted, docs
- `src/app/(auth)` — login, register, password reset, email confirmation
- `src/app/(app)` — signed-in area (client-rendered after the session check)
- `src/proxy.ts` — redirects (self-hosted edition, signed-out users)
- `src/lib/api.ts` — same-origin API client with CSRF header

Environment:

- `UPTIVORA_API_INTERNAL_URL` — where the Next server reaches the API (default `http://localhost:8000`)
- `UPTIVORA_EDITION` — `hosted` (default) or `selfhosted`

`npm run dev`, `npm run build`, `npm run lint`. No analytics, no external fonts or scripts at runtime.
