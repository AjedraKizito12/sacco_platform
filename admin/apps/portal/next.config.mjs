/** @type {import('next').NextConfig} */
const cspDirectives = {
  "default-src": ["'self'"],
  // Next.js dev needs unsafe-eval for HMR; production drops it via the
  // middleware in sub-plan 07. unsafe-inline is required for streaming SSR
  // bootstrap until we wire nonces (also sub-plan 07).
  "script-src": ["'self'", "'unsafe-eval'", "'unsafe-inline'"],
  "style-src": ["'self'", "'unsafe-inline'"],
  "img-src": ["'self'", "data:", "blob:"],
  "font-src": ["'self'"],
  "connect-src": [
    "'self'",
    // Backend API. Sub-plan 05 reads this from NEXT_PUBLIC_API_BASE_URL and
    // we'd ideally template it in, but headers() runs at build time. Keep
    // permissive in dev; the production reverse-proxy enforces tighter
    // origin policy.
    "http://localhost:8001",
    "http://localhost:8000",
    "ws://localhost:3000",
  ],
  "frame-ancestors": ["'none'"],
  "form-action": ["'self'"],
  "base-uri": ["'self'"],
  "object-src": ["'none'"],
};

const cspString = Object.entries(cspDirectives)
  .map(([directive, values]) => `${directive} ${values.join(" ")}`)
  .join("; ");

const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  // Library packages from the workspace must be transpiled by Next so
  // their TypeScript / ESM exports work without pre-built dist/ output.
  transpilePackages: ["@sacco/ui", "@sacco/api-client", "@sacco/schemas"],
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "Content-Security-Policy", value: cspString },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
