"""Windows-only desktop adapter. No ADB or game process access."""
import ctypes as C
import queue
import threading
from ctypes import wintypes as W
from dataclasses import dataclass

from PIL import ImageGrab

from .engine import SafetyStop
from .focus import activate

user32 = C.WinDLL("user32", use_last_error=True)
user32.GetForegroundWindow.restype = W.HWND
user32.GetAncestor.argtypes = [W.HWND, W.UINT]
user32.GetAncestor.restype = W.HWND
user32.WindowFromPoint.argtypes = [W.POINT]
user32.WindowFromPoint.restype = W.HWND
user32.GetClientRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
user32.ClientToScreen.argtypes = [W.HWND, C.POINTER(W.POINT)]
user32.GetWindowTextLengthW.argtypes = [W.HWND]
user32.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
user32.IsWindowVisible.argtypes = [W.HWND]
user32.IsIconic.argtypes = [W.HWND]
user32.IsWindow.argtypes = [W.HWND]
user32.SetForegroundWindow.argtypes = [W.HWND]
user32.BringWindowToTop.argtypes = [W.HWND]
user32.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
user32.GetWindowThreadProcessId.restype = W.DWORD
user32.AttachThreadInput.argtypes = [W.DWORD, W.DWORD, W.BOOL]
user32.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
user32.SendMessageTimeoutW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM,
                                     W.UINT, W.UINT, C.POINTER(C.c_size_t)]
user32.SendMessageTimeoutW.restype = C.c_ssize_t
kernel32 = C.WinDLL("kernel32", use_last_error=True)
kernel32.GetCurrentThreadId.restype = W.DWORD


class DesktopFocus:
    @staticmethod
    def foreground():
        handle = user32.GetForegroundWindow()
        return user32.GetAncestor(handle, 2) if handle else None

    @staticmethod
    def thread_id():
        # AttachThreadInput requires a message queue on the calling worker.
        message = W.MSG()
        user32.PeekMessageW(C.byref(message), None, 0, 0, 0)
        return kernel32.GetCurrentThreadId()

    @staticmethod
    def window_thread(handle):
        return user32.GetWindowThreadProcessId(handle, None) if handle else 0

    @staticmethod
    def attach(current, other, enabled):
        return bool(user32.AttachThreadInput(current, other, enabled))

    @staticmethod
    def bring_to_top(handle):
        user32.BringWindowToTop(handle)

    @staticmethod
    def set_foreground(handle):
        user32.SetForegroundWindow(handle)

    @staticmethod
    def activation_point(handle):
        """Find visible draggable caption chrome, never a game-surface point."""
        rect = W.RECT()
        if not user32.GetWindowRect(handle, C.byref(rect)):
            return None
        title = C.create_unicode_buffer(user32.GetWindowTextLengthW(handle) + 1)
        user32.GetWindowTextW(handle, title, len(title))
        # BlueStacks uses custom chrome which can report HTCLIENT instead of
        # HTCAPTION. Its instance title occupies the first 28 pixels at the top,
        # between the logo and toolbar buttons, in the supplied player layout.
        bluestacks = "bluestacks app player" in title.value.lower()
        custom_caption = None
        width = rect.right - rect.left
        for dy in (14, 22, 8, 28):
            for dx in (min(100, int(width * .2)), int(width * .35)):
                x, y = rect.left + dx, rect.top + dy
                hit = user32.WindowFromPoint(W.POINT(x, y))
                if user32.GetAncestor(hit, 2) != handle:
                    continue
                result = C.c_size_t()
                packed = (x & 0xffff) | ((y & 0xffff) << 16)
                if not user32.SendMessageTimeoutW(handle, 0x0084, 0, packed, 2, 20, C.byref(result)):
                    continue
                if result.value == 2:  # HTCAPTION: safe native caption activation.
                    return x, y
                if bluestacks and result.value == 1 and dx <= 100 and dy <= 22:
                    custom_caption = custom_caption or (x, y)
        return custom_caption

    @staticmethod
    def click_caption(handle, point):
        import pyautogui
        # Confirm that the activation point is still part of the visible title
        # bar; another application may have moved or appeared during the wait.
        if DesktopFocus.activation_point(handle) != point:
            raise SafetyStop("Title bar changed during activation. Keep both game windows visible.")
        pyautogui.failSafeCheck()
        pyautogui.click(*point, _pause=False)


def enable_dpi_awareness():
    try:
        user32.SetProcessDpiAwarenessContext(C.c_void_p(-4))
    except AttributeError:
        user32.SetProcessDPIAware()


