# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import pytest
from unittest.mock import ANY

from guardata.api.protocol.base import packb, unpackb, InvalidMessageError
from guardata.api.protocol.handshake import (
    HandshakeFailedChallenge,
    HandshakeBadIdentity,
    HandshakeBadAdministrationToken,
    HandshakeRVKMismatch,
    HandshakeRevokedDevice,
    ServerHandshake,
    BaseClientHandshake,
    APIV1_AnonymousClientHandshake,
    APIV1_AdministrationClientHandshake,
    APIV1_HandshakeType,
    HandshakeOrganizationExpired,
)
from guardata.api.version import API_V1_VERSION


@pytest.mark.parametrize("check_rvk", (True, False))
def test_good_anonymous_handshake(coolorg, check_rvk):
    sh = ServerHandshake()

    if check_rvk:
        ch = APIV1_AnonymousClientHandshake(coolorg.organization_id, coolorg.root_verify_key)
    else:
        ch = APIV1_AnonymousClientHandshake(coolorg.organization_id)
    assert sh.state == "stalled"

    challenge_req = sh.build_challenge_req()
    assert sh.state == "challenge"

    answer_req = ch.process_challenge_req(challenge_req)

    sh.process_answer_req(answer_req)
    assert sh.state == "answer"
    assert sh.answer_type == APIV1_HandshakeType.ANONYMOUS
    if check_rvk:
        assert sh.answer_data == {
            "client_api_version": API_V1_VERSION,
            "organization_id": coolorg.organization_id,
            "rvk": coolorg.root_verify_key,
        }
    else:
        assert sh.answer_data == {
            "client_api_version": API_V1_VERSION,
            "organization_id": coolorg.organization_id,
            "rvk": None,
        }
    result_req = sh.build_result_req()
    assert sh.state == "result"

    ch.process_result_req(result_req)
    assert sh.client_api_version == API_V1_VERSION


def test_good_administration_handshake():
    admin_token = "Xx" * 16
    sh = ServerHandshake()

    ch = APIV1_AdministrationClientHandshake(admin_token)
    assert sh.state == "stalled"

    challenge_req = sh.build_challenge_req()
    assert sh.state == "challenge"

    answer_req = ch.process_challenge_req(challenge_req)

    sh.process_answer_req(answer_req)
    assert sh.state == "answer"
    assert sh.answer_type == APIV1_HandshakeType.ADMINISTRATION
    assert sh.answer_data == {"client_api_version": API_V1_VERSION, "token": admin_token}
    result_req = sh.build_result_req()
    assert sh.state == "result"

    ch.process_result_req(result_req)
    assert sh.client_api_version == API_V1_VERSION


# 1) Server build challenge (nothing more to test...)

# 2) Client process challenge

# 2-b) Client check API version

# 3) Server process answer
@pytest.mark.parametrize(
    "req",
    [
        {},
        {"handshake": "answer", "type": "dummy"},  # Invalid type
        # Anonymous answer
        {
            "handshake": "answer",
            "type": APIV1_HandshakeType.ANONYMOUS.value,
            "organization_id": "<good>",
            "rvk": b"dummy",  # Invalid VerifyKey
        },
        {
            "handshake": "answer",
            "type": APIV1_HandshakeType.ANONYMOUS.value,
            "organization_id": "d@mmy",  # Invalid OrganizationID
            "rvk": "<good>",
        },
        # Admin answer
        {
            "handshake": "answer",
            "type": APIV1_HandshakeType.ADMINISTRATION.value,
            # Missing token
        },
    ],
)
def test_process_answer_req_bad_format(req, alice):
    for key, good_value in [
        ("organization_id", alice.organization_id),
        ("device_id", alice.device_id),
        ("rvk", alice.root_verify_key.encode()),
    ]:
        if req.get(key) == "<good>":
            req[key] = good_value
    req["client_api_version"] = API_V1_VERSION
    sh = ServerHandshake()
    sh.build_challenge_req()
    with pytest.raises(InvalidMessageError):
        sh.process_answer_req(packb(req))


# 4) Server build result


def test_build_result_req_bad_key(alice, bob):
    sh = ServerHandshake()
    sh.build_challenge_req()
    answer = {
        "handshake": "answer",
        "type": "authenticated",
        "client_api_version": API_V1_VERSION,
        "organization_id": alice.organization_id,
        "device_id": alice.device_id,
        "rvk": alice.root_verify_key.encode(),
        "answer": alice.signing_key.sign(sh.challenge),
    }
    sh.process_answer_req(packb(answer))
    with pytest.raises(HandshakeFailedChallenge):
        sh.build_result_req(bob.verify_key)


def test_build_result_req_bad_challenge(alice):
    sh = ServerHandshake()
    sh.build_challenge_req()
    answer = {
        "handshake": "answer",
        "type": "authenticated",
        "client_api_version": API_V1_VERSION,
        "organization_id": alice.organization_id,
        "device_id": alice.device_id,
        "rvk": alice.root_verify_key.encode(),
        "answer": alice.signing_key.sign(sh.challenge + b"-dummy"),
    }
    sh.process_answer_req(packb(answer))
    with pytest.raises(HandshakeFailedChallenge):
        sh.build_result_req(alice.verify_key)


@pytest.mark.parametrize(
    "method,expected_result",
    [
        ("build_bad_protocol_result_req", "bad_protocol"),
        ("build_bad_identity_result_req", "bad_identity"),
        ("build_organization_expired_result_req", "organization_expired"),
        ("build_rvk_mismatch_result_req", "rvk_mismatch"),
        ("build_revoked_device_result_req", "revoked_device"),
        ("build_bad_administration_token_result_req", "bad_admin_token"),
    ],
)
def test_build_bad_outcomes(alice, method, expected_result):
    sh = ServerHandshake()
    sh.build_challenge_req()
    answer = {
        "handshake": "answer",
        "type": "authenticated",
        "client_api_version": API_V1_VERSION,
        "organization_id": alice.organization_id,
        "device_id": alice.device_id,
        "rvk": alice.root_verify_key.encode(),
        "answer": alice.signing_key.sign(sh.challenge),
    }
    sh.process_answer_req(packb(answer))
    req = getattr(sh, method)()
    assert unpackb(req) == {"handshake": "result", "result": expected_result, "help": ANY}


# 5) Client process result


@pytest.mark.parametrize(
    "req",
    [
        {},
        {"handshake": "foo", "result": "ok"},
        {"result": "ok"},
        {"handshake": "result", "result": "error"},
    ],
)
def test_process_result_req_bad_format(req):
    ch = BaseClientHandshake()
    with pytest.raises(InvalidMessageError):
        ch.process_result_req(packb(req))


@pytest.mark.parametrize(
    "result,exc_cls",
    [
        ("bad_identity", HandshakeBadIdentity),
        ("organization_expired", HandshakeOrganizationExpired),
        ("rvk_mismatch", HandshakeRVKMismatch),
        ("revoked_device", HandshakeRevokedDevice),
        ("bad_admin_token", HandshakeBadAdministrationToken),
        ("dummy", InvalidMessageError),
    ],
)
def test_process_result_req_bad_outcome(result, exc_cls):
    ch = BaseClientHandshake()
    with pytest.raises(exc_cls):
        ch.process_result_req(packb({"handshake": "result", "result": result}))


# TODO: test with revoked device
# TODO: test with user with all devices revoked
