# Build stage: Go toolchain pinned by digest (finalists are rebuilt)
FROM golang:1.26.1-bookworm@sha256:ab3d6955bbc813a0f3fdf220c1d817dd89c0b3f283777db8ece4a32fe7858edd AS build
WORKDIR /src
COPY go.mod ./
COPY mech ./mech
COPY cmd ./cmd
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -buildvcs=false -trimpath -ldflags="-s -w" -o /pilot ./cmd/bot

# Runtime: static binary only
FROM scratch
COPY --from=build /pilot /bot/pilot
COPY LICENSE-OvalRunner LICENSE-giddygiddyboy /licenses/
USER 65534:65534
ENTRYPOINT ["/bot/pilot"]
