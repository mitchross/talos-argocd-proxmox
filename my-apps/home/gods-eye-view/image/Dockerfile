# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e

LABEL org.opencontainers.image.source="https://github.com/bilawalsidhu/gods-eye-view" \
      org.opencontainers.image.revision="759652207fd1279ece97f0f19af566feb9a82146" \
      org.opencontainers.image.licenses="MIT"

WORKDIR /app
ADD --checksum=sha256:fcdd9c4d11a388eb3716e4b74730829ec0e039ccd93a1465e820a2937b17ff01 \
    https://codeload.github.com/bilawalsidhu/gods-eye-view/tar.gz/759652207fd1279ece97f0f19af566feb9a82146 /tmp/source.tar.gz
RUN tar -xzf /tmp/source.tar.gz --strip-components=1 -C /app \
    && rm /tmp/source.tar.gz

ENV PUPPETEER_SKIP_DOWNLOAD=true
# Vite, ws, and the Cesium plugin are required by the live data server.
RUN npm ci --include=dev --no-audit --no-fund \
    && npm cache clean --force \
    && mkdir -p /app/.gev-cache /app/.gev-logs

USER 1000:1000
EXPOSE 4173
CMD ["node", "/opt/repo-scripts/start.mjs"]
