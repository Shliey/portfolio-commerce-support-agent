import { spawn } from "node:child_process";
import { writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const pidFile = fileURLToPath(new URL("../.e2e-pids.json", import.meta.url));

async function waitFor(url: string): Promise<void> {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // The service is still starting.
    }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

export default async function globalSetup(): Promise<void> {
  const detached = process.platform !== "win32";
  const pythonRelative = process.platform === "win32"
    ? "../../.venv/Scripts/python.exe"
    : "../../.venv/bin/python";
  const python = fileURLToPath(new URL(pythonRelative, import.meta.url));
  const vite = fileURLToPath(new URL("../node_modules/vite/bin/vite.js", import.meta.url));
  const projectRoot = fileURLToPath(new URL("../..", import.meta.url));
  const webRoot = fileURLToPath(new URL("..", import.meta.url));

  const backend = spawn(
    python,
    ["-m", "uvicorn", "commerce_support.api:app", "--host", "127.0.0.1", "--port", "8010"],
    { cwd: projectRoot, detached, stdio: "ignore", windowsHide: true },
  );
  const frontend = spawn(
    process.execPath,
    [vite, "--host", "127.0.0.1", "--port", "5174"],
    {
      cwd: webRoot,
      detached,
      stdio: "ignore",
      windowsHide: true,
      env: { ...process.env, VITE_API_BASE: "http://127.0.0.1:8010" },
    },
  );
  backend.unref();
  frontend.unref();
  await writeFile(pidFile, JSON.stringify({ backend: backend.pid, frontend: frontend.pid }));
  await Promise.all([
    waitFor("http://127.0.0.1:8010/health"),
    waitFor("http://127.0.0.1:5174"),
  ]);
}
