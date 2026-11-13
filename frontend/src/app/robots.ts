import type { MetadataRoute } from "next";

/** Public pages may be indexed; the signed-in app, admin and auth flows may not. */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: ["/", "/pricing", "/self-hosted", "/docs", "/legal", "/privacy", "/terms",
        "/licence-agreement", "/dpa"],
      disallow: ["/api/", "/admin", "/dashboard", "/monitors", "/incidents", "/settings", "/billing",
        "/login", "/register", "/forgot-password", "/reset-password", "/verify-email",
        "/confirm-alerts", "/unsubscribe", "/accept-invite"],
    },
  };
}
