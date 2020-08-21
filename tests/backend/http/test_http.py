# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import pytest
import re
import trio
import ssl
from uuid import uuid4
from tests.common import customize_fixtures
import h11

from guardata import __version__ as guardata_version
from guardata.api.protocol import OrganizationID, InvitationType
from guardata.core.types.backend_address import BackendInvitationAddr


@pytest.fixture
def backend_http_send(running_backend, backend_addr):
    async def _http_send(target):
        stream = await trio.open_tcp_stream(backend_addr.hostname, backend_addr.port)
        if backend_addr.use_ssl:
            ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            ssl_context.load_default_certs()
            stream = trio.SSLStream(stream, ssl_context, server_hostname=backend_addr.hostname)

        if isinstance(target, str):
            target = target.encode("utf8")
        req = b"GET %s HTTP/1.1\r\nHost: %s\r\n" % (target, backend_addr.hostname)
        await stream.send_all(req)
        rep = await stream.receive_some(4096)
        await stream.aclose()
        return rep.decode("utf8")

    return _http_send


@pytest.mark.trio
async def test_get_not_utf8_path(running_backend, backend_addr):
    # Invalid HTTP target part (not ISO-8859-1)
    target = b"/\xf1"
    req = b"GET %s HTTP/1.0\r\n\r\n" % target

    stream = await trio.open_tcp_stream(backend_addr.hostname, backend_addr.port)
    await stream.send_all(req)
    rep = await stream.receive_some()
    assert rep == b""

    # Connection is now closed
    with pytest.raises(trio.BrokenResourceError):
        await stream.send_all(req)


@pytest.mark.trio
async def test_bad_method(running_backend, backend_addr):
    req = b"SPAM / HTTP/1.0\r\n\r\n"

    stream = await trio.open_tcp_stream(backend_addr.hostname, backend_addr.port)
    await stream.send_all(req)
    rep = await stream.receive_some()
    assert rep.startswith(b"HTTP/1.1 405 Method Not Allowed\r\n")


@pytest.mark.trio
async def test_bad_method_encoding(running_backend, backend_addr):
    # Try with invalid HTTP method (not ISO-8859-1)
    req = b"G\xf1T / HTTP/1.0\r\n\r\n"

    stream = await trio.open_tcp_stream(backend_addr.hostname, backend_addr.port)
    await stream.send_all(req)
    rep = await stream.receive_some()
    assert rep == b""

    # Connection is now closed
    with pytest.raises(trio.BrokenResourceError):
        await stream.send_all(req)


@pytest.mark.trio
@pytest.mark.parametrize("debug", [False, True])
async def test_default_response_headers(backend_factory, server_factory, backend_http_send, debug):
    config = {}
    if debug:
        config["debug"] = True

    async with backend_factory(populated=False, config=config) as backend:
        async with server_factory(backend.handle_client) as server:
            stream = await trio.open_tcp_stream(server.addr.hostname, server.addr.port)

            req = b"GET / HTTP/1.0\r\n\r\n"
            await stream.send_all(req)
            rep = await stream.receive_some()
            if debug:
                val = b"server: guardata/%s %s\r\n" % (
                    guardata_version.encode(),
                    h11.PRODUCT_ID.encode(),
                )
                assert val in rep
            else:
                assert b"server: guardata\r\n" in rep
            assert b"content-type: text/html;charset=utf-8\r\n" in rep
            assert b"date: " in rep


@pytest.mark.trio
async def test_get_404(backend_http_send):
    rep = await backend_http_send("/dummy")
    assert rep.startswith("HTTP/1.1 404 Not Found\r\n")


@pytest.mark.trio
async def test_get_root(backend_http_send):
    rep = await backend_http_send("/")
    assert rep.startswith("HTTP/1.1 200 OK\r\n")


