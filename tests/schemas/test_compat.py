# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import json
import importlib_resources

import tests.schemas
from tests.schemas.builder import generate_api_data_specs, generate_client_data_specs


def test_api_data_compat():
    specs = json.loads(importlib_resources.read_text(tests.schemas, "api_data.json"))
    assert generate_api_data_specs() == specs


def test_client_data_compat():
    specs = json.loads(importlib_resources.read_text(tests.schemas, "client_data.json"))
    assert generate_client_data_specs() == specs
