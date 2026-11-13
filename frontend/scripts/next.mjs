// Runs the Next.js CLI with telemetry switched off for every command (dev, build, start).
// Uptivora must not phone home — neither the product nor its build tooling.
import { spawn } from "node:child_process";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const nextBin = require.resolve("next/dist/bin/next");
const env = { ...process.env, NEXT_TELEMETRY_DISABLED: "1" };

const child = spawn(process.execPath, [nextBin, ...process.argv.slice(2)], { stdio: "inherit", env });
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => child.kill(signal));
child.on("exit", (code, signal) => process.exit(code ?? (signal ? 1 : 0)));
