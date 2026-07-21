// Regenerate the static MapLibre style JSONs served at maps.vanillax.me/styles/.
//
// VersaTiles v4.6's frontend builds its styles CLIENT-SIDE (via the
// @versatiles/style JS library) and ships no static style.json. External
// MapLibre clients that only take a style *URL* — e.g. RadarNG's native app —
// need a concrete document, so we pre-generate the same styles here, pin the
// output in git, and serve them from the tiny style-server (see
// style-server.yaml). Every URL the output references (tiles / glyphs /
// sprite) points back at this same VersaTiles server and is verified 200.
//
// Run (from this directory):
//   bun add @versatiles/style@5.13.0     # or: npm i @versatiles/style@5.13.0
//   node generate.mjs
//   # then commit the regenerated light.json / dark.json
//
// Bump BASE_URL only if the public hostname changes. Add/swap themes from the
// library's set: colorful, eclipse, graybeard, neutrino, shadow.
import { writeFileSync } from 'node:fs';
import { colorful, eclipse } from '@versatiles/style';

const BASE_URL = 'https://maps.vanillax.me';

function build(fn) {
  const s = fn({ baseUrl: BASE_URL });
  // @versatiles/style emits the modern ARRAY sprite form (sprite: [{id,url}]).
  // MapLibre GL JS accepts it, but MapLibre Native (what RadarNG uses) wants a
  // single string. There's only one sprite source ("basics"), so collapse it.
  if (Array.isArray(s.sprite)) {
    const basics = s.sprite.find((x) => x.id === 'basics') ?? s.sprite[0];
    s.sprite = basics.url;
  }
  return s;
}

writeFileSync('light.json', JSON.stringify(build(colorful), null, '\t') + '\n');
writeFileSync('dark.json', JSON.stringify(build(eclipse), null, '\t') + '\n');
console.log('wrote light.json (colorful) + dark.json (eclipse)');
