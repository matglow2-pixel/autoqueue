"""Clock-driven decisions, independent of Windows and mouse control."""
from dataclasses import dataclass, field


class SafetyStop(RuntimeError):
    pass


@dataclass
class View:
    state: str = "unknown"
    likes: list[tuple[int, int]] = field(default_factory=list)


@dataclass(frozen=True)
class Action:
    role: str
    kind: str
    point: tuple[int, int] | None = None


class Engine:
    def __init__(self):
        self.accepted = set()
        self.absent_since = {}
        self.last_accept = float("-inf")
        self.pending = None
        self.results = False
        self.results_seen = {}
        self.finished = set()
        self.member_at = float("inf")
        self.liked = {"leader": [], "member": []}
        self.next_click = 0.0
        self.runs = 0

    def step(self, views: dict[str, View], now: float) -> Action | None:
        for role, view in views.items():
            if view.state == "results":
                self.results_seen.setdefault(role, now)
            else:
                self.results_seen.pop(role, None)
            if view.state == "accept":
                self.absent_since.pop(role, None)
            else:
                self.absent_since.setdefault(role, now)
                # Loading and declined matches can briefly hide the prompt.
                if view.state in {"world", "menu", "queue", "results"} or now - self.absent_since[role] >= 3:
                    self.accepted.discard(role)

        if self.pending:
            action, deadline = self.pending
            view = views[action.role]
            expected = {
                "dungeon": {"menu"},
                "match": {"queue", "accept"},
                "return": {"world", "menu", "queue"},
            }
            if action.kind == "like":
                done = view.state == "results" and not any(
                    self.near(action.point, p) for p in view.likes
                )
            else:
                done = view.state in expected[action.kind]
            if done:
                self.pending = None
                if action.kind == "return":
                    self.finished.add(action.role)
                    if action.role == "leader":
                        # Delay begins after the leader has actually returned.
                        self.member_at = now + 2
            elif now >= deadline:
                raise SafetyStop(
                    f"{action.role}: could not confirm {action.kind}. "
                    "Check the game and calibration, then resume."
                )
            else:
                return None

        if now < self.next_click:
            return None

        # Prompt detection always wins over opening another menu.
        for role in ("leader", "member"):
            if (views[role].state == "accept" and role not in self.accepted
                    and now - self.last_accept >= 1):
                self.accepted.add(role)
                self.last_accept = now
                return self.emit(Action(role, "accept"), now)

        if any(v.state == "accept" for v in views.values()):
            return None

        if any(v.state == "results" for v in views.values()):
            self.results = True

        if self.results:
            if len(self.finished) == 2:
                self.results = False
                self.finished.clear()
                self.liked = {"leader": [], "member": []}
                self.runs += 1
                return None
            role = "member" if "leader" in self.finished else "leader"
            if role == "member" and now < self.member_at:
                return None
            view = views[role]
            if view.state != "results":
                return None
            # Let avatars/buttons finish appearing before counting zero likes.
            if now - self.results_seen[role] < 2:
                return None
            choices = [p for p in view.likes
                       if not any(self.near(p, old) for old in self.liked[role])]
            if choices:
                if len(self.liked[role]) >= 3:
                    raise SafetyStop("More than three like buttons found. Recalibrate the like template.")
                point = sorted(choices)[0]
                self.liked[role].append(point)
                return self.emit(Action(role, "like", point), now, timeout=4)
            return self.emit(Action(role, "return"), now, timeout=25)

        # Both must be back outside combat before a new queue can start.
        if views["member"].state not in {"world", "queue"}:
            return None
        if views["leader"].state == "world":
            return self.emit(Action("leader", "dungeon"), now, timeout=10)
        if views["leader"].state == "menu":
            return self.emit(Action("leader", "match"), now, timeout=15)
        return None

    @staticmethod
    def near(a, b):
        return abs(a[0] - b[0]) < 20 and abs(a[1] - b[1]) < 20

    def emit(self, action, now, timeout=None):
        self.next_click = now + 0.6
        if timeout:
            self.pending = (action, now + timeout)
        return action

    def rebase_after_pause(self, duration):
        """Paused time must not consume confirmation deadlines or delays."""
        if self.pending:
            action, deadline = self.pending
            self.pending = action, deadline + duration
        self.next_click += duration
        self.member_at += duration
        self.last_accept += duration
        self.absent_since = {r: t + duration for r, t in self.absent_since.items()}
        self.results_seen = {r: t + duration for r, t in self.results_seen.items()}
