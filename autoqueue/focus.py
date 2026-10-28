"""Bounded foreground activation, kept independent of ctypes for regression tests."""
import time

from .engine import SafetyStop


def request_foreground(api, handle):
    """Temporarily share input queues; always release each successful attachment."""
    current = api.thread_id()
    others = dict.fromkeys((api.window_thread(api.foreground()), api.window_thread(handle)))
    attached = []
    try:
        for thread in others:
            if thread and thread != current and api.attach(current, thread, True):
                attached.append(thread)
        api.bring_to_top(handle)
        api.set_foreground(handle)
    finally:
        for thread in reversed(attached):
            api.attach(current, thread, False)


def activate(api, handle, allowed=lambda: True, sleep=time.sleep):
    """Request focus, wait for Windows, then use a safe title-bar click if needed.

    A title-bar activation never substitutes for the intended game click. The
    caller must take a fresh screenshot and authorize that separate action.
    """
    def check_running():
        if not allowed():
            raise SafetyStop("Input stopped.")

    def wait_for_focus():
        for _ in range(10):
            check_running()
            if api.foreground() == handle:
                return True
            sleep(.02)
        return False

    check_running()
    if api.foreground() == handle:
        return
    request_foreground(api, handle)
    if wait_for_focus():
        return
    point = api.activation_point(handle)
    if point is not None:
        check_running()
        api.click_caption(handle, point)
        if wait_for_focus():
            return
    raise SafetyStop(
        "Could not activate BlueStacks automatically. Keep its title bar visible "
        "and run BlueStacks and Autoqueue at the same Windows permission level."
    )
