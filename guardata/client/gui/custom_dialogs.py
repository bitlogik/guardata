# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS
# Copyright 2020 BitLogiK for guardata (https://guardata.app) - AGPLv3

import platform

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QWidget, QCompleter, QDialog, QStyleOption, QStyle, QSizePolicy

from structlog import get_logger

from guardata.client.gui.lang import translate as _
from guardata.client.gui import desktop
from guardata.client.gui.custom_widgets import Button
from guardata.client.gui.guardata_application import guardataApp

from guardata.client.gui.ui.error_widget import Ui_ErrorWidget
from guardata.client.gui.ui.info_widget import Ui_InfoWidget
from guardata.client.gui.ui.question_widget import Ui_QuestionWidget
from guardata.client.gui.ui.input_widget import Ui_InputWidget
from guardata.client.gui.ui.greyed_dialog import Ui_GreyedDialog


logger = get_logger()


class GreyedDialog(QDialog, Ui_GreyedDialog):
    closing = pyqtSignal(QDialog.DialogCode)

    def __init__(self, center_widget, title, parent, hide_close=False, width=None, is_modal=False):
        super().__init__(parent)
        self.setupUi(self)
        self.setModal(True)
        self.setObjectName("GreyedDialog")
        self.setWindowModality(Qt.ApplicationModal)
        self.button_close.apply_style()
        if platform.system() == "Windows" or platform.system() == "Darwin":
            # SplashScreen on Windows freezes the Window
            self.setWindowFlags(Qt.FramelessWindowHint)
        else:
            # FramelessWindowHint on Linux (at least xfce) is less pretty
            self.setWindowFlags(Qt.SplashScreen)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.center_widget = center_widget
        self.main_layout.addWidget(center_widget)
        self.center_widget.show()
        if not title and hide_close:
            self.widget_title.hide()
        if title:
            self.label_title.setText(title)
        if hide_close:
            self.button_close.hide()
        main_win = guardataApp.get_main_window()
        if width:
            if width < main_win.size().width():
                spacing = int((main_win.size().width() - width) / 2)
                self._get_spacer_right().changeSize(
                    spacing, 0, QSizePolicy.Preferred, QSizePolicy.Preferred
                )
                self._get_spacer_left().changeSize(
                    spacing, 0, QSizePolicy.Preferred, QSizePolicy.Preferred
                )
        if main_win:
            if main_win.isVisible():
                if (not is_modal) or platform.system() == "Windows":
                    self.setParent(main_win)
                self.resize(main_win.size())
            else:
                main_win.show_top()
            self.move(0, 0)
        else:
            logger.error("GreyedDialog did not find the main window, this is probably a bug")
        self.setFocus()
        self.accepted.connect(self.on_finished)
        self.rejected.connect(self.on_finished)

    def _get_spacer_top(self):
        return self.vertical_layout.itemAt(0).spacerItem()

    def _get_spacer_bottom(self):
        return self.vertical_layout.itemAt(2).spacerItem()

    def _get_spacer_left(self):
        return self.horizontal_layout.itemAt(0).spacerItem()

    def _get_spacer_right(self):
        return self.horizontal_layout.itemAt(2).spacerItem()

    def paintEvent(self, event):
        opt = QStyleOption()
        opt.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PE_Widget, opt, p, self)

    def on_finished(self):
        self.closing.emit(self.result())
        self.hide()


class TextInputWidget(QWidget, Ui_InputWidget):
    finished = pyqtSignal(QDialog.DialogCode, str)
    accepted = pyqtSignal()

    def __init__(
        self,
        message,
        placeholder="",
        default_text="",
        completion=None,
        button_text=None,
        validator=None,
    ):
        super().__init__()
        self.setupUi(self)
        button_text = button_text or _("ACTION_OK")
        self.button_ok.setText(button_text)
        self.label_message.setText(message)
        self.line_edit_text.setPlaceholderText(placeholder)
        self.line_edit_text.setText(default_text)
        if validator:
            self.line_edit_text.setValidator(validator)
        if completion:
            completer = QCompleter(completion)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.popup().setStyleSheet("border: 1px solid rgb(30, 78, 162);")
            self.line_edit_text.setCompleter(completer)
        self.button_ok.clicked.connect(self._on_button_clicked)
        self.setFocus()
        self.line_edit_text.setFocus()

    @property
    def text(self):
        return self.line_edit_text.text()

    def on_closing(self, return_code):
        self.finished.emit(return_code, self.text)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._on_button_clicked()
        event.accept()

    def _on_button_clicked(self):
        self.accepted.emit()


