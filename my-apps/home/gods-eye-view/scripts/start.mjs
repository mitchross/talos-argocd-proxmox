import { createServer } from '/app/node_modules/vite/dist/node/index.js';

// Most upstream data proxies only register with configureServer, not preview.
const server = await createServer({
  root: '/app',
  configFile: '/app/vite.config.js',
  configLoader: 'runner',
  cacheDir: '/tmp/vite',
  server: {
    host: '0.0.0.0',
    port: 4173,
    strictPort: true,
    allowedHosts: ['gods-eye-view.vanillax.me'],
    cors: false,
    hmr: false,
    watch: null,
    fs: {
      deny: ['**/.gev-cache/**', '**/.gev-logs/**'],
    },
  },
  plugins: [{
    name: 'cluster-runtime',
    enforce: 'pre',
    configureServer(vite) {
      vite.middlewares.use((req, res, next) => {
        const pathname = new URL(req.url, 'http://localhost').pathname;
        if (pathname === '/healthz') {
          res.setHeader('Content-Type', 'text/plain');
          res.end('ok\n');
        } else if (pathname.startsWith('/api/setup/')) {
          res.statusCode = 403;
          res.setHeader('Content-Type', 'application/json');
          res.end(JSON.stringify({ error: 'Provider credentials are managed through 1Password and GitOps.' }));
        } else {
          next();
        }
      });
    },
  }],
});

await server.listen();
server.printUrls();
for (const signal of ['SIGTERM', 'SIGINT']) {
  process.once(signal, async () => {
    await server.close();
    process.exit(0);
  });
}
