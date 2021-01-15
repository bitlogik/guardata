# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3
# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import os
import attr
import json
from typing import Optional, FrozenSet
from pathlib import Path
import binascii
import base64
from structlog import get_logger

from guardata.api.data import EntryID


logger = get_logger()


def get_default_data_base_dir(environ: dict) -> Path:
    if os.name == "nt":
        return Path(environ["LOCALAPPDATA"]) / "guardata/data"
    else:
        path = environ.get("XDG_DATA_HOME")
        if not path:
            path = f"{environ['HOME']}/.local/share"
        return Path(path) / "guardata"


def get_default_cache_base_dir(environ: dict) -> Path:
    if os.name == "nt":
        return Path(environ["LOCALAPPDATA"]) / "guardata/cache"
    else:
        path = environ.get("XDG_CACHE_HOME")
        if not path:
            path = f"{environ.get('HOME')}/.cache"
        return Path(path) / "guardata"


def get_default_config_dir(environ: dict) -> Path:
    if os.name == "nt":
        return Path(environ["LOCALAPPDATA"]) / "guardata/config"
    else:
        path = environ.get("XDG_CONFIG_HOME")
        if not path:
            path = f"{environ.get('HOME')}/.config"
        return Path(path) / "guardata"


def get_default_mountpoint_base_dir(environ: dict) -> Path:
    return Path.home() / "guardata"


@attr.s(slots=True, frozen=True, auto_attribs=True)
class ClientConfig:
    config_dir: Path
    data_base_dir: Path
    cache_base_dir: Path
    mountpoint_base_dir: Path

    pattern_filter: Optional[str] = None  # if not None : overrides the path with this regex
    pattern_filter_path: Optional[Path] = None  # default path or failsafe pattern

    debug: bool = False

    backend_max_cooldown: int = 30
    backend_connection_keepalive: Optional[int] = 29
    backend_max_connections: int = 4

    invitation_token_size: int = 8

    mountpoint_enabled: bool = False
    disabled_workspaces: FrozenSet[EntryID] = frozenset()

    gui_last_device: Optional[str] = None
    gui_tray_enabled: bool = True
    gui_language: Optional[str] = None
    gui_first_launch: bool = True
    gui_last_version: Optional[str] = None
    gui_check_version_at_startup: bool = True
    gui_check_version_url: str = "https://dl.guardata.app/latest"
    gui_check_version_allow_pre_release: bool = False
    gui_confirmation_before_close: bool = True
    gui_workspace_color: bool = False
    gui_allow_multiple_instances: bool = False
    gui_show_confined: bool = False
    gui_geometry: bytes = None

    ipc_socket_file: Path = None
    ipc_win32_mutex_name: str = "guardata"

    def evolve(self, **kwargs):
        return attr.evolve(self, **kwargs)


def config_factory(
    config_dir: Path = None,
    data_base_dir: Path = None,
    cache_base_dir: Path = None,
    mountpoint_base_dir: Path = None,
    pattern_filter: Optional[str] = None,
    pattern_filter_path: Optional[str] = None,
    mountpoint_enabled: bool = False,
    disabled_workspaces: FrozenSet[EntryID] = frozenset(),
    backend_max_cooldown: int = 30,
    backend_connection_keepalive: Optional[int] = 29,
    backend_max_connections: int = 4,
    debug: bool = False,
    gui_last_device: str = None,
    gui_tray_enabled: bool = True,
    gui_language: str = None,
    gui_first_launch: bool = True,
    gui_last_version: str = None,
    gui_check_version_at_startup: bool = True,
    gui_check_version_allow_pre_release: bool = False,
    gui_workspace_color: bool = False,
    gui_allow_multiple_instances: bool = False,
    gui_show_confined: bool = False,
    gui_geometry: bytes = None,
    environ: dict = {},
    **_,
) -> ClientConfig:
    data_base_dir = data_base_dir or get_default_data_base_dir(environ)
    client_config = ClientConfig(
        config_dir=config_dir or get_default_config_dir(environ),
        data_base_dir=data_base_dir,
        cache_base_dir=cache_base_dir or get_default_cache_base_dir(environ),
        mountpoint_base_dir=get_default_mountpoint_base_dir(environ),
        pattern_filter=pattern_filter,
        mountpoint_enabled=mountpoint_enabled,
        disabled_workspaces=disabled_workspaces,
        backend_max_cooldown=backend_max_cooldown,
        backend_connection_keepalive=backend_connection_keepalive,
        backend_max_connections=backend_max_connections,
        debug=debug,
        gui_last_device=gui_last_device,
        gui_tray_enabled=gui_tray_enabled,
        gui_language=gui_language,
        gui_first_launch=gui_first_launch,
        gui_last_version=gui_last_version,
        gui_check_version_at_startup=gui_check_version_at_startup,
        gui_check_version_allow_pre_release=gui_check_version_allow_pre_release,
        gui_workspace_color=gui_workspace_color,
        gui_allow_multiple_instances=gui_allow_multiple_instances,
        gui_show_confined=gui_show_confined,
        gui_geometry=gui_geometry,
        ipc_socket_file=data_base_dir / "guardata.lock",
        ipc_win32_mutex_name="guardata",
    )

    # Make sure the directories exist on the system
    client_config.config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    client_config.data_base_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    client_config.cache_base_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    # Mountpoint base directory is not used on windows
    if os.name != "nt":
        client_config.mountpoint_base_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    return client_config


