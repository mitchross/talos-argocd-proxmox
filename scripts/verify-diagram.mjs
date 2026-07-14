import { readFile } from "node:fs/promises";
import { DOMParser } from "@xmldom/xmldom";
import { diagramHash } from "./diagram-hash.mjs";

const [diagram, ...hashInputs] = process.argv.slice(2);

if (!diagram || hashInputs.length === 0) {
  throw new Error(
    "usage: node scripts/verify-diagram.mjs <diagram.svg> <hash-input>...",
  );
}

const document = new DOMParser().parseFromString(
  await readFile(diagram, "utf8"),
  "image/svg+xml",
);
const svg = document.documentElement;
const expectedHash = await diagramHash(hashInputs);

if (svg.localName !== "svg") {
  throw new Error(`${diagram}: expected an SVG document`);
}

if (svg.getAttribute("data-source-hash") !== expectedHash) {
  throw new Error(`${diagram}: generated asset is stale; run npm run diagrams`);
}

if (!document.getElementsByTagName("title").length) {
  throw new Error(`${diagram}: missing accessible title`);
}

if (!document.getElementsByTagName("desc").length) {
  throw new Error(`${diagram}: missing accessible description`);
}

if (document.getElementsByTagName("foreignObject").length) {
  throw new Error(`${diagram}: HTML labels break static SVG renderers`);
}

if (svg.getAttributeNS("http://www.w3.org/XML/1998/namespace", "space") !== "preserve") {
  throw new Error(`${diagram}: missing xml:space=preserve`);
}

const styles = Array.from(document.getElementsByTagName("style"))
  .map((style) => style.textContent)
  .join("\n");

if (!styles.includes("prefers-reduced-motion")) {
  throw new Error(`${diagram}: missing reduced-motion fallback`);
}
