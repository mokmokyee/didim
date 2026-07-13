import { readFile, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const taxonomyPath = path.join(root, "collector", "data", "keyword_taxonomy.json");
const filterMapPath = path.join(root, "collector", "data", "filter_keyword_map.json");
const outputPath = path.join(root, "public", "data", "search_taxonomy.json");

const [taxonomy, filterMap] = await Promise.all([
  readFile(taxonomyPath, "utf8").then(JSON.parse),
  readFile(filterMapPath, "utf8").then(JSON.parse),
]);

const output = `${JSON.stringify({
  version: taxonomy.version,
  keywords: taxonomy.keywords.map(({ id, label, aliases }) => ({ id, label, aliases })),
  filters: filterMap.filters,
}, null, 2)}\n`;

if (process.argv.includes("--check")) {
  let current = "";
  try {
    current = await readFile(outputPath, "utf8");
  } catch {
    // The message below explains how to create the generated file.
  }
  if (current !== output) {
    console.error("Search taxonomy is out of date. Run: npm run search-taxonomy:sync");
    process.exit(1);
  }
} else {
  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(outputPath, output, "utf8");
  console.log(`Updated ${path.relative(root, outputPath)}`);
}