def load_config(config_dir: Path, **extra_config) -> ClientConfig:

    config_file = config_dir / "config.json"
    try:
        raw_conf = config_file.read_text()
        data_conf = json.loads(raw_conf)

    except OSError:
        # Config file not created yet, fallback to default
        data_conf = {}

    except (ValueError, json.JSONDecodeError) as exc:
        # Config file broken, fallback to default
        logger.warning(f"Ignoring invalid config in {config_file} ({exc})")
        data_conf = {}

    try:
        data_conf["data_base_dir"] = Path(data_conf["data_base_dir"])
    except (KeyError, ValueError):
        pass

    try:
        data_conf["cache_base_dir"] = Path(data_conf["cache_base_dir"])
    except (KeyError, ValueError):
        pass

    try:
        data_conf["disabled_workspaces"] = frozenset(map(EntryID, data_conf["disabled_workspaces"]))
    except (KeyError, ValueError):
        pass

    try:
        data_conf["gui_geometry"] = base64.b64decode(data_conf["gui_geometry"].encode("ascii"))
    except (AttributeError, KeyError, UnicodeEncodeError, binascii.Error):
        data_conf["gui_geometry"] = None

    if data_conf.get("gui_last_version"):
        data_conf["gui_last_version"] = data_conf["gui_last_version"].lstrip("v")

    return config_factory(config_dir=config_dir, **data_conf, **extra_config, environ=os.environ)


def reload_config(config: ClientConfig) -> ClientConfig:
    return load_config(config.config_dir, debug=config.debug)


def save_config(config: ClientConfig):
    config_path = config.config_dir
    config_path.mkdir(mode=0o700, parents=True, exist_ok=True)
    config_path /= "config.json"
    config_path.touch(exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "data_base_dir": str(config.data_base_dir),
                "cache_base_dir": str(config.cache_base_dir),
                "pattern_filter": config.pattern_filter,
                "disabled_workspaces": list(map(str, config.disabled_workspaces)),
                "backend_max_cooldown": config.backend_max_cooldown,
                "backend_connection_keepalive": config.backend_connection_keepalive,
                "gui_last_device": config.gui_last_device,
                "gui_tray_enabled": config.gui_tray_enabled,
                "gui_language": config.gui_language,
                "gui_first_launch": config.gui_first_launch,
                "gui_last_version": config.gui_last_version,
                "gui_check_version_at_startup": config.gui_check_version_at_startup,
                "gui_check_version_allow_pre_release": config.gui_check_version_allow_pre_release,
                "gui_workspace_color": config.gui_workspace_color,
                "gui_allow_multiple_instances": config.gui_allow_multiple_instances,
                "gui_show_confined": config.gui_show_confined,
                "gui_geometry": base64.b64encode(config.gui_geometry).decode("ascii")
                if config.gui_geometry
                else None,
            },
            indent=True,
        )
    )
