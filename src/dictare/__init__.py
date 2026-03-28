"""dictare: Voice-to-text for your terminal."""

__version__ = "0.2.5rc3"

# URL prefix where the OpenVIP protocol endpoints are mounted.
# All OpenVIP routes live under this path (e.g. /openvip/status, /openvip/speech).
# Management (dictare-specific) routes live under /api/.
OPENVIP_BASE_PATH = "/openvip"
