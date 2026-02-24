#!/bin/bash
#
# Build a .deb package for dictare
#
# Usage: ./build-deb.sh
# Output: dictare_<version>_<arch>.deb
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Read version from source
VERSION=$(python3 -c "
import re, pathlib
text = pathlib.Path('$REPO_ROOT/src/dictare/__init__.py').read_text()
print(re.search(r'__version__\s*=\s*\"(.+?)\"', text).group(1))
")

# Debian doesn't allow hyphens in upstream version; replace 'a' pre-release
# e.g. 3.0.0a61 -> 3.0.0~a61
DEB_VERSION=$(echo "$VERSION" | sed 's/a/~a/')

ARCH=$(dpkg --print-architecture 2>/dev/null || echo "amd64")

echo "Building dictare ${DEB_VERSION} for ${ARCH}..."

# Create temp build directory
BUILD_DIR=$(mktemp -d)
PKG_DIR="${BUILD_DIR}/dictare_${DEB_VERSION}_${ARCH}"
trap "rm -rf $BUILD_DIR" EXIT

# Create directory structure
mkdir -p "${PKG_DIR}/DEBIAN"
mkdir -p "${PKG_DIR}/opt/dictare"
mkdir -p "${PKG_DIR}/usr/local/bin"

# Create venv and install dictare
echo "Creating venv and installing dictare..."
uv venv --python 3.11 "${PKG_DIR}/opt/dictare/.venv"
VIRTUAL_ENV="${PKG_DIR}/opt/dictare/.venv" \
    uv pip install --python "${PKG_DIR}/opt/dictare/.venv/bin/python" \
    "dictare==${VERSION}" --prerelease=allow

# Create wrapper script
cat > "${PKG_DIR}/usr/local/bin/dictare" << 'WRAPPER'
#!/bin/sh
exec /opt/dictare/.venv/bin/dictare "$@"
WRAPPER
chmod 755 "${PKG_DIR}/usr/local/bin/dictare"

# Generate control file with version
sed "s/@VERSION@/${DEB_VERSION}/g; s/@ARCH@/${ARCH}/g" \
    "${SCRIPT_DIR}/debian/control" > "${PKG_DIR}/DEBIAN/control"

# Copy maintainer scripts
for script in postinst prerm postrm; do
    if [ -f "${SCRIPT_DIR}/debian/${script}" ]; then
        cp "${SCRIPT_DIR}/debian/${script}" "${PKG_DIR}/DEBIAN/${script}"
        chmod 755 "${PKG_DIR}/DEBIAN/${script}"
    fi
done

# Build the package
dpkg-deb --build "${PKG_DIR}" "${SCRIPT_DIR}/dictare_${DEB_VERSION}_${ARCH}.deb"

echo ""
echo "Package built: dictare_${DEB_VERSION}_${ARCH}.deb"
echo ""
echo "Install with:  sudo dpkg -i dictare_${DEB_VERSION}_${ARCH}.deb"
echo "Remove with:   sudo dpkg -r dictare"
