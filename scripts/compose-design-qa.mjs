import { existsSync } from "node:fs";
import path from "node:path";
import sharp from "sharp";

const source = path.resolve(
  process.argv[2] || "docs/reference/linkix-home-source.png",
);
const implementation = path.resolve(
  process.argv[3] || "docs/screenshots/linkix-home-desktop.png",
);
const output = path.resolve(
  process.argv[4] || "docs/screenshots/linkix-design-comparison.png",
);

if (!existsSync(source) || !existsSync(implementation)) {
  throw new Error("source and implementation screenshots are required");
}

const targetWidth = 1400;
const targetHeight = 903;
const [sourcePng, implementationPng] = await Promise.all([
  sharp(source).resize(targetWidth, targetHeight).png().toBuffer(),
  sharp(implementation).resize(targetWidth, targetHeight).png().toBuffer(),
]);

async function composePair(left, right, width, height, destination) {
  await sharp({
    create: {
      width: width * 2,
      height,
      channels: 4,
      background: "#f6f4ef",
    },
  })
    .composite([
      { input: left, left: 0, top: 0 },
      { input: right, left: width, top: 0 },
    ])
    .png()
    .toFile(destination);
}

async function cropPair(region, suffix) {
  const [left, right] = await Promise.all([
    sharp(sourcePng).extract(region).png().toBuffer(),
    sharp(implementationPng).extract(region).png().toBuffer(),
  ]);
  const destination = output.replace(/\.png$/i, `-${suffix}.png`);
  await composePair(left, right, region.width, region.height, destination);
  return destination;
}

await composePair(
  sourcePng,
  implementationPng,
  targetWidth,
  targetHeight,
  output,
);
const focusedOutputs = await Promise.all([
  cropPair({ left: 400, top: 225, width: 600, height: 320 }, "hero"),
  cropPair({ left: 280, top: 675, width: 840, height: 215 }, "bot"),
]);

console.log(output);
for (const focusedOutput of focusedOutputs) {
  console.log(focusedOutput);
}
