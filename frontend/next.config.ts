import type { NextConfig } from "next";

// The browser always calls same-origin /api/*; Next proxies it to FastAPI.
// This avoids CORS and keeps auth cookies first-party.
const apiUrl = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

export default nextConfig;
