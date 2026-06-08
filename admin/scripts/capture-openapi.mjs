// admin/scripts/capture-openapi.mjs
// Boots uvicorn in a child process, waits for /healthz, fetches /openapi.json,
// and writes it to packages/api-client/openapi.json. Commits-ready.
//
// Usage: node admin/scripts/capture-openapi.mjs
// (called from admin/ root via `pnpm openapi:capture`)

import { spawn } from "node:child_process";
import { writeFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "..", "..");
const OUTPUT = resolve(
  __dirname, "..", "packages/api-client/openapi.json",
);
const HOST = "127.0.0.1";
const PORT = process.env.OPENAPI_CAPTURE_PORT ?? "8765";
const URL = `http://${HOST}:${PORT}`;
const HEALTH = `${URL}/healthz`;
const SPEC = `${URL}/openapi.json`;

async function waitForHealth(timeoutMs = 30_000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const r = await fetch(HEALTH);
      if (r.ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`uvicorn did not become healthy within ${timeoutMs}ms`);
}

async function main() {
  // Launch uvicorn from the repo root. Environment must already have
  // DATABASE_URL etc. set (or .env present).
  const child = spawn(
    "python",
    ["-m", "uvicorn", "app.main:app", "--host", HOST, "--port", PORT, "--no-access-log"],
    {
      cwd: REPO_ROOT,
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );

  // Surface errors but don't tee stdout — it's noisy.
  child.stderr.on("data", (b) => process.stderr.write(b));

  try {
    await waitForHealth();
    const r = await fetch(SPEC);
    if (!r.ok) {
      throw new Error(`/openapi.json returned ${r.status}`);
    }
    const json = await r.json();
    await mkdir(dirname(OUTPUT), { recursive: true });
    await writeFile(OUTPUT, JSON.stringify(json, null, 2) + "\n");
    console.log(`wrote ${OUTPUT}`);
  } finally {
    child.kill("SIGTERM");
    // Allow uvicorn 2s to shut down cleanly
    await new Promise((r) => setTimeout(r, 2000));
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
