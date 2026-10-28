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
        self.resume_generation = 0

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
                self.resume_generation += 1
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
        self.resume_generation = 0
        self.cleanup_progress = {}
        self.cleanup_sequences = {}

    def send(self, kind, text):
        self.events.put((kind, text))

    def observe(self, role):
        window = self.targets[role]
        image = window.capture()
        size = tuple(image.size)
        if role in self.sizes and size != self.sizes[role]:
            raise SafetyStop("Window resized. Stop and Start to use its new size.")
        self.sizes[role] = size
        view = self.recognizer.inspect(image, role=role)
        if view.state in {"world", "menu", "queue"}:
            self.cleanup_progress.pop(role, None)
            self.cleanup_sequences.pop(role, None)
        return view

    def cleanup(self, role, view):
        points = self.cleanup_sequences.get(role) or cleanup_points(view)
        if points is None:
            return False
        self.cleanup_sequences[role] = points
        index = self.cleanup_progress.get(role, 0)
        if index == 0:
            self.send("log", f"{role}: clicking {len(points) - 1} thumbs-up icons, then Exit.")
        while index < len(points):
            with self.control.lock:
                if not self.control.active():
                    return False
                sent = self.targets[role].click(points[index], allowed=self.control.active,
                                                expected_size=self.sizes[role])
                if sent is False:
                    return False
                index += 1
                self.cleanup_progress[role] = index
            # Let Windows dispatch this tap, without another screenshot/OCR or
            # per-like acknowledgement. Pause/Stop can interrupt the sequence.
            if index < len(points):
                self.control.stopped.wait(.01)
        return True

    def run(self):
        try:
            self.work()
        finally:
            for window in self.targets.values():
                close = getattr(window, "close_capture", None)
                if close:
                    close()

    def work(self):
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
                with self.control.lock:
                    if self.resume_generation != self.control.resume_generation:
                        self.engine.on_resume(self.control.now())
                        self.resume_generation = self.control.resume_generation
                summary = "; ".join(f"{r}: {v.state}" + (f" ({v.detail})" if v.detail else "")
                                    for r, v in views.items())
                self.send("status", f"{self.engine.runs} cycles completed · {summary}")
                remaining = self.engine.requeue_at - self.control.now()
                if remaining > 0 and all(v.state in {"world", "menu"} for v in views.values()):
                    self.send("status", f"Waiting {remaining:.1f}s for dungeon reload after leader Exit.")
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
                    if action.kind == "cleanup":
                        sent = self.cleanup(action.role, fresh)
                        if not sent:
                            continue
                    else:
                        point = action_point(action, fresh)
                        if point is None:
                            continue
                    if not self.control.active() and action.kind != "cleanup":
                        continue  # A changed/unreadable screen never authorizes input.
                    with self.control.lock:
                        if not self.control.active() and action.kind != "cleanup":
                            continue
                        if action.kind != "cleanup":
                            sent = self.targets[action.role].click(
                                point, allowed=self.control.active,
                                expected_size=self.sizes[action.role])
                            if sent is False:
                                continue
                        clicked_at = self.control.now()
                        planned.next_click = clicked_at
                        if action.kind == "accept":
                            planned.last_accept = clicked_at
                        if action.kind == "cleanup" and action.role == "leader":
                            planned.requeue_at = clicked_at + 5
                        if planned.pending:
                            pending_action, deadline = planned.pending
                            if deadline is not None:
                                planned.pending = pending_action, deadline + clicked_at - decision_time
                            if pending_action.kind == "match":
                                planned.match_retry_at += clicked_at - decision_time
                        self.engine = planned
                    self.send("log", f"{action.role}: {action.kind}")
            except Exception as error:
                if not self.control.stopped.is_set():
                    self.control.pause()
                    self.send("paused", str(error))
            self.control.stopped.wait(.02)


def action_point(action, view):
    expected = {"dungeon": "world", "match": "menu", "accept": "accept"}[action.kind]
    if view.state != expected:
        return None
    return view.targets.get(action.kind)


def cleanup_points(view):
    if view.state != "results" or not view.likes_ready or "return" not in view.targets:
        return None
    keys = tuple(f"like_{i}" for i in range(1, 5) if f"like_{i}" in view.targets) + ("return",)
    return tuple(view.targets[k] for k in keys)
