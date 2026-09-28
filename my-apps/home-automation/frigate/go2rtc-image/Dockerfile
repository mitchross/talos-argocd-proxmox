FROM golang:1.27.1-alpine@sha256:8a5910f31396cd4d89662f56c68b3ae31d374308270a1c3bd96672ee5ed43414 AS build
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

FROM busybox:1.38.0@sha256:fd7dc98638c8e305f4dc34e979f1c0fdfdcaeb0fbf8fcff77ae834b6da3d7e6e
LABEL org.opencontainers.image.source="https://github.com/mitchross/talos-argocd-proxmox"
LABEL org.opencontainers.image.description="Pinned B101 go2rtc for Frigate Nest stream recovery"
COPY --from=build /go2rtc /go2rtc
ENTRYPOINT ["/go2rtc"]
