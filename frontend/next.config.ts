import type { NextConfig } from "next";

// The browser always calls same-origin /api/*; Next proxies it to FastAPI.
// This avoids CORS and keeps auth cookies first-party.
const apiUrl = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

// The dev server only serves its scripts and hot reload to localhost unless told
// otherwise, so a page opened at WEB_BASE_URL (e.g. http://knowhub-local.com, mapped to
// 127.0.0.1 in /etc/hosts) would load without JavaScript. Allow that hostname.
function devOrigins(): string[] {
  try {
    const host = new URL(process.env.WEB_BASE_URL ?? "").hostname;
    return host && host !== "localhost" ? [host] : [];
  } catch {
    return [];
  }
}

const nextConfig: NextConfig = {
  allowedDevOrigins: devOrigins(),
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

export default nextConfig;
