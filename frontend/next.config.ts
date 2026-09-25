/**
 * Next.js configuration. The app is built as a standalone server (small runtime image).
 * Image optimization is off (the UI has no raster images), which also keeps the 19 MB
 * `sharp` native bundle out of the standalone output.
 * In the Docker stack, Caddy is the single entry point and sends /api/* straight to the
 * backend, so no rewrite is needed (ADR 0006). For `npm run dev` outside Docker, setting
 * BACKEND_URL (e.g. http://localhost:8080, the Caddy entry point) forwards /api/* there so
 * the browser still talks to one origin.
 */
import type { NextConfig } from "next"

const BACKEND_URL = process.env.BACKEND_URL

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  images: { unoptimized: true },
  outputFileTracingExcludes: { "*": ["node_modules/@img/**", "node_modules/sharp/**"] },
  async rewrites() {
    return BACKEND_URL ? [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }] : []
  },
}

export default nextConfig
