import type { NextConfig } from "next";

// In development the browser talks to Next.js, which forwards /api/* to FastAPI.
// In production Caddy routes /api/* to the API directly; this rewrite is then unused.
const API_URL = process.env.UPTIVORA_API_INTERNAL_URL ?? "http://localhost:8000";

const isDev = process.env.NODE_ENV === "development";

// Everything is served from this origin: no CDNs, fonts, analytics or third-party scripts.
// Next.js streams its RSC payload in inline <script> tags, so 'unsafe-inline' is required for
// scripts without per-request nonces (which would disable static rendering). External script
// sources stay blocked, which is what matters most for this app. Dev adds eval/websocket for HMR.
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self'",
  `connect-src 'self'${isDev ? " ws: wss:" : ""}`,
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
  "manifest-src 'self'",
  "worker-src 'self'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  // Everything is same-origin, so cross-origin isolation costs nothing.
  { key: "Cross-Origin-Embedder-Policy", value: "require-corp" },
  { key: "Cross-Origin-Resource-Policy", value: "same-origin" },
];

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  poweredByHeader: false,
  experimental: {
    // Only validate segments that explicitly export `instant`. The signed-in area is
    // client-rendered behind the session check and cannot have a server-rendered shell.
    instantInsights: { validationLevel: "manual-warning" },
  },
  output: "standalone",
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
