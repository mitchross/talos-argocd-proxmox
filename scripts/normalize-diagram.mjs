import { readFile, writeFile } from "node:fs/promises";
import { DOMParser, XMLSerializer } from "@xmldom/xmldom";
import { diagramHash } from "./diagram-hash.mjs";

const [path, ...hashInputs] = process.argv.slice(2);

if (!path || hashInputs.length === 0) {
  throw new Error(
    "usage: node scripts/normalize-diagram.mjs <diagram.svg> <hash-input>...",
  );
}

const source = await readFile(path, "utf8");
const document = new DOMParser().parseFromString(source, "image/svg+xml");
const svg = document.documentElement;

if (svg.localName !== "svg") {
  throw new Error(`${path}: expected an SVG document`);
}

svg.setAttributeNS(
  "http://www.w3.org/XML/1998/namespace",
  "xml:space",
  "preserve",
);
svg.setAttribute("data-source-hash", await diagramHash(hashInputs));

await writeFile(path, new XMLSerializer().serializeToString(document));
