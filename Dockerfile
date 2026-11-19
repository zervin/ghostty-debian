ARG DEBIAN_IMAGE=debian:trixie-slim@sha256:7378260c0a098d27ac206225db5e7d92b8c7c84ea7afccc86eeb513756bbd392
FROM ${DEBIAN_IMAGE}
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential debhelper devscripts fakeroot minisign curl ca-certificates \
    pandoc gettext libadwaita-1-dev libgtk-4-dev libxml2-utils pkgconf \
    libbz2-dev libonig-dev xz-utils python3 lintian ncurses-bin \
    desktop-file-utils binutils file patchelf \
    && rm -rf /var/lib/apt/lists/*
# No credentials, source, or dependency cache are baked into this image.
RUN useradd --uid 1000 --create-home builder
USER 1000:1000
ENV HOME=/work/home ZIG_GLOBAL_CACHE_DIR=/work/zig-cache
ENV PATH=/work/zig:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
WORKDIR /work
