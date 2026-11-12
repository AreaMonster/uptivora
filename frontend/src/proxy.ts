import { NextResponse, type NextRequest } from "next/server";

const SESSION_COOKIES = ["__Host-uptivora_session", "uptivora_session"];
const APP_PREFIXES = ["/dashboard", "/monitors", "/incidents", "/settings", "/admin"];
const MARKETING_ONLY = ["/", "/pricing", "/self-hosted"];

/**
 * Runs at request time:
 * - Self-hosted installations have no marketing site: send visitors to the dashboard.
 * - Visitors without a session cookie are sent to the login page before the app shell loads.
 *   (This is only a UX shortcut; every API request is authorised by the backend.)
 */
export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const selfHosted = process.env.UPTIVORA_EDITION === "selfhosted";

  if (selfHosted && MARKETING_ONLY.includes(pathname)) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  const isApp = APP_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`));
  if (isApp && !SESSION_COOKIES.some((name) => request.cookies.has(name))) {
    const login = new URL("/login", request.url);
    login.searchParams.set("next", `${pathname}${search}`);
    return NextResponse.redirect(login);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/", "/pricing", "/self-hosted", "/dashboard/:path*", "/monitors/:path*",
    "/incidents/:path*", "/settings/:path*", "/admin", "/admin/:path*"],
};
