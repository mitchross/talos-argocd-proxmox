FROM golang:1.26.1-alpine@sha256:2389ebfa5b7f43eeafbd6be0c3700cc46690ef842ad962f6c5bd6be49ed82039 AS build
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

FROM busybox:1.37.0@sha256:9db7b59979c38555a39def84a31fb98b5296952f9e3afd4f6f11f05b07adfab0
LABEL org.opencontainers.image.source="https://github.com/mitchross/talos-argocd-proxmox"
LABEL org.opencontainers.image.description="Pinned B101 go2rtc for Frigate Nest stream recovery"
COPY --from=build /go2rtc /go2rtc
ENTRYPOINT ["/go2rtc"]
