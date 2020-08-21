# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

from guardata.client.client_events import ClientEvent

import sys
import signal
from queue import Queue
from contextlib import contextmanager

import trio
from structlog import get_logger

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QApplication

from guardata.client.config import ClientConfig
from guardata.event_bus import EventBus
from guardata.client.ipcinterface import (
    run_ipc_server,
    send_to_ipc_server,
    IPCServerAlreadyRunning,
    IPCServerNotRunning,
    IPCCommand,
)

try:
    from guardata.client.gui import lang
    from guardata.client.gui.guardata_application import guardataApp
    from guardata.client.gui.new_version import CheckNewVersion
    from guardata.client.gui.systray import systray_available, Systray
    from guardata.client.gui.main_window import MainWindow
    from guardata.client.gui.trio_thread import ThreadSafeQtSignal, run_trio_thread
except ImportError as exc:
    raise ModuleNotFoundError(
        """PyQt forms haven't been generated.
You must install the guardata package or run `python setup.py generate_pyqt_forms`
"""
    ) from exc


logger = get_logger()


def before_quit(systray):
    def _before_quit():
        systray.hide()

    return _before_quit


async def _start_ipc_server(config, main_window, start_arg, result_queue):
    new_instance_needed_qt = ThreadSafeQtSignal(main_window, "new_instance_needed", object)
    foreground_needed_qt = ThreadSafeQtSignal(main_window, "foreground_needed")

    async def cmd_handler(cmd):
        if cmd["cmd"] == IPCCommand.FOREGROUND:
            foreground_needed_qt.emit()
        elif cmd["cmd"] == IPCCommand.NEW_INSTANCE:
            new_instance_needed_qt.emit(cmd.get("start_arg"))
        return {"status": "ok"}

    while True:
        try:
            async with run_ipc_server(
                cmd_handler, config.ipc_socket_file, win32_mutex_name=config.ipc_win32_mutex_name
            ):
                result_queue.put("started")
                await trio.sleep_forever()

        except IPCServerAlreadyRunning:
            # guardata is already started, give it our work then
            try:
                try:
                    if start_arg:
                        await send_to_ipc_server(
                            config.ipc_socket_file, IPCCommand.NEW_INSTANCE, start_arg=start_arg
                        )
                    else:
                        await send_to_ipc_server(config.ipc_socket_file, IPCCommand.FOREGROUND)
                finally:
                    result_queue.put("already_running")
                return

            except IPCServerNotRunning:
                # IPC server has closed, retry to create our own
                continue


@contextmanager
def fail_on_first_exception(kill_window):
    exceptions = []

    def excepthook(etype, exception, traceback):
        exceptions.append(exception)
        kill_window()
        return previous_hook(etype, exception, traceback)

    sys.excepthook, previous_hook = excepthook, sys.excepthook

    try:
        yield
    finally:
        sys.excepthook = previous_hook
        if exceptions:
            raise exceptions[0]


def run_gui(config: ClientConfig, start_arg: str = None, diagnose: bool = False):
    logger.info("Starting UI")

    # Needed for High DPI usage of QIcons, otherwise only QImages are well scaled
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = guardataApp()

    app.load_stylesheet()
    app.load_font()

    lang_key = lang.switch_language(config)

    event_bus = EventBus()
    with run_trio_thread() as jobs_ctx:
        win = MainWindow(
            jobs_ctx=jobs_ctx,
            event_bus=event_bus,
            config=config,
            minimize_on_close=config.gui_tray_enabled and systray_available(),
        )

        result_queue = Queue(maxsize=1)

        class ThreadSafeNoQtSignal(ThreadSafeQtSignal):
            def __init__(self):
                self.qobj = None
                self.signal_name = ""
                self.args_types = ()

            def emit(self, *args):
                pass

        jobs_ctx.submit_job(
            ThreadSafeNoQtSignal(),
            ThreadSafeNoQtSignal(),
            _start_ipc_server,
            config,
            win,
            start_arg,
            result_queue,
        )
        if result_queue.get() == "already_running":
            # Another instance of guardata already started, nothing more to do
            return

        if systray_available():
            systray = Systray(parent=win)
            win.systray_notification.connect(systray.on_systray_notification)
            systray.on_close.connect(win.close_app)
            systray.on_show.connect(win.show_top)
            app.aboutToQuit.connect(before_quit(systray))
            if config.gui_tray_enabled:
                app.setQuitOnLastWindowClosed(False)

        if config.gui_check_version_at_startup and not diagnose:
            CheckNewVersion(jobs_ctx=jobs_ctx, event_bus=event_bus, config=config, parent=win)

        win.showMaximized(skip_dialogs=diagnose, invitation_link=start_arg)
        win.show_top()
        win.new_instance_needed.emit(start_arg)

        def kill_window(*args):
            win.close_app(force=True)
            QApplication.quit()

        signal.signal(signal.SIGINT, kill_window)

        # QTimer wakes up the event loop periodically which allows us to close
        # the window even when it is in background.
        timer = QTimer()
        timer.start(1000 if diagnose else 400)
        timer.timeout.connect(kill_window if diagnose else lambda: None)

        if diagnose:
            diagnose_timer = QTimer()
            diagnose_timer.start(1000)
            diagnose_timer.timeout.connect(kill_window)

        if lang_key:
            event_bus.send(ClientEvent.GUI_CONFIG_CHANGED, gui_language=lang_key)

        if diagnose:
            with fail_on_first_exception(kill_window):
                return app.exec_()
        else:
            return app.exec_()
