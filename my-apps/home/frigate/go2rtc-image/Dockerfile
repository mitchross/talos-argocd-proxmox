FROM golang:1.27.1-alpine@sha256:4cb7ac979db5fcc41cae44b2227ba5ab8a51e8807f40d9ba4dee20a0ad960b5b AS build
RUN apk add --no-cache git
WORKDIR /src
RUN git init . && git remote add origin https://github.com/bober10113/go2rtc.git \
    && git fetch --depth=1 origin ec152af109f3f2ead77b81650772444a91d3fb44 \
    && git checkout --detach FETCH_HEAD
RUN go mod download && go mod verify
# These cover the fork's recovery changes; upstream source-registration tests require other module setup.
RUN go test ./pkg/nest ./pkg/webrtc ./internal/exec ./internal/streams \
    -run 'Test(Nest|NegotiateRTC|GetReceiver|LocalNest|ExecNest|RecentExecNest|ResetLocalNest|Begin|MarkExecNest|MediaCounters|SourceScheme)'
RUN CGO_ENABLED=0 go build -trimpath -o /go2rtc . && /go2rtc -version

FROM busybox:1.38.0@sha256:dc2d74b28e4cf8984fa52af1f39bc7c3d9c73760b41a74d629f5d11b1ab28616
LABEL org.opencontainers.image.source="https://github.com/mitchross/talos-argocd-proxmox"
LABEL org.opencontainers.image.description="Pinned B101 go2rtc for Frigate Nest stream recovery"
COPY --from=build /go2rtc /go2rtc
ENTRYPOINT ["/go2rtc"]
