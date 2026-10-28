"""Background OCR and guarded input. The GUI stays responsive during inference."""
import copy
import os
import random
import threading
import time
from pathlib import Path

from .engine import Engine, SafetyStop
from .vision import Recognizer, remember_like_patches, clicked_likes_cleared


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
    def __init__(self, targets, events, recognizer_factory=Recognizer, like_delay=None):
        super().__init__(daemon=True)
        self.targets = targets
        self.events = events
        self.control = Control()
        self.recognizer_factory = recognizer_factory
        self.like_delay = like_delay or (lambda: random.uniform(.2, .5))
        self.engine = Engine()
        self.sizes = {}
        self.resume_generation = 0
        self.cleanup_progress = {}
        self.cleanup_sequences = {}
        self.verification_since = {}
        self.cleanup_retries = {}
        self.missing_likes_since = {}
        self.diagnostic_saved = set()
        self.last_images = {}
        self.like_evidence = {}
        self.clicked_likes = {}

    def send(self, kind, text):
        self.events.put((kind, text))

    def observe(self, role):
        window = self.targets[role]
        image = window.capture()
        size = tuple(image.size)
        if role in self.sizes and size != self.sizes[role]:
            raise SafetyStop("Window resized. Stop and Start to use its new size.")
        self.sizes[role] = size
        self.last_images[role] = image
        view = self.recognizer.inspect(image, role=role)
        if view.state == "results":
            view.likes_cleared = view.likes_cleared or clicked_likes_cleared(
                image, self.like_evidence.get(role, {}), self.clicked_likes.get(role, set()))
            if view.likes_cleared and not view.likes:
                view.likes_ready = True
                view.detail = "Clicked white buttons disappeared; Exit ready."
        if view.state == "results" and not view.likes_ready:
            self.missing_likes_since.setdefault(role, self.control.now())
            if self.control.now() - self.missing_likes_since[role] >= 3:
                self.save_diagnostic(role, image)
        else:
            self.missing_likes_since.pop(role, None)
        if view.state in {"world", "menu", "queue"}:
            self.cleanup_progress.pop(role, None)
            self.cleanup_sequences.pop(role, None)
            self.verification_since.pop(role, None)
            self.cleanup_retries.pop(role, None)
            self.diagnostic_saved.discard(role)
            self.like_evidence.pop(role, None)
            self.clicked_likes.pop(role, None)
        return view

    def save_diagnostic(self, role, image=None):
        if role in self.diagnostic_saved:
            return
        try:
            if image is None:
                image = self.targets[role].capture()
            folder = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "SwordStaffAutoqueue" / "debug"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{role}-results-{time.strftime('%Y%m%d-%H%M%S')}.png"
            image.save(path)
            self.diagnostic_saved.add(role)
            self.send("log", f"{role}: results kept open. Diagnostic screenshot saved: {path}")
        except OSError as error:
            self.send("log", f"Could not save diagnostic screenshot: {error}")

    def verify_likes(self, role):
        fresh = self.observe(role)
        if not self.control.active() or fresh.state != "results":
            return False
        if fresh.likes_cleared and not fresh.likes:
            return True  # The white buttons we clicked disappeared. Incoming likes are irrelevant.
        now = self.control.now()
        self.verification_since.setdefault(role, now)
        elapsed = now - self.verification_since[role]
        if fresh.likes and elapsed >= .3:
            retries = self.cleanup_retries.get(role, 0)
            if retries >= 2:
                self.save_diagnostic(role)
                raise SafetyStop(f"{role}: thumbs still visible after retries; results kept open.")
            self.cleanup_sequences[role] = cleanup_points(fresh)
            self.cleanup_progress[role] = 0
            self.cleanup_retries[role] = retries + 1
            self.verification_since.pop(role, None)
            self.send("log", f"{role}: retrying {len(fresh.likes)} thumbs that did not register.")
        elif not fresh.likes_ready and elapsed >= 1:
            self.save_diagnostic(role)
            raise SafetyStop(f"{role}: could not verify likes; results kept open.")
        return False

    def cleanup(self, role, view):
        points = self.cleanup_sequences.get(role) or cleanup_points(view)
        if points is None:
            return False
        self.cleanup_sequences[role] = points
        index = self.cleanup_progress.get(role, 0)
        if index == 0:
            image = self.last_images.get(role)
            if image is not None:
                remember_like_patches(image, points[:-1], self.like_evidence.setdefault(role, {}))
            self.send("log", f"{role}: clicking {len(points) - 1} thumbs-up icons, then Exit.")
        while index < len(points):
            if not self.control.active():
                return False
            # Check once after the whole batch, not between individual likes.
            if index == len(points) - 1 and not self.verify_likes(role):
                return False
            with self.control.lock:
                if not self.control.active():
                    return False
                sent = self.targets[role].click(points[index], allowed=self.control.active,
                                                expected_size=self.sizes[role])
                if sent is False:
                    return False
                index += 1
                self.cleanup_progress[role] = index
                if index < len(points):
                    self.clicked_likes.setdefault(role, set()).add(points[index - 1])
            # Let Windows dispatch this tap, without another screenshot/OCR or
            # per-like acknowledgement. Pause/Stop can interrupt the sequence.
            if index < len(points):
                delay = self.like_delay() if index < len(points) - 1 else .01
                self.control.stopped.wait(delay)
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
                settling = []
                for role, view in views.items():
                    if view.state == "results":
                        wait = 2 if role == "member" else 1
                        seen = self.engine.results_seen.get(role, self.control.now())
                        left = wait - (self.control.now() - seen)
                        if left > 0:
                            settling.append(f"{role} end-screen wait {left:.1f}s")
                if settling:
                    summary += " · " + "; ".join(settling)
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
