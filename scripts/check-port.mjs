#!/usr/bin/env node
/**
 * Refuses to start a dev server on a port that's already taken.
 *
 * On Windows two servers can listen on the same port, and the old one keeps
 * answering, so you end up testing old code against an old database without
 * noticing. This catches that and tells you how to stop the old server.
 *
 * Usage: node scripts/check-port.mjs 8000
 */
import { execSync } from "node:child_process";

const port = Number(process.argv[2]);
const isWindows = process.platform === "win32";

function run(command) {
  try {
    return execSync(command, { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] });
  } catch {
    return "";
  }
}

/** Process ids listening on the port. */
function listeners() {
  if (isWindows) {
    // "  TCP    127.0.0.1:8000    0.0.0.0:0    LISTENING    21284"
    return run("netstat -ano -p tcp")
      .split(/\r?\n/)
      .filter((line) => line.includes("LISTENING"))
      .map((line) => line.trim().split(/\s+/))
      .filter(([, local]) => local?.endsWith(`:${port}`))
      .map((cols) => cols.at(-1));
  }
  return run(`lsof -ti tcp:${port} -sTCP:LISTEN`).split(/\s+/);
}

const pids = [...new Set(listeners())].filter((pid) => pid && pid !== "0");

if (pids.length > 0) {
  const stop = isWindows ? pids.map((pid) => `taskkill /PID ${pid} /T /F`).join("\n  ") : `kill ${pids.join(" ")}`;
  console.error(`\nPort ${port} is already in use (process ${pids.join(", ")}), probably an old dev server.`);
  console.error(`Stop it, then run the command again:\n\n  ${stop}\n`);
  process.exit(1);
}
