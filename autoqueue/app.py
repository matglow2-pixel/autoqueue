import json
import copy
import os
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import ImageTk

from .engine import Engine, SafetyStop
from .vision import Recognizer
from .windows import Hotkeys, enable_dpi_awareness, list_windows

ROLES = ("leader", "member")
STATES = ("world", "menu", "queue", "accept", "results")
HELP = {
    "world": "Show the outdoor dungeon entrance. Drag a box around the fixed minimap location label (Demonseal Gorge), then click the dungeon entrance.",
    "menu": "Open the dungeon panel BEFORE queuing. Drag a box tightly around the yellow Match button, then click its center.",
    "queue": "Start matchmaking. Drag a box tightly around Cancel (leader), or the fixed Matchmaking label (member). Exclude the changing timer. No click point needed.",
    "accept": "When a match appears, capture it BEFORE accepting. Drag a box tightly around the yellow Accept button, then click its center.",
    "results": "On the end screen BEFORE liking anyone: drag a box tightly around the Drops label, then click the bottom-left return arrow.",
    "like": "On the same end screen: drag a box around ONE whole white, unclicked like button, including the thumb. No click point needed. All matching buttons in this row will be liked.",
}


class Editor(tk.Toplevel):
    def __init__(self, parent, image, state, done):
        super().__init__(parent)
        self.title(f"Calibrate {state}")
        self.image, self.state, self.done = image, state, done
        self.box = self.point = self.start = None
        self.rectangle = self.cross = None
        ttk.Label(self, text=HELP[state], wraplength=660).pack(padx=12, pady=8)
        self.hint = ttk.Label(self, text="1. Drag the recognition box. 2. Click the action point (if needed).")
        self.hint.pack()
        scale = min(1, (self.winfo_screenheight() - 240) / image.height,
                    (self.winfo_screenwidth() - 150) / image.width)
        self.scale = scale
        self.photo = ImageTk.PhotoImage(image.resize((int(image.width * scale), int(image.height * scale))))
        self.canvas = tk.Canvas(self, width=self.photo.width(), height=self.photo.height(), cursor="crosshair")
        self.canvas.pack(padx=12, pady=8)
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        bar = ttk.Frame(self)
        bar.pack(pady=8)
        ttk.Button(bar, text="Reset marks", command=self.reset).pack(side="left", padx=5)
        ttk.Button(bar, text="Save calibration", command=self.save).pack(side="left", padx=5)
        self.grab_set()

    def reset(self):
        for item in (self.rectangle, self.cross):
            if item:
                self.canvas.delete(item)
        self.box = self.point = self.start = None

    def press(self, event):
        self.start = event.x, event.y

    def drag(self, event):
        if self.box is None and self.start:
            if self.rectangle:
                self.canvas.delete(self.rectangle)
            self.rectangle = self.canvas.create_rectangle(*self.start, event.x, event.y, outline="red", width=2)

    def release(self, event):
        if self.box is None and self.start:
            x, y = self.start
            coords = [min(x, event.x), min(y, event.y), max(x, event.x), max(y, event.y)]
            if coords[2] - coords[0] < 8 or coords[3] - coords[1] < 8:
                return
            self.box = [round(v / self.scale) for v in coords]
            self.hint.config(text="Recognition box set. Click the action point, or Save if none is needed.")
        elif self.state not in {"queue", "like"}:
            self.point = [round(event.x / self.scale), round(event.y / self.scale)]
            if self.cross:
                self.canvas.delete(self.cross)
            self.cross = self.canvas.create_oval(event.x - 5, event.y - 5, event.x + 5, event.y + 5,
                                                 fill="lime", outline="black")

    def save(self):
        if self.box is None or (self.state not in {"queue", "like"} and self.point is None):
            messagebox.showinfo("Missing marks", "Drag a recognition box, then mark the action point.", parent=self)
            return
        self.done(self.image, self.box, self.point)
        self.destroy()


