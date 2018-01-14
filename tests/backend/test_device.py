import pytest
from unittest.mock import patch
from nacl.public import PrivateKey, SealedBox

from parsec.utils import to_jsonb64, from_jsonb64

from tests.common import freeze_time, connect_backend
from tests.backend.test_user import mock_generate_token


@pytest.fixture
async def token(backend, alice):
    token = '1234567890'
    with freeze_time('2017-07-07T00:00:00'):
        await backend.user.declare_unconfigured_device(token, alice.user_id, 'phone2')
    return token


@pytest.mark.trio
async def test_device_declare(backend, alice, bob, mock_generate_token):
    mock_generate_token.return_value = '<token>'
    async with connect_backend(backend, auth_as=alice) as sock:
        await sock.send({
            'cmd': 'device_declare',
            'device_name': 'phone2',
        })
        rep = await sock.recv()
    assert rep == {
        'status': 'ok',
        'token': '<token>',
    }


@pytest.mark.parametrize('bad_msg', [
    {'device_name': 42},
    {'device_name': None},
    {'device_name': 'phone2', 'unknown': 'field'},
    {}
])
@pytest.mark.trio
async def test_device_declare_bad_msg(backend, alice, bad_msg):
    async with connect_backend(backend, auth_as=alice) as sock:
        await sock.send({'cmd': 'device_declare', **bad_msg})
        rep = await sock.recv()
        assert rep['status'] == 'bad_message'


@pytest.mark.trio
async def test_device_configure(backend, alice, token, mock_generate_token):
    mock_generate_token.side_effect = ['<config_try_id>']
    verifykey = b'0\xba\x9fY\xd1\xb4D\x93\r\xf6\xa7[\xe8\xaa\xf9\xeea\xb8\x01\x98\xc1~im}C\xfa\xde\\\xe6\xa1-'
    cypherkey = b"\x8b\xfc\xc1\x88\xb7\xd7\x16t\xce<\x7f\xd2j_fTI\x14r':\rF!\xff~\xa8\r\x912\xe3N"

    async with connect_backend(backend, auth_as='anonymous') as anonymous_sock, \
            connect_backend(backend, auth_as=alice) as alice_sock:

        await alice_sock.send({
            'cmd': 'event_subscribe',
            'event': 'device_try_claim_submitted',
        })
        rep = await alice_sock.recv()

        await anonymous_sock.send({
            'cmd': 'device_configure',
            'user_id': 'alice',
            'device_name': 'phone2',
            'token': token,
            'device_verify_key': to_jsonb64(verifykey),
            'user_privkey_cypherkey': to_jsonb64(cypherkey),
        })

        await alice_sock.send({
            'cmd': 'event_listen',
        })
        rep = await alice_sock.recv()
        assert rep == {
            'status': 'ok',
            'event': 'device_try_claim_submitted',
            'subject': '<config_try_id>',
        }

        await alice_sock.send({
            'cmd': 'device_get_configuration_try',
            'configuration_try_id': '<config_try_id>',
        })
        rep = await alice_sock.recv()
        assert rep == {
            'status': 'ok',
            'status': 'waiting_answer',
            'device_name': 'phone2',
            'device_verify_key': 'MLqfWdG0RJMN9qdb6Kr57mG4AZjBfmltfUP63lzmoS0=\n',
            'user_privkey_cypherkey': 'i/zBiLfXFnTOPH/Sal9mVEkUcic6DUYh/36oDZEy404=\n',
        }
        user_privkey_cypherkey = PrivateKey(from_jsonb64(rep['user_privkey_cypherkey']))

        box = SealedBox(user_privkey_cypherkey)
        cyphered_user_privkey = box.encrypt(alice.privkey.encode())
        await alice_sock.send({
            'cmd': 'device_accept_configuration_try',
            'configuration_try_id': '<config_try_id>',
            'cyphered_user_privkey': to_jsonb64(cyphered_user_privkey),
        })
        rep = await alice_sock.recv()
        assert rep == {
            'status': 'ok',
        }

        rep = await anonymous_sock.recv()
        assert rep['status'] == 'ok'
        transmitted_cyphered_user_privkey = from_jsonb64(rep['cyphered_user_privkey'])
        assert transmitted_cyphered_user_privkey == cyphered_user_privkey
