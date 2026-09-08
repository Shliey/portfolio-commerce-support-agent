import { execFileSync } from "node:child_process";
import { readFile, rm } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const pidFile = fileURLToPath(new URL("../.e2e-pids.json", import.meta.url));

function stop(pid: number | undefined): void {
  if (!pid) return;
  try {
    if (process.platform === "win32") {
      execFileSync("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore" });
    } else {
      process.kill(-pid, "SIGTERM");
    }
  } catch {
    // A service that already exited needs no cleanup.
  }
}

export default async function globalTeardown(): Promise<void> {
  const pids = JSON.parse(await readFile(pidFile, "utf8")) as {
    backend?: number;
    frontend?: number;
  };
  stop(pids.backend);
  stop(pids.frontend);
  await rm(pidFile, { force: true });
}

