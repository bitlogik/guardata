# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2020 Scille SAS

from guardata.client.types import WorkspaceRole
from guardata.client.gui.lang import translate as _


NOT_SHARED_KEY = "NOT_SHARED"


def get_role_translation(user_role):
    ROLES_TRANSLATIONS = {
        WorkspaceRole.READER: _("TEXT_WORKSPACE_ROLE_READER"),
        WorkspaceRole.CONTRIBUTOR: _("TEXT_WORKSPACE_ROLE_CONTRIBUTOR"),
        WorkspaceRole.MANAGER: _("TEXT_WORKSPACE_ROLE_MANAGER"),
        WorkspaceRole.OWNER: _("TEXT_WORKSPACE_ROLE_OWNER"),
        NOT_SHARED_KEY: _("TEXT_WORKSPACE_ROLE_NOT_SHARED"),
    }
    return ROLES_TRANSLATIONS[user_role]
