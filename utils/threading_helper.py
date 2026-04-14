"""
threading_helper.py — Thread-safe background task runner for Kivy.

All heavy operations (compression, conversion, AI) run on background threads.
UI updates are dispatched back to the main thread via Clock.schedule_once.
"""

import threading
import traceback
from kivy.clock import Clock
from kivy.logger import Logger


class BackgroundTask:
    """
    Runs a function on a background thread with progress, success, and error callbacks.
    All callbacks are dispatched to the Kivy main thread automatically.

    Usage:
        def do_work(on_progress):
            for i in range(100):
                on_progress(i, f"Processing {i}%...")
            return "result_path.pdf"

        task = BackgroundTask(
            target=do_work,
            on_progress=lambda p, msg: update_ui(p, msg),
            on_complete=lambda result: show_success(result),
            on_error=lambda e: show_error(e),
        )
        task.start()
    """

    def __init__(self, target, on_progress=None, on_complete=None, on_error=None):
        """
        Args:
            target: callable(on_progress) -> result. The heavy work function.
                    It receives an on_progress(percent, message) callback.
            on_progress: callable(percent: int, message: str) — UI update.
            on_complete: callable(result) — called on success with return value.
            on_error: callable(error_message: str) — called on failure.
        """
        self.target = target
        self._on_progress = on_progress
        self._on_complete = on_complete
        self._on_error = on_error
        self._thread = None
        self._cancelled = False

    def start(self):
        """Start the background task."""
        self._cancelled = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def cancel(self):
        """Request cancellation. The target function should check is_cancelled."""
        self._cancelled = True

    @property
    def is_cancelled(self):
        return self._cancelled

    @property
    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def _run(self):
        """Internal thread runner."""
        try:
            def progress_callback(percent, message=""):
                if self._cancelled:
                    return
                if self._on_progress:
                    Clock.schedule_once(
                        lambda dt, p=percent, m=message: self._on_progress(p, m), 0
                    )

            result = self.target(progress_callback)

            if not self._cancelled and self._on_complete:
                Clock.schedule_once(
                    lambda dt, r=result: self._on_complete(r), 0
                )
        except Exception as e:
            error_msg = str(e)
            Logger.error(f"BackgroundTask: {error_msg}")
            Logger.error(traceback.format_exc())
            if not self._cancelled and self._on_error:
                Clock.schedule_once(
                    lambda dt, m=error_msg: self._on_error(m), 0
                )


class TaskLock:
    """
    Prevents duplicate task execution. 
    Use to disable buttons while a task is running.
    """

    def __init__(self):
        self._locked = False

    @property
    def is_locked(self):
        return self._locked

    def acquire(self):
        if self._locked:
            return False
        self._locked = True
        return True

    def release(self):
        self._locked = False
