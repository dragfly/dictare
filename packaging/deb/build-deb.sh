#!/bin/bash
#
# Build a .deb package for voxtype
#
# Usage: ./build-deb.sh
# Output: voxtype_<version>_<arch>.deb
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Read version from source
VERSION=$(python3 -c "
import re, pathlib
text = pathlib.Path('$REPO_ROOT/src/voxtype/__init__.py').read_text()
print(re.search(r'__version__\s*=\s*\"(.+?)\"', text).group(1))
")

# Debian doesn't allow hyphens in upstream version; replace 'a' pre-release
# e.g. 3.0.0a61 -> 3.0.0~a61
DEB_VERSION=$(echo "$VERSION" | sed 's/a/~a/')

ARCH=$(dpkg --print-architecture 2>/dev/null || echo "amd64")

echo "Building voxtype ${DEB_VERSION} for ${ARCH}..."

# Create temp build directory
BUILD_DIR=$(mktemp -d)
PKG_DIR="${BUILD_DIR}/voxtype_${DEB_VERSION}_${ARCH}"
trap "rm -rf $BUILD_DIR" EXIT

# Create directory structure
mkdir -p "${PKG_DIR}/DEBIAN"
mkdir -p "${PKG_DIR}/opt/voxtype"
mkdir -p "${PKG_DIR}/usr/local/bin"

# Create venv and install voxtype
echo "Creating venv and installing voxtype..."
uv venv --python 3.11 "${PKG_DIR}/opt/voxtype/.venv"
VIRTUAL_ENV="${PKG_DIR}/opt/voxtype/.venv" \
    uv pip install --python "${PKG_DIR}/opt/voxtype/.venv/bin/python" \
    "voxtype==${VERSION}" --prerelease=allow

# Create wrapper script
cat > "${PKG_DIR}/usr/local/bin/voxtype" << 'WRAPPER'
#!/bin/sh
exec /opt/voxtype/.venv/bin/voxtype "$@"
WRAPPER
chmod 755 "${PKG_DIR}/usr/local/bin/voxtype"

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
dpkg-deb --build "${PKG_DIR}" "${SCRIPT_DIR}/voxtype_${DEB_VERSION}_${ARCH}.deb"

echo ""
echo "Package built: voxtype_${DEB_VERSION}_${ARCH}.deb"
echo ""
echo "Install with:  sudo dpkg -i voxtype_${DEB_VERSION}_${ARCH}.deb"
echo "Remove with:   sudo dpkg -r voxtype"