@dataclass
class Window:
    handle: int
    title: str

    def rect(self):
        if not user32.IsWindow(self.handle) or user32.IsIconic(self.handle):
            raise SafetyStop(f"{self.title}: window closed or minimized.")
        rect, point = W.RECT(), W.POINT(0, 0)
        if not user32.GetClientRect(self.handle, C.byref(rect)):
            raise SafetyStop("Cannot read window dimensions.")
        if not user32.ClientToScreen(self.handle, C.byref(point)):
            raise SafetyStop("Cannot locate window on screen.")
        return point.x, point.y, rect.right, rect.bottom

    def require_visible(self):
        x, y, width, height = self.rect()
        for fx, fy in ((.02, .02), (.98, .02), (.5, .5), (.02, .98), (.98, .98)):
            hit = user32.WindowFromPoint(W.POINT(x + int(width * fx), y + int(height * fy)))
            if user32.GetAncestor(hit, 2) != self.handle:
                raise SafetyStop(f"{self.title}: another window covers the game. Keep both visible.")
        return x, y, width, height

    def capture(self):
        x, y, w, h = self.require_visible()
        image = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).convert("RGB")
        if self.rect() != (x, y, w, h):
            raise SafetyStop("Window moved during a screen read. Resume once it is in place.")
        return image

    def focus(self, allowed=lambda: True):
        self.require_visible()
        activate(DesktopFocus(), self.handle, allowed)

    def click(self, point, allowed=lambda: True, expected_size=None):
        import pyautogui
        pyautogui.FAILSAFE = True
        pyautogui.failSafeCheck()
        x, y, w, h = self.require_visible()
        if expected_size and (w, h) != tuple(expected_size):
            raise SafetyStop("Window resized before input. Stop and Start to use its new size.")
        px, py = map(int, point)
        if not (0 <= px < w and 0 <= py < h):
            raise SafetyStop("Click is outside the game window.")
        if not allowed():
            raise SafetyStop("Input stopped.")
        if DesktopFocus.foreground() != self.handle:
            return False  # Focus changed after OCR. Let the runner read again.
        hit = user32.WindowFromPoint(W.POINT(x + px, y + py))
        if user32.GetAncestor(hit, 2) != self.handle:
            raise SafetyStop("Click target is covered by another window.")
        if not allowed():
            raise SafetyStop("Input stopped.")
        pyautogui.click(x + px, y + py, _pause=False)
        return True


def list_windows():
    result = []
    callback_type = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)

    @callback_type
    def visit(handle, _):
        length = user32.GetWindowTextLengthW(handle)
        if user32.IsWindowVisible(handle) and length:
            title = C.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(handle, title, length + 1)
            window = Window(handle, title.value)
            try:
                _, _, width, height = window.rect()
                if width >= 200 and height >= 300:
                    result.append(window)
            except SafetyStop:
                pass
        return True

    user32.EnumWindows.argtypes = [callback_type, W.LPARAM]
    user32.EnumWindows(visit, 0)
    return sorted(result, key=lambda w: ("bluestacks" not in w.title.lower(), w.title))


class Hotkeys:
    def __init__(self):
        # Tk has its own Windows message pump. Register on a dedicated thread
        # so Tk cannot consume/drop the WM_HOTKEY messages before we see them.
        self.events = queue.SimpleQueue()
        self.ready = threading.Event()
        self.error = None
        self.thread_id = None
        self.thread = threading.Thread(target=self.listen, daemon=True)
        self.thread.start()
        if not self.ready.wait(3):
            raise SafetyStop("Global hotkeys could not initialize.")
        if self.error:
            raise SafetyStop(self.error)

    def listen(self):
        kernel32 = C.WinDLL("kernel32")
        kernel32.GetCurrentThreadId.restype = W.DWORD
        self.thread_id = kernel32.GetCurrentThreadId()
        registered = []
        try:
            for identifier, key in ((81, 0x77), (82, 0x78)):  # F8, F9
                if not user32.RegisterHotKey(None, identifier, 0x4000, key):
                    self.error = "F8 or F9 is already in use. Close the other app and restart."
                    return
                registered.append(identifier)
            self.ready.set()
            msg = W.MSG()
            while user32.GetMessageW(C.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312:
                    self.events.put("toggle" if msg.wParam == 81 else "stop")
        finally:
            for identifier in registered:
                user32.UnregisterHotKey(None, identifier)
            self.ready.set()

    def poll(self):
        events = []
        while True:
            try:
                events.append(self.events.get_nowait())
            except queue.Empty:
                break
        return events

    def close(self):
        if self.thread_id:
            user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)
            self.thread.join(timeout=1)
