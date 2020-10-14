# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS


AUTHENTICATED_CMDS = {
    "events_subscribe",
    "events_listen",
    "ping",  # TODO: remove ping and ping event (only have them in tests)
    # Message
    "message_get",
    # User&Device
    "user_get",
    "user_create",
    "user_revoke",
    "device_create",
    # Human
    "human_find",
    # Invitation
    "invite_new",
    "invite_delete",
    "invite_list",
    "invite_1_greeter_wait_peer",
    "invite_2a_greeter_get_hashed_nonce",
    "invite_2b_greeter_send_nonce",
    "invite_3a_greeter_wait_peer_trust",
    "invite_3b_greeter_signify_trust",
    "invite_4_greeter_communicate",
    # Block
    "block_create",
    "block_read",
    # Vlob
    "vlob_poll_changes",
    "vlob_create",
    "vlob_read",
    "vlob_update",
    "vlob_list_versions",
    "vlob_maintenance_get_reencryption_batch",
    "vlob_maintenance_save_reencryption_batch",
    # Realm
    "realm_create",
    "realm_status",
    "realm_get_role_certificates",
    "realm_update_roles",
    "realm_start_reencryption_maintenance",
    "realm_finish_reencryption_maintenance",
    # Organization
    "organization_stats",
}

INVITED_CMDS = {
    "ping",  # TODO: remove ping and ping event (only have them in tests)
    "invite_info",
    "invite_1_claimer_wait_peer",
    "invite_2a_claimer_send_hashed_nonce",
    "invite_2b_claimer_send_nonce",
    "invite_3a_claimer_signify_trust",
    "invite_3b_claimer_wait_peer_trust",
    "invite_4_claimer_communicate",
}

APIV1_ANONYMOUS_CMDS = {
    "organization_bootstrap",
    "ping",
}

# TODO: replace administration cmds by a dedicated HTTP REST API
APIV1_ADMINISTRATION_CMDS = {
    "organization_create",
    "organization_stats",
    "organization_status",
    "organization_update",
    "ping",
}
