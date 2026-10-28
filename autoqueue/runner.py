"""Background OCR and guarded input. The GUI stays responsive during inference."""
import copy
import threading
import time

from .engine import Engine, SafetyStop
from .vision import Recognizer


class Control:
    def __init__(self):
        self.lock = threading.RLock()
        self.running = threading.Event()
        self.running.set()
        self.stopped = threading.Event()
        self.paused_at = None
        self.paused_total = 0.0

    def active(self):
        return self.running.is_set() and not self.stopped.is_set()

    def now(self):
        with self.lock:
            clock = self.paused_at if self.paused_at is not None else time.monotonic()
            return clock - self.paused_total

    def pause(self):
        with self.lock:
            if self.paused_at is None:
                self.paused_at = time.monotonic()
            self.running.clear()

    def resume(self):
        with self.lock:
            if self.paused_at is not None:
                self.paused_total += time.monotonic() - self.paused_at
                self.paused_at = None
            self.running.set()

    def stop(self):
        with self.lock:
            self.stopped.set()
            self.running.set()  # Wake a paused worker so it can exit.


class Runner(threading.Thread):
    def __init__(self, targets, events, recognizer_factory=Recognizer):
        super().__init__(daemon=True)
        self.targets = targets
        self.events = events
        self.control = Control()
        self.recognizer_factory = recognizer_factory
        self.engine = Engine()
        self.sizes = {}

    def send(self, kind, text):
        self.events.put((kind, text))

    def observe(self, role):
        window = self.targets[role]
        image = window.capture()
        size = tuple(image.size)
        if role in self.sizes and size != self.sizes[role]:
            raise SafetyStop("Window resized. Stop and Start to use its new size.")
        self.sizes[role] = size
        return self.recognizer.inspect(image)

    def run(self):
        self.send("log", "Loading the built-in OCR engine...")
        try:
            self.recognizer = self.recognizer_factory()
        except Exception as error:
            self.control.stop()
            self.send("error", f"OCR could not load: {error}. Run setup.bat again.")
            return
        self.send("log", "OCR ready. Waiting for the game screens.")
        while not self.control.stopped.is_set():
            if not self.control.running.wait(.1):
                continue
            if self.control.stopped.is_set():
                break
            try:
                views = {role: self.observe(role) for role in ("leader", "member")}
                if not self.control.active():
                    continue
                summary = "; ".join(f"{r}: {v.state}" + (f" ({v.detail})" if v.detail else "")
                                    for r, v in views.items())
                self.send("status", f"{self.engine.runs} cycles completed · {summary}")
                planned = copy.deepcopy(self.engine)
                decision_time = self.control.now()
                action = planned.step(views, decision_time)
                if action is None:
                    self.engine = planned
                else:
                    # Activate first: Windows may need a title-bar click before
                    # it will focus another process. Read again after that, so
                    # a focus click can never double as a stale game action.
                    self.targets[action.role].focus(allowed=self.control.active)
                    if not self.control.active():
                        continue
                    fresh = self.observe(action.role)
                    if not self.control.active():
                        continue
                    point = action_point(action, fresh, all_liked=len(planned.liked[action.role]) == 3)
                    if point is None:
                        continue  # A changed/unreadable screen never authorizes input.
                    with self.control.lock:
                        if not self.control.active():
                            continue
                        sent = self.targets[action.role].click(
                            point, allowed=self.control.active,
                            expected_size=self.sizes[action.role])
                        if sent is False:
                            continue
                        clicked_at = self.control.now()
                        planned.next_click = clicked_at + .6
                        if action.kind == "accept":
                            planned.last_accept = clicked_at
                        if planned.pending:
                            pending_action, deadline = planned.pending
                            planned.pending = pending_action, deadline + clicked_at - decision_time
                        self.engine = planned
                    self.send("log", f"{action.role}: {action.kind}")
            except Exception as error:
                if not self.control.stopped.is_set():
                    self.control.pause()
                    self.send("paused", str(error))
            self.control.stopped.wait(.15)


def action_point(action, view, all_liked=False):
    expected = {"dungeon": "world", "match": "menu", "accept": "accept",
                "like": "results", "return": "results"}[action.kind]
    if view.state != expected:
        return None
    if action.kind == "like":
        if not view.likes_ready:
            return None
        return next((p for p in view.likes if Engine.near(action.point, p)), None)
    if action.kind == "return" and (view.likes or not (view.likes_ready or all_liked)):
        return None
    return view.targets.get(action.kind)
