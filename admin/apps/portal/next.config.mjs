/** @type {import('next').NextConfig} */
const isProd = process.env.NODE_ENV === "production";
const apiOrigin = process.env.NEXT_PUBLIC_API_BASE_URL;

const connectSrc = ["'self'"];
if (apiOrigin) {
  connectSrc.push(apiOrigin);
} else {
  // Local dev fallback: the API runs on the host, ports 8000/8001.
  connectSrc.push("http://localhost:8000", "http://localhost:8001", "ws://localhost:3000");
}

const cspDirectives = {
  "default-src": ["'self'"],
  // Dev needs unsafe-eval for HMR; production drops it.
  "script-src": isProd ? ["'self'", "'unsafe-inline'"] : ["'self'", "'unsafe-eval'", "'unsafe-inline'"],
  "style-src": ["'self'", "'unsafe-inline'"],
  "img-src": ["'self'", "data:", "blob:"],
  "font-src": ["'self'"],
  "connect-src": connectSrc,
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
