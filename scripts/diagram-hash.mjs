import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";

export async function diagramHash(paths) {
  const hash = createHash("sha256");

  for (const path of paths) {
    hash.update(await readFile(path));
    hash.update("\0");
  }

  return hash.digest("hex");
}
