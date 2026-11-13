#!/bin/sh
# Build release images and the self-hosted customer bundle.
#
#   deploy/release/build.sh            # version from backend/pyproject.toml
#   deploy/release/build.sh 0.2.0
#
# Output in dist/:
#   uptivora-selfhosted-<version>.tar.gz   compose stack, docs and both images (offline install)
#   SHA256SUMS
# Run from a clean checkout of the release tag; see docs/operations/release.md.
set -eu
cd "$(dirname "$0")/../.."

VERSION="${1:-$(sed -n 's/^version = "\(.*\)"/\1/p' backend/pyproject.toml | head -n 1)}"
PREFIX="${UPTIVORA_IMAGE_PREFIX:-uptivora}"
case "$VERSION" in
	*[!0-9A-Za-z.-]* | "") echo "invalid version: $VERSION" >&2; exit 1 ;;
esac

if [ -n "$(git status --porcelain)" ] && [ "${ALLOW_DIRTY:-0}" != 1 ]; then
	echo "Working tree is not clean. Commit first (or ALLOW_DIRTY=1 for a test build)." >&2
	exit 1
fi

# Refuse to ship anything that looks like a signing key or secret.
if git ls-files | grep -Eq '(\.pem|\.key|\.uptivora-license)$|(^|/)secrets/|(^|/)\.dev-keys/'; then
	echo "A key, licence or secret file is tracked by git — aborting." >&2
	exit 1
fi

REVISION="$(git rev-parse --short HEAD)"
echo "Building Uptivora $VERSION ($REVISION)"
docker build --pull --label "org.opencontainers.image.version=$VERSION" \
	--label "org.opencontainers.image.revision=$REVISION" -t "$PREFIX/api:$VERSION" backend
docker build --pull --label "org.opencontainers.image.version=$VERSION" \
	--label "org.opencontainers.image.revision=$REVISION" -t "$PREFIX/web:$VERSION" frontend

# The images must not contain development keys or the dev seed.
docker run --rm --entrypoint sh "$PREFIX/api:$VERSION" -c \
	'test ! -e /app/.dev-keys && test ! -e /app/app/devseed.py && test ! -d /app/tests' || {
	echo "Image check failed: development files found in the API image" >&2
	exit 1
}

NAME="uptivora-selfhosted-$VERSION"
OUT="dist/$NAME"
rm -rf "$OUT"
mkdir -p "$OUT/images" "$OUT/docs" "$OUT/license" "$OUT/backups"
cp deploy/selfhosted/compose.yaml deploy/selfhosted/Caddyfile deploy/selfhosted/backup.sh \
	deploy/selfhosted/install.sh "$OUT/"
sed "s/^UPTIVORA_VERSION=.*/UPTIVORA_VERSION=$VERSION/" deploy/selfhosted/.env.example > "$OUT/.env.example"
cp docs/selfhosted/*.md "$OUT/docs/"
# The top-level README points into docs/.
sed 's/](\([a-z]*\.md\)/](docs\/\1/g' docs/selfhosted/README.md > "$OUT/README.md"
chmod +x "$OUT/install.sh" "$OUT/backup.sh"

echo "Saving images ..."
docker save "$PREFIX/api:$VERSION" "$PREFIX/web:$VERSION" | gzip -9 > "$OUT/images/uptivora-$VERSION.tar.gz"

tar -C dist -czf "dist/$NAME.tar.gz" "$NAME"
(cd dist && sha256sum "$NAME.tar.gz" > SHA256SUMS)
echo "Done: dist/$NAME.tar.gz"
cat dist/SHA256SUMS
