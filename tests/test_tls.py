"""TLS protocol policy for Mumble control connections."""
import ssl
from unittest.mock import MagicMock, patch

from pymumble_py3.mumble import _wrap_socket


def test_control_socket_requires_tls12_or_newer():
    context = ssl.create_default_context()
    # Start permissively to verify the wrapper enforces its own minimum.
    context.minimum_version = ssl.TLSVersion.MINIMUM_SUPPORTED
    sock = MagicMock()
    with patch("pymumble_py3.mumble.ssl.create_default_context", return_value=context):
        with patch.object(context, "wrap_socket", return_value=MagicMock()) as wrap:
            result = _wrap_socket(sock, server_hostname="mumble.example")

    assert context.minimum_version == ssl.TLSVersion.TLSv1_2
    wrap.assert_called_once_with(sock, server_hostname="mumble.example")
    assert result is wrap.return_value
