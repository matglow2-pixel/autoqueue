"""Clock-driven decisions, independent of Windows and mouse control."""
from dataclasses import dataclass, field


class SafetyStop(RuntimeError):
    pass


class WindowUnavailable(SafetyStop):
    """Temporary occlusion: retry observation without disabling the worker."""


RESULTS_WAIT = 1.0
DUNGEON_RETRY_SECONDS = 2.0
MAX_DUNGEON_ATTEMPTS = 3


@dataclass
class View:
    state: str = "unknown"
    likes: list[tuple[int, int]] = field(default_factory=list)
    targets: dict[str, tuple[int, int]] = field(default_factory=dict)
    likes_ready: bool = True
    detail: str = ""
    likes_cleared: bool = False


@dataclass(frozen=True)
class Action:
    role: str
    kind: str
    point: tuple[int, int] | None = None


class Engine:
    def __init__(self):
        self.accepted = set()
        self.accept_sent_at = {}
        self.absent_since = {}
        self.last_accept = float("-inf")
        self.pending = None
        self.results = False
        self.results_seen = {}
        self.finished = set()
        self.next_click = 0.0
        self.runs = 0
        self.match_attempts = 0
        self.match_retry_at = 0.0
        self.dungeon_attempts = 0
        self.dungeon_retry_at = 0.0
        self.requeue_at = 0.0

    def step(self, views: dict[str, View], now: float) -> Action | None:
        for role, view in views.items():
            if view.state == "results":
                self.results_seen.setdefault(role, now)
            elif view.state in {"world", "menu", "queue", "accept", "accepted"}:
                self.results_seen.pop(role, None)
            if view.state in {"accept", "accepted", "blocked"}:
                self.absent_since.pop(role, None)
            else:
                self.absent_since.setdefault(role, now)
                # Loading and declined matches can briefly hide the prompt.
                if view.state in {"world", "menu", "queue", "results"} or now - self.absent_since[role] >= 3:
                    self.accepted.discard(role)
                    self.accept_sent_at.pop(role, None)

        # Accept prompts are time-sensitive. They must be handled before an
        # older action's confirmation deadline, even after a very long queue.
        if any(v.state == "accept" for v in views.values()):
            self.pending = None
            self.match_attempts = 0
            self.dungeon_attempts = 0
            if self.results:
                self.results = False
                self.finished.clear()
            # Give each account its first attempt before retrying a missed tap.
            # A sent click is not an acknowledgement from BlueStacks. Retry
            # only a freshly detected, still-active yellow Accept button.
            roles = sorted(("leader", "member"), key=lambda r: (
                r in self.accepted, self.accept_sent_at.get(r, float("-inf"))))
            for role in roles:
                if (views[role].state == "accept" and now - self.last_accept >= 1.5
                        and now - self.accept_sent_at.get(role, float("-inf")) >= 2):
                    self.accepted.add(role)
                    self.accept_sent_at[role] = now
                    self.last_accept = now
                    return self.emit(Action(role, "accept"), now)
            return None

        if self.pending:
            action, deadline = self.pending
            view = views[action.role]
            if view.state == "blocked":
                return None
            expected = {
                "dungeon": {"menu", "queue", "accepted", "results"},
                "match": {"queue", "world", "results"},
                "cleanup": {"world", "menu", "queue"},
            }
            done = view.state in expected[action.kind]
            if done:
                self.pending = None
                if action.kind == "match":
                    self.match_attempts = 0
                if action.kind == "dungeon":
                    self.dungeon_attempts = 0
                if action.kind == "cleanup":
                    self.finished.add(action.role)
            elif action.kind == "dungeon":
                # A tap during the return animation may be ignored. Retry the
                # same marked point only while the outside HUD is confirmed.
                # An unreadable/loading frame never authorizes a retry or pause.
                if view.state == "world" and now >= self.dungeon_retry_at:
                    if self.dungeon_attempts >= MAX_DUNGEON_ATTEMPTS:
                        raise SafetyStop(
                            f"{action.role}: dungeon menu not detected after {MAX_DUNGEON_ATTEMPTS} entrance clicks. "
                            "Check the leader's game screen, then press F8."
                        )
                    return self.emit(Action(action.role, "dungeon"), now)
                return None
            elif action.kind == "match":
                # An unreadable queue/transition is still a queue wait. There
                # is no deadline for a match to be found. Only a positively
                # detected, still-visible Match button permits a bounded retry.
                if view.state == "menu" and now >= self.match_retry_at:
                    if self.match_attempts >= 3:
                        raise SafetyStop("Match stayed visible after three clicks. Check the game, then resume.")
                    return self.emit(Action(action.role, "match"), now)
                return None
            elif deadline is not None and now >= deadline:
                raise SafetyStop(
                    f"{action.role}: could not confirm {action.kind}. "
                    "Check the game screen, then resume."
                )
            else:
                return None

        if now < self.next_click:
            return None

        if any(v.state == "results" for v in views.values()):
            self.results = True

        if self.results:
            if len(self.finished) == 2:
                self.results = False
                self.finished.clear()
                self.runs += 1
                return None
            role = "leader" if "member" in self.finished else "member"
            view = views[role]
            if view.state != "results":
                return None
            wait = RESULTS_WAIT
            if now - self.results_seen[role] < wait:
                return None
            if not view.likes_ready:
                return None
            return self.emit(Action(role, "cleanup"), now, timeout=25)

        # Both must be back outside combat before a new queue can start.
        if now < self.requeue_at:
            return None
        if views["member"].state not in {"world", "queue"}:
            return None
        if views["leader"].state == "world":
            return self.emit(Action("leader", "dungeon"), now)
        if views["leader"].state == "menu":
            return self.emit(Action("leader", "match"), now)
        return None

    @staticmethod
    def near(a, b):
        return abs(a[0] - b[0]) < 20 and abs(a[1] - b[1]) < 20

    def emit(self, action, now, timeout=None):
        self.next_click = now
        if action.kind == "cleanup" and action.role == "leader":
            self.requeue_at = now + 5
        if action.kind == "dungeon":
            self.pending = (action, None)
            self.dungeon_attempts += 1
            self.dungeon_retry_at = now + DUNGEON_RETRY_SECONDS
        elif action.kind == "match":
            self.pending = (action, None)
            self.match_attempts += 1
            self.match_retry_at = now + 2
        elif timeout:
            self.pending = (action, now + timeout)
        return action

    def on_resume(self, now):
        """Give a fresh confirmation window instead of rethrowing old deadlines."""
        if self.pending:
            action, _ = self.pending
            if action.kind == "dungeon":
                self.pending = (action, None)
                self.dungeon_attempts = 0
                self.dungeon_retry_at = now + DUNGEON_RETRY_SECONDS
            elif action.kind == "match":
                self.pending = (action, None)
                self.match_attempts = 0
                self.match_retry_at = now + 2
            else:
                self.pending = (action, now + 25)

    def rebase_after_pause(self, duration):
        """Paused time must not consume confirmation deadlines or delays."""
        if self.pending:
            action, deadline = self.pending
            self.pending = action, deadline + duration if deadline is not None else None
        self.next_click += duration
        self.last_accept += duration
        self.accept_sent_at = {r: t + duration for r, t in self.accept_sent_at.items()}
        self.match_retry_at += duration
        self.dungeon_retry_at += duration
        self.requeue_at += duration
        self.results_seen = {r: t + duration for r, t in self.results_seen.items()}
        self.absent_since = {r: t + duration for r, t in self.absent_since.items()}
