"""Qt utilities shared across panels.

`BasePanel` provides a Tk-compatibility `after()` shim so existing
threading patterns (`self.after(0, lambda: ...)`) work unchanged when
called from background threads.
"""
from typing import Callable
import threading

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QMessageBox


class BasePanel(QWidget):
    """QWidget with a thread-safe `after()` helper.

    Emitting a pyqtSignal from a worker thread is the canonical Qt way
    to hop back to the UI thread; this signal carries a no-arg callable
    so existing call-sites that use ``self.after(0, lambda: ...)`` work
    without modification.
    """

    _run_in_ui = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._run_in_ui.connect(self._invoke, Qt.ConnectionType.QueuedConnection)

    def _invoke(self, fn: Callable):
        try:
            fn()
        except Exception:
            import traceback
            traceback.print_exc()

    def after(self, _delay_ms: int, fn: Callable, *args, **kwargs):
        """Schedule ``fn(*args, **kwargs)`` on the UI thread.

        Delay is ignored (always 0). Callable form mirrors ``Tk.after``.
        """
        if args or kwargs:
            self._run_in_ui.emit(lambda: fn(*args, **kwargs))
        else:
            self._run_in_ui.emit(fn)


def run_thread(fn: Callable, *args, **kwargs) -> threading.Thread:
    """Start a daemon thread running ``fn(*args, **kwargs)``.

    Replaces the boilerplate ``threading.Thread(..., daemon=True).start()``
    used pervasively across the old panels.
    """
    t = threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True)
    t.start()
    return t


class CancelToken:
    """Cooperative cancellation flag shared between UI and worker thread.

    Workers must poll ``token.cancelled`` at safe interruption points
    (e.g. between module iterations, between bus broadcasts). Python's
    threading model can't forcibly stop a thread mid-syscall — the
    worst-case latency is one outstanding adapter read (≈1.5 s on
    ELM-class hardware). The UI side calls ``token.cancel()`` when the
    user clicks Cancel.
    """

    def __init__(self):
        self._evt = threading.Event()

    def cancel(self) -> None:
        self._evt.set()

    def reset(self) -> None:
        self._evt.clear()

    @property
    def cancelled(self) -> bool:
        return self._evt.is_set()


def warn(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.warning(parent, title, text)


def info(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.information(parent, title, text)


def error(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.critical(parent, title, text)


def confirm(parent: QWidget, title: str, text: str, *, icon=QMessageBox.Icon.Question) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(icon)
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.setDefaultButton(QMessageBox.StandardButton.No)
    return box.exec() == QMessageBox.StandardButton.Yes
