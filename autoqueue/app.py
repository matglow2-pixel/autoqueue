"""The desktop UI: assign two windows and start. No calibration or templates."""
import queue
import time
import tkinter as tk
from tkinter import messagebox, ttk

from .engine import SafetyStop
from .runner import Runner
from .windows import Hotkeys, enable_dpi_awareness, list_windows


class App:
    def __init__(self, root):
        self.root = root
        self.runner = None
        self.retired = []
        self.start_pending = False
        self.events = queue.SimpleQueue()
        self.windows = []
        self.selectors = {}
        self.hotkeys = Hotkeys()
        root.title("Sword x Staff Autoqueue — OCR 1.8")
        root.geometry("760x440")
        ttk.Label(root, text="Sword x Staff Autoqueue", font=("Segoe UI", 17)).pack(pady=12)
        ttk.Label(root, text="Select the two game windows, then Start. Buttons are detected automatically.").pack()
        ttk.Label(root, text="Keep both games visible, side by side, in English. Both accounts must already be in the party.").pack(pady=5)
        frame = ttk.LabelFrame(root, text="Accounts")
        frame.pack(fill="x", padx=12, pady=8)
        for role in ("leader", "member"):
            row = ttk.Frame(frame)
            row.pack(fill="x", padx=8, pady=5)
            ttk.Label(row, text=role.title(), width=9).pack(side="left")
            selector = ttk.Combobox(row, state="readonly", width=72)
            selector.pack(side="left", fill="x", expand=True)
            self.selectors[role] = selector
        ttk.Button(frame, text="Refresh windows", command=self.refresh).pack(pady=5)
        controls = ttk.Frame(root)
        controls.pack(pady=6)
        ttk.Button(controls, text="Start / Pause (F8)", command=self.toggle).pack(side="left", padx=6)
        ttk.Button(controls, text="Stop (F9)", command=self.stop).pack(side="left", padx=6)
        self.status = ttk.Label(root, text="Stopped. Choose the in-game leader above.", wraplength=720)
        self.status.pack(padx=12, pady=5)
        self.log = tk.Text(root, height=8, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, padx=12, pady=8)
        self.refresh()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.tick)

    def write(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", time.strftime("%H:%M:%S ") + text + "\n")
        if int(self.log.index("end-1c").split(".")[0]) > 300:
            self.log.delete("1.0", "100.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def refresh(self):
        self.stop()
        self.windows = list_windows()
        labels = [f"{w.title}  [{w.handle:X}]" for w in self.windows]
        players = [i for i, w in enumerate(self.windows)
                   if "bluestacks" in w.title.lower() or "app player" in w.title.lower()]
        for role, selector in self.selectors.items():
            selector.configure(values=labels)
            selector.set("")
            index = 0 if role == "leader" else 1
            if len(players) > index:
                selector.current(players[index])

    def selected(self):
        targets = {}
        for role, selector in self.selectors.items():
            if selector.current() < 0:
                raise SafetyStop("Select the leader and member game windows first.")
            targets[role] = self.windows[selector.current()]
        if targets["leader"].handle == targets["member"].handle:
            raise SafetyStop("Choose two different windows.")
        return targets

    def toggle(self):
        if self.start_pending:
            return
        if self.runner and not self.runner.control.stopped.is_set():
            if self.runner.control.active():
                self.runner.control.pause()
                self.status.configure(text="Paused. F8 resumes; F9 stops.")
                return
            self.root.iconify()
            self.start_pending = True
            self.root.after(400, self.begin)
            return
        # A stopped worker may still be completing OCR. Do not overlap workers.
        if self.runner:
            self.retired.append(self.runner)
            self.runner = None
        if any(thread.is_alive() for thread in self.retired):
            self.status.configure(text="Finishing the previous screen read. Press F8 again in a moment.")
            return
        try:
            targets = self.selected()
        except SafetyStop as error:
            messagebox.showinfo("Choose windows", str(error))
            return
        self.pending_targets = targets
        self.root.iconify()
        self.start_pending = True
        self.root.after(400, self.begin)

    def begin(self):
        if not self.start_pending:
            return
        self.start_pending = False
        if self.runner and not self.runner.control.stopped.is_set():
            self.runner.control.resume()
        else:
            # Drop stale messages from the stopped worker before a new session.
            while not self.events.empty():
                self.events.get_nowait()
            self.runner = Runner(self.pending_targets, self.events)
            self.runner.start()
        for selector in self.selectors.values():
            selector.configure(state="disabled")
        self.status.configure(text="Running. F8 pauses; F9 stops.")
        self.write("Started. End-screen wait: 1s. Likes 0.2–0.5s apart; accepts 1.5s apart; reload 5s. Missed accepts retry automatically.")

    def stop(self):
        self.start_pending = False
        if self.runner:
            self.runner.control.stop()
        for selector in self.selectors.values():
            selector.configure(state="readonly")
        self.status.configure(text="Stopped. No further clicks. F8 starts a new session.")

    def tick(self):
        events = self.hotkeys.poll()
        if "stop" in events:
            self.stop()
        elif "toggle" in events:
            self.toggle()
        while True:
            try:
                kind, text = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.write(text)
            elif self.runner and not self.runner.control.stopped.is_set():
                if kind == "status" and self.runner.control.active():
                    self.status.configure(text="Running · " + text)
                elif kind == "paused":
                    self.status.configure(text="Paused: " + text)
                    self.write("Paused: " + text)
                    self.root.deiconify()
            elif kind == "error":
                self.write(text)
                self.status.configure(text=text)
                self.root.deiconify()
        self.retired = [thread for thread in self.retired if thread.is_alive()]
        self.root.after(100, self.tick)

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
        return
    root.mainloop()
