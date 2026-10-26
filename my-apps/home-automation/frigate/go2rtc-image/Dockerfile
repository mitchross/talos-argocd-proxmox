FROM golang:1.27.3-alpine@sha256:b8c9b82affbbb82a020bbcf998dad2ba9516944ac7e883524642a481a9505e9c AS build
RUN apk add --no-cache git
WORKDIR /src
RUN git init . && git remote add origin https://github.com/mitchross/go2rtc.git \
    && git fetch --depth=1 origin e7600f4665d14e4e2d8c5bbb72cc10285d243269 \
    && git checkout --detach FETCH_HEAD
RUN go mod download && go mod verify
# Upstream's other packages have tests that fail without source registration; run the patched ones.
RUN go test ./pkg/nest ./pkg/webrtc && go test ./internal/streams -run 'TestPreload'
RUN CGO_ENABLED=0 go build -trimpath -o /go2rtc . && /go2rtc -version

FROM busybox:1.38.0@sha256:fd7dc98638c8e305f4dc34e979f1c0fdfdcaeb0fbf8fcff77ae834b6da3d7e6e
LABEL org.opencontainers.image.source="https://github.com/mitchross/talos-argocd-proxmox"
LABEL org.opencontainers.image.description="Upstream go2rtc with Nest WebRTC fixes for Frigate"
COPY --from=build /go2rtc /go2rtc
ENTRYPOINT ["/go2rtc"]
