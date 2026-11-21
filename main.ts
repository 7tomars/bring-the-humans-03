// main.ts — the bring-the-humans-03 entry program.
//
// The entry is a TikTok video; this program's whole job is to hand the house
// the video's address: it copies this repository's VIDEO.json into the output
// directory, byte for byte. The house reads the video (and its view count)
// itself — nothing written here about the video counts.

import { copyFileSync, mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const botDir = process.env.MAKEFUN_BOT_DIR ?? ".";
const outDir = process.env.MAKEFUN_OUTPUT_DIR ?? "/output";

const source = join(botDir, "VIDEO.json");
const target = join(outDir, "VIDEO.json");

// Read it as JSON first, so a malformed file fails loudly here instead of
// being handed over unread.
const raw = readFileSync(source);
const parsed: unknown = JSON.parse(raw.toString("utf8"));
const url = (parsed as { url?: unknown } | null)?.url;
if (typeof parsed !== "object" || parsed === null || typeof url !== "string") {
  throw new Error("VIDEO.json must be a JSON object with a url string");
}

// The grader provides the output directory; a local run may not have made
// one yet, so create it rather than fail on a missing folder.
mkdirSync(outDir, { recursive: true });
copyFileSync(source, target);

// The two runs of an entry must write the same bytes: check the copy landed
// exactly as the repository holds it.
if (!readFileSync(target).equals(raw)) {
  throw new Error("copied VIDEO.json differs from the repository's");
}