class App:
    def __init__(self, root):
        self.root = root
        root.title("Sword x Staff — Autoqueue")
        root.geometry("760x650")
        self.folder = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "SwordStaffAutoqueue"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / "calibration.json"
        try:
            self.config = json.loads(self.path.read_text()) if self.path.exists() else {}
        except (ValueError, OSError):
            self.config = {}
        self.engine = None
        self.running = False
        self.paused_at = None
        self.recognizer = None
        self.windows = []
        self.targets = {}
        self.last_status = None
        self.capturing = False
        self.starting = False
        self.hotkeys = Hotkeys()

        ttk.Label(root, text="Two BlueStacks windows · no ADB", font=("Segoe UI", 15)).pack(pady=12)
        ttk.Label(root, text="Keep both games visible, side by side. Assign roles to match your in-game party.").pack()
        frame = ttk.LabelFrame(root, text="1. Assign windows (select again after restarting BlueStacks)")
        frame.pack(fill="x", padx=12, pady=10)
        self.selectors = {}
        for role in ROLES:
            row = ttk.Frame(frame)
            row.pack(fill="x", padx=8, pady=4)
            ttk.Label(row, text=role.title(), width=10).pack(side="left")
            combo = ttk.Combobox(row, state="readonly", width=72)
            combo.pack(side="left", fill="x", expand=True)
            self.selectors[role] = combo
        ttk.Button(frame, text="Refresh windows", command=self.refresh).pack(pady=5)

        frame = ttk.LabelFrame(root, text="2. Calibrate once at your chosen window size")
        frame.pack(fill="x", padx=12, pady=5)
        row = ttk.Frame(frame)
        row.pack(fill="x", padx=8, pady=8)
        self.role = tk.StringVar(value="leader")
        self.state = tk.StringVar(value="world")
        ttk.Combobox(row, textvariable=self.role, values=ROLES, state="readonly", width=10).pack(side="left", padx=3)
        ttk.Combobox(row, textvariable=self.state, values=STATES + ("like",), state="readonly", width=12).pack(side="left", padx=3)
        self.capture_button = ttk.Button(row, text="Capture in 3 seconds", command=self.capture)
        self.capture_button.pack(side="left", padx=5)
        ttk.Button(row, text="Check screens (no clicks)", command=self.check).pack(side="left", padx=3)
        self.progress = ttk.Label(frame, wraplength=710)
        self.progress.pack(padx=8, pady=5)
        self.tip = ttk.Label(frame, text=HELP["world"], wraplength=710)
        self.tip.pack(padx=8, pady=5)
        self.state.trace_add("write", lambda *_: self.tip.config(text=HELP[self.state.get()]))

        controls = ttk.Frame(root)
        controls.pack(pady=10)
        ttk.Button(controls, text="Start / pause (F8)", command=self.toggle).pack(side="left", padx=5)
        ttk.Button(controls, text="STOP (F9)", command=self.stop).pack(side="left", padx=5)
        ttk.Label(root, text="F9 stops all future clicks. Mouse to a screen corner also pauses on the next click.").pack()
        self.status = ttk.Label(root, text="Stopped. Calibrate both accounts before starting.", wraplength=710)
        self.status.pack(pady=8)
        self.log = tk.Text(root, height=9, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, padx=12, pady=10)
        self.refresh()
        self.update_progress()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(150, self.tick)

    def write(self, text):
        self.log.config(state="normal")
        self.log.insert("end", time.strftime("%H:%M:%S ") + text + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def update_progress(self):
        lines = []
        for role in ROLES:
            required = self.required(role)
            markers = self.config.get(role, {}).get("markers", {})
            missing = [s for s in required if s not in markers]
            lines.append(f"{role.title()}: " + ("missing " + ", ".join(missing) if missing else "calibration complete"))
        self.progress.config(text="\n".join(lines))

    @staticmethod
    def required(role):
        return STATES + ("like",) if role == "leader" else ("world", "queue", "accept", "results", "like")

    def refresh(self):
        if self.running or self.engine is not None:
            self.stop()
        self.windows = list_windows()
        labels = [f"{w.title}  [window {w.handle:X}]" for w in self.windows]
        for combo in self.selectors.values():
            combo.set("")
            combo["values"] = labels

    def selected(self):
        targets = {}
        for role, combo in self.selectors.items():
            if combo.current() < 0:
                raise SafetyStop("Select both the leader and member windows.")
            targets[role] = self.windows[combo.current()]
        if targets["leader"].handle == targets["member"].handle:
            raise SafetyStop("Leader and member must be two different windows.")
        return targets

    def capture(self):
        self.stop()
        try:
            targets = self.selected()
        except SafetyStop as error:
            messagebox.showinfo("Choose windows", str(error))
            return
        role, state = self.role.get(), self.state.get()
        if state not in self.required(role):
            messagebox.showinfo("Not needed", "Only the leader needs a dungeon menu marker.")
            return
        self.capturing = True
        self.capture_button.config(state="disabled")
        self.root.iconify()

        def take():
            try:
                image = targets[role].capture()
            except Exception as error:
                self.root.deiconify()
                messagebox.showerror("Capture failed", str(error))
            else:
                self.root.deiconify()
                Editor(self.root, image, state,
                       lambda img, box, point: self.save_marker(role, state, img, box, point))
            finally:
                self.capturing = False
                self.capture_button.config(state="normal")
        self.root.after(3000, take)

    def save_marker(self, role, state, image, box, point):
        data = self.config.get(role, {})
        if data.get("size") and data["size"] != list(image.size):
            if not messagebox.askyesno("Window resized", "This window changed size. Clear its old calibration and use this size?"):
                return
            data = {}
        data.setdefault("markers", {})
        data["size"] = list(image.size)
        name = f"{role}-{state}.png"
        image.crop(box).save(self.folder / name)
        data["markers"][state] = {"box": box, "point": point, "file": name}
        self.config[role] = data
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.config, indent=2))
        temp.replace(self.path)
        self.update_progress()
        self.write(f"Saved {role} {state}.")

    def prepare(self):
        targets = self.selected()
        if self.engine and self.targets and any(targets[r].handle != self.targets[r].handle for r in ROLES):
            raise SafetyStop("Window assignments changed. Press F9 before starting a new session.")
        self.targets = targets
        for role in ROLES:
            data = self.config.get(role, {})
            if any(s not in data.get("markers", {}) for s in self.required(role)):
                raise SafetyStop(f"Finish {role} calibration first.")
        self.recognizer = Recognizer(self.folder, self.config)

    def views(self):
        return {role: self.recognizer.inspect(role, window.capture(self.config[role]["size"]))
                for role, window in self.targets.items()}

    def check(self):
        if self.capturing or self.starting:
            return
        if self.running:
            self.pause("Paused for screen check.")
        try:
            self.prepare()
        except Exception as error:
            self.write(str(error))
            return
        self.capturing = True
        self.root.iconify()

        def inspect():
            try:
                views = self.views()
                self.write("Screen check: " + "; ".join(
                    f"{role}: {v.state}, {len(v.likes)} unclicked likes" for role, v in views.items()))
            except Exception as error:
                self.write(str(error))
            finally:
                self.capturing = False
                self.root.deiconify()
        self.root.after(400, inspect)

    def toggle(self):
        if self.capturing or self.starting or self.root.grab_current():
            return
        if self.running:
            self.pause("Paused. F8 resumes; F9 resets the session.")
            return
        try:
            self.prepare()
            self.starting = True
            self.root.iconify()
            self.root.after(400, self.begin)
        except Exception as error:
            self.pause(str(error))

    def begin(self):
        if not self.starting:
            return
        self.starting = False
        try:
            self.views()  # Verify visibility and calibrated dimensions first.
            if self.engine is None:
                self.engine = Engine()
            elif self.paused_at is not None:
                self.engine.rebase_after_pause(time.monotonic() - self.paused_at)
            self.running = True
            self.paused_at = None
            self.write("Running. F8 pauses; F9 stops.")
            self.status.config(text="Running. Waiting for recognized screens.")
        except Exception as error:
            self.pause(str(error))

    def pause(self, reason):
        if self.paused_at is None:
            self.paused_at = time.monotonic()
        self.running = False
        self.status.config(text=reason)
        self.write(reason)

    def stop(self):
        self.running = False
        self.starting = False
        self.engine = None
        self.paused_at = None
        self.last_status = None
        self.status.config(text="Stopped. No more clicks. F8 starts a new session.")

    def tick(self):
        try:
            events = self.hotkeys.poll()
            if "stop" in events:
                self.stop()
            elif "toggle" in events:
                self.toggle()
            if self.running:
                # Role selection must never change under a running session.
                selected = self.selected()
                if any(selected[r].handle != self.targets[r].handle for r in ROLES):
                    raise SafetyStop("Window selection changed. Stop and start a new session.")
                views = self.views()
                status = "; ".join(f"{r}: {v.state}" for r, v in views.items())
                self.status.config(text=f"Running · {self.engine.runs} cycles completed · {status}")
                if status != self.last_status:
                    self.write(status)
                    self.last_status = status
                planned = copy.deepcopy(self.engine)
                action = planned.step(views, time.monotonic())
                if action:
                    # Handle emergency hotkeys once more immediately before input.
                    events = self.hotkeys.poll()
                    if events:
                        self.stop()  # Discard the planned action and its bookkeeping.
                    else:
                        window = self.targets[action.role]
                        fresh = self.recognizer.inspect(action.role,
                            window.capture(self.config[action.role]["size"]))
                        expected = {"dungeon": "world", "match": "menu", "accept": "accept",
                                    "like": "results", "return": "results"}[action.kind]
                        if fresh.state != expected:
                            raise SafetyStop("Screen changed before click. Inspect it, then F9/F8 to restart.")
                        if action.kind == "like" and not any(Engine.near(action.point, p) for p in fresh.likes):
                            raise SafetyStop("Like button changed before click. F9/F8 to restart.")
                        if action.kind == "return" and fresh.likes:
                            raise SafetyStop("New unclicked likes appeared. F8 resumes after inspection.")
                        point = action.point or self.config[action.role]["markers"][expected]["point"]
                        window.click(point)
                        self.engine = planned
                        self.write(f"{action.role}: {action.kind}")
                else:
                    self.engine = planned
        except Exception as error:
            self.pause(f"Paused: {error}")
        self.root.after(200, self.tick)

    def close(self):
        self.stop()
        self.hotkeys.close()
        self.root.destroy()


def main():
    enable_dpi_awareness()
    root = tk.Tk()
    try:
        App(root)
    except Exception as error:
        messagebox.showerror("Autoqueue could not start", str(error))
        root.destroy()
        sys.exit(1)
    root.mainloop()