def get_text_input(
    parent,
    title,
    message,
    on_finished,
    placeholder="",
    default_text="",
    completion=None,
    button_text=None,
    validator=None,
):
    w = TextInputWidget(
        message=message,
        placeholder=placeholder,
        default_text=default_text,
        completion=completion,
        button_text=button_text,
        validator=validator,
    )
    d = GreyedDialog(w, title=title, parent=parent)
    d.closing.connect(w.on_closing)
    w.accepted.connect(d.accept)
    w.line_edit_text.setFocus()
    w.finished.connect(on_finished)
    d.show()


class QuestionWidget(QWidget, Ui_QuestionWidget):
    finished = pyqtSignal(QDialog.DialogCode, str)
    accepted = pyqtSignal()

    def __init__(self, message, button_texts, radio_mode=False):
        super().__init__()
        self.setupUi(self)
        self.status = None
        self.label_message.setText(message)
        for text in button_texts:
            b = Button(text)
            b.clicked_self.connect(self._on_button_clicked)
            b.setCursor(Qt.PointingHandCursor)
            if radio_mode:
                self.layout_radios.addWidget(b)
            else:
                self.layout_buttons.insertWidget(1, b)

    def on_closing(self, return_code):
        self.finished.emit(return_code, self.status)

    def _on_button_clicked(self, button):
        self.status = button.text()
        self.accepted.emit()


def ask_question(parent, title, message, button_texts, on_finished, radio_mode=False):
    w = QuestionWidget(message=message, button_texts=button_texts, radio_mode=radio_mode)
    d = GreyedDialog(w, title=title, parent=parent)
    d.closing.connect(w.on_closing)
    w.accepted.connect(d.accept)
    w.finished.connect(on_finished)
    d.show()


class ErrorWidget(QWidget, Ui_ErrorWidget):
    def __init__(self, message, exception=None):
        super().__init__()
        self.setupUi(self)
        self.label_message.setText(message)
        self.label_message.setOpenExternalLinks(True)
        self.label_icon.apply_style()
        self.text_details.hide()
        if not exception:
            self.button_details.hide()
        else:
            import traceback

            stack = traceback.format_exception(None, exception, None)
            if not stack:
                self.button_details.hide()
            else:
                except_text = "<b>{}</b><br /><br />{}".format(
                    str(exception).replace("\n", "<br />"), "<br />".join(stack)
                )
                except_text = except_text.replace("\n", "<br />")
                self.text_details.setHtml(except_text)
        self.button_details.clicked.connect(self.toggle_details)
        self.button_details.apply_style()
        self.button_copy.clicked.connect(self.copy_to_clipboard)
        self.button_copy.hide()
        self.button_copy.apply_style()

    def copy_to_clipboard(self):
        desktop.copy_to_clipboard(self.text_details.toPlainText())

    def toggle_details(self, checked):
        if not checked:
            self.text_details.hide()
            self.button_copy.hide()
        else:
            self.text_details.show()
            self.button_copy.show()


def show_error(parent, message, exception=None):
    w = ErrorWidget(message, exception)
    d = GreyedDialog(w, title=_("TEXT_ERR_DIALOG_TITLE"), parent=parent, is_modal=True)
    d.open()


class InfoWidget(QWidget, Ui_InfoWidget):
    accepted = pyqtSignal()

    def __init__(self, message, button_text=None):
        super().__init__()
        self.setupUi(self)
        self.label_message.setText(message)
        self.label_icon.apply_style()
        self.button_ok.setText(_("ACTION_CONTINUE") or button_text)
        self.button_ok.clicked.connect(self._on_button_clicked)
        self.button_ok.setFocus()

    def _on_button_clicked(self, button):
        self.accepted.emit()


def show_info(parent, message, button_text=None):
    w = InfoWidget(message, button_text)
    d = GreyedDialog(w, title=None, parent=parent, hide_close=True, is_modal=True)
    w.accepted.connect(d.accept)
    w.button_ok.setFocus()
    d.open()