@pytest.mark.trio
async def test_get_static(backend_http_send):
    # Get resource
    rep = await backend_http_send("/static/favicon.ico")
    assert rep.startswith("HTTP/1.1 200 OK\r\n")

    # Also test resource in a subfolder
    rep = await backend_http_send("/static/base.css")
    assert rep.startswith("HTTP/1.1 200 OK\r\n")

    # __init__.py is present but shouldn't be visible
    rep = await backend_http_send("/static/__init__.py")
    assert rep.startswith("HTTP/1.1 404 Not Found\r\n")

    # Finally test non-existing resource
    rep = await backend_http_send("/static/dummy")
    assert rep.startswith("HTTP/1.1 404 Not Found\r\n")

    # Prevent from leaving the static directory
    rep = await backend_http_send("/static/../__init__.py")
    assert rep.startswith("HTTP/1.1 404 Not Found\r\n")


@pytest.mark.trio
async def test_get_redirect_not_available(backend_http_send):
    rep = await backend_http_send("/redirect/foo/bar?a=1&b=2")
    assert rep.startswith("HTTP/1.1 501 Not Implemented\r\n")


@pytest.mark.trio
@customize_fixtures(backend_has_email=True)
async def test_get_redirect(backend_http_send, backend_addr):
    rep = await backend_http_send("/redirect/foo/bar?a=1&b=2")
    assert rep.startswith("HTTP/1.1 200 OK\r\n")
    assert rep.find("<div class=\"parsecLink\">parsec://example.com:9999/foo/bar?a=1&b=2&no_ssl=true") > 0


@pytest.mark.trio
@customize_fixtures(backend_over_ssl=True, backend_has_email=True)
async def test_get_redirect_over_ssl(backend_http_send, backend_addr):
    rep = await backend_http_send("/redirect/foo/bar?a=1&b=2")
    assert rep.startswith("HTTP/1.1 200 OK\r\n")
    assert rep.find("<div class=\"parsecLink\">parsec://example.com:9999/foo/bar?a=1&b=2") > 0


@pytest.mark.trio
@customize_fixtures(backend_has_email=True)
async def test_get_redirect_no_ssl_param_overwritten(backend_http_send, backend_addr):
    rep = await backend_http_send("/redirect/spam?no_ssl=false&a=1&b=2")
    assert rep.startswith("HTTP/1.1 200 OK\r\n")
    assert rep.find("<div class=\"parsecLink\">parsec://example.com:9999/spam?a=1&b=2&no_ssl=true") > 0


@pytest.mark.trio
@customize_fixtures(backend_over_ssl=True, backend_has_email=True)
async def test_get_redirect_no_ssl_param_overwritten_with_ssl_enabled(
    backend_http_send, backend_addr
):
    rep = await backend_http_send("/redirect/spam?a=1&b=2&no_ssl=true")
    assert rep.startswith("HTTP/1.1 200 OK\r\n")
    assert rep.find("<div class=\"parsecLink\">parsec://example.com:9999/spam?a=1&b=2") > 0


@pytest.mark.trio
@customize_fixtures(backend_has_email=True)
async def test_get_redirect_invitation(backend_http_send, backend_addr):
    invitation_addr = BackendInvitationAddr.build(
        backend_addr=backend_addr,
        organization_id=OrganizationID("Org"),
        invitation_type=InvitationType.USER,
        token=uuid4(),
    )
    # TODO: should use invitation_addr.to_redirection_url() when available !
    *_, target = invitation_addr.to_url().split("/")
    rep = await backend_http_send(f"/redirect/{target}")
    assert rep.startswith("HTTP/1.1 200 OK\r\n")
    location_match = re.search(r'class="parsecLink">(.+)</div>', rep)
    location_addr = BackendInvitationAddr.from_url(location_match.group(1))
    assert location_addr == invitation_addr


@pytest.mark.trio
@customize_fixtures(backend_over_ssl=True, backend_has_email=True)
async def test_get_redirect_invitation_over_ssl(backend_http_send, backend_addr):
    await test_get_redirect_invitation(backend_http_send, backend_addr)
