import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

async function readLocalEnv() {
  try {
    const source = await readFile(path.join(root, ".env"), "utf8");
    const values = {};
    for (const rawLine of source.split(/\r?\n/)) {
      const line = rawLine.trim();
      if (!line || line.startsWith("#")) continue;
      const separator = line.indexOf("=");
      if (separator < 1) continue;
      const name = line.slice(0, separator).trim();
      let value = line.slice(separator + 1).trim();
      if ((value.startsWith('"') && value.endsWith('"')) ||
          (value.startsWith("'") && value.endsWith("'"))) {
        value = value.slice(1, -1);
      }
      values[name] = value;
    }
    return values;
  } catch (error) {
    if (error && error.code === "ENOENT") return {};
    throw error;
  }
}

const localEnv = await readLocalEnv();
const apiKey = String(process.env.GEMINI_API_KEY || localEnv.GEMINI_API_KEY || "").trim();
const model = String(process.env.GEMINI_MODEL || localEnv.GEMINI_MODEL || "gemini-3.1-flash-lite").trim();

if (!apiKey) {
  throw new Error("GEMINI_API_KEY is required to generate the browser runtime configuration.");
}

const output = [
  "// Generated during deployment. Do not commit this file.",
  `export const geminiApiKey = ${JSON.stringify(apiKey)};`,
  `export const geminiModel = ${JSON.stringify(model)};`,
  "",
].join("\n");

await writeFile(path.join(root, "public", "js", "gemini-runtime-config.js"), output, {
  encoding: "utf8",
  mode: 0o600,
});

console.log("Generated public/js/gemini-runtime-config.js from GEMINI_API_KEY.");
