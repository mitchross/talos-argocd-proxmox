// Regenerate the static MapLibre styles served at maps.vanillax.me/styles/ and
// the in-cluster copies the raster renderer uses (../../raster/styles/).
//
// The VersaTiles frontend builds its styles client-side and ships no static
// style.json, but native MapLibre clients (Radar NG) need a style *URL*. Keep
// @versatiles/style at the version the running VersaTiles server bundles, or
// sprite/icon names drift from what the server serves (that happened once:
// v4.6 → v4.14 moved sprites from /assets/sprites/basics to /assets/sprites/base).
//
// Run (from this directory):
//   bun add @versatiles/style@6.0.1
//   node generate.mjs
//   # then commit the regenerated JSON files
import { writeFileSync } from 'node:fs';
import { osm } from '@versatiles/style';

const PUBLIC_BASE = 'https://maps.vanillax.me';
const IN_CLUSTER_BASE = 'http://versatiles.versatiles.svc.cluster.local:8080';

// The library points the source at a TileJSON whose `tiles` are relative;
// inline them so every client resolves tiles without the TileJSON hop.
function build(theme, base) {
  const style = osm({ theme, urls: { base } });
  for (const source of Object.values(style.sources)) {
    if (source.type === 'vector' && source.url) {
      delete source.url;
      source.tiles = [`${base}/tiles/osm/{z}/{x}/{y}`];
      source.minzoom = 0;
      source.maxzoom = 14;
    }
  }
  return JSON.stringify(style, null, '\t') + '\n';
}

writeFileSync('light.json', build('colorful', PUBLIC_BASE));
writeFileSync('dark.json', build('colorful-dark', PUBLIC_BASE));
writeFileSync('../../raster/styles/light.json', build('colorful', IN_CLUSTER_BASE));
writeFileSync('../../raster/styles/dark.json', build('colorful-dark', IN_CLUSTER_BASE));
console.log('wrote light/dark for maps.vanillax.me and for the in-cluster renderer');
