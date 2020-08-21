# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

from PyQt5.QtGui import QValidator, QIntValidator

from guardata.api.protocol import OrganizationID, UserID, DeviceName, DeviceID
from guardata.client.types import (
    BackendAddr,
    BackendOrganizationAddr,
    BackendOrganizationBootstrapAddr,
    BackendOrganizationClaimUserAddr,
    BackendOrganizationClaimDeviceAddr,
)


class NetworkPortValidator(QIntValidator):
    def __init__(self):
        super().__init__(1, 65536)


class OrganizationIDValidator(QValidator):
    def validate(self, string, pos):
        try:
            if len(string) == 0:
                return QValidator.Intermediate, string, pos
            OrganizationID(string)
            return QValidator.Acceptable, string, pos
        except ValueError:
            return QValidator.Invalid, string, pos


class BackendAddrValidator(QValidator):
    def validate(self, string, pos):
        try:
            if len(string) == 0:
                return QValidator.Intermediate, string, pos
            BackendAddr.from_url(string)
            return QValidator.Acceptable, string, pos
        except ValueError:
            if pos > 3:
                return QValidator.Invalid, string, pos
            return QValidator.Intermediate, string, pos


class BackendOrganizationAddrValidator(QValidator):
    def validate(self, string, pos):
        try:
            if len(string) == 0:
                return QValidator.Intermediate, string, pos
            BackendOrganizationAddr.from_url(string)
            return QValidator.Acceptable, string, pos
        except ValueError:
            return QValidator.Intermediate, string, pos


class BackendOrganizationBootstrapAddrValidator(QValidator):
    def validate(self, string, pos):
        try:
            if len(string) == 0:
                return QValidator.Intermediate, string, pos
            BackendOrganizationBootstrapAddr.from_url(string)
            return QValidator.Acceptable, string, pos
        except ValueError:
            return QValidator.Intermediate, string, pos


class BackendOrganizationClaimUserAddrValidator(QValidator):
    def validate(self, string, pos):
        try:
            if len(string) == 0:
                return QValidator.Intermediate, string, pos
            BackendOrganizationClaimUserAddr.from_url(string)
            return QValidator.Acceptable, string, pos
        except ValueError:
            return QValidator.Intermediate, string, pos


class BackendOrganizationClaimDeviceAddrValidator(QValidator):
    def validate(self, string, pos):
        try:
            if len(string) == 0:
                return QValidator.Intermediate, string, pos
            BackendOrganizationClaimDeviceAddr.from_url(string)
            return QValidator.Acceptable, string, pos
        except ValueError:
            return QValidator.Intermediate, string, pos


class UserIDValidator(QValidator):
    def validate(self, string, pos):
        try:
            if len(string) == 0:
                return QValidator.Intermediate, string, pos
            UserID(string)
            return QValidator.Acceptable, string, pos
        except ValueError:
            return QValidator.Invalid, string, pos


class DeviceNameValidator(QValidator):
    def validate(self, string, pos):
        try:
            if len(string) == 0:
                return QValidator.Intermediate, string, pos
            DeviceName(string)
            return QValidator.Acceptable, string, pos
        except ValueError:
            return QValidator.Invalid, string, pos


class DeviceIDValidator(QValidator):
    def validate(self, string, pos):
        try:
            if len(string) == 0:
                return QValidator.Intermediate, string, pos
            DeviceID(string)
            return QValidator.Acceptable, string, pos
        except ValueError:
            return QValidator.Invalid, string, pos
