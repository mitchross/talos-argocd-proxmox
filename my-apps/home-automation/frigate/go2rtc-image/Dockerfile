FROM golang:1.27.4-alpine@sha256:70bd7ddea8b6cbe5d6943cde279d6b67feb10cc924fb9100d1d8757c1575b280 AS build
RUN apk add --no-cache git
WORKDIR /src
RUN git init . && git remote add origin https://github.com/mitchross/go2rtc.git \
    && git fetch --depth=1 origin e7600f4665d14e4e2d8c5bbb72cc10285d243269 \
    && git checkout --detach FETCH_HEAD
RUN go mod download && go mod verify
# Upstream's other packages have tests that fail without source registration; run the patched ones.
RUN go test ./pkg/nest ./pkg/webrtc && go test ./internal/streams -run 'TestPreload'
RUN CGO_ENABLED=0 go build -trimpath -o /go2rtc . && /go2rtc -version

FROM busybox:1.38.0@sha256:a46257e06c82ad85242d0d38077d0a52d9896389ca60a1a59d3463db586e5fa4
LABEL org.opencontainers.image.source="https://github.com/mitchross/talos-argocd-proxmox"
LABEL org.opencontainers.image.description="Upstream go2rtc with Nest WebRTC fixes for Frigate"
COPY --from=build /go2rtc /go2rtc
ENTRYPOINT ["/go2rtc"]
