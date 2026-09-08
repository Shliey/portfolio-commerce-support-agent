import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const forbidden = [
  /ANTHROPIC_API_KEY/i,
  /OPENAI_API_KEY/i,
  /sk-ant-[a-z0-9_-]+/i,
  /sk-[a-z0-9]{20,}/i,
  /authorization:\s*bearer\s+[a-z0-9._-]+/i,
];

async function files(path) {
  const entries = await readdir(path, { withFileTypes: true });
  const nested = await Promise.all(entries.map(entry => {
    const resolved = join(path, entry.name);
    return entry.isDirectory() ? files(resolved) : [resolved];
  }));
  return nested.flat();
}

for (const path of await files(fileURLToPath(new URL("../dist", import.meta.url)))) {
  const content = await readFile(path, "utf8");
  for (const pattern of forbidden) {
    if (pattern.test(content)) throw new Error(`credential-like content in ${path}: ${pattern}`);
  }
}
console.log("dist credential scan passed");
