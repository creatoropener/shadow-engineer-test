// Syntax-only baseline. A passing independent behavior regression is still required.
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { spawnSync } from "node:child_process";

const { JSDOM } = createRequire("/opt/patchproof/node/package.json")("jsdom");
const target = path.resolve(process.argv[2] || "index.html");
const root = fs.realpathSync(process.cwd());
const dom = new JSDOM(fs.readFileSync(target, "utf8")); // No scripts or resources execute.
const types = new Set(["", "module", "text/javascript", "application/javascript",
  "text/ecmascript", "application/ecmascript"]);
let checked = 0;
let remote = 0;

for (const script of dom.window.document.querySelectorAll("script")) {
  const type = (script.getAttribute("type") || "").trim().toLowerCase();
  if (!types.has(type)) continue; // JSON-LD, import maps, and other data blocks.
  const src = script.getAttribute("src");
  let code = script.textContent;
  let label = `${target}#inline-${checked + 1}`;
  if (src) {
    if (/^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(src)) {
      remote++;
      continue;
    }
    const relative = decodeURIComponent(src.split(/[?#]/, 1)[0]);
    const local = fs.realpathSync(relative.startsWith("/")
      ? path.resolve(root, `.${relative}`)
      : path.resolve(path.dirname(target), relative));
    if (!local.startsWith(root + path.sep)) throw new Error("Script path escapes repository");
    code = fs.readFileSync(local, "utf8");
    label = local;
  }
  if (!code.trim()) continue;
  const result = spawnSync(process.execPath,
    ["--check", `--input-type=${type === "module" ? "module" : "commonjs"}`],
    { input: code, encoding: "utf8" });
  if (result.error || result.status !== 0) {
    console.error(`${label}: ${result.error || result.stderr}`);
    process.exitCode = 1;
  }
  checked++;
}
dom.window.close();
console.log(`Syntax checked ${checked} script(s); ${remote} remote script(s) not checked. No behavior verified by this gate.`);
