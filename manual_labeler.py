import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import csv
import cv2
from PIL import Image, ImageTk

# ── Palette ───────────────────────────────────────────────────────────────────
BG        = "#f0f0f0"   # window / panel background
BG_DARK   = "#e1e1e1"   # button, scrubber, tick strip
BG_HOVER  = "#c8c8c8"   # button hover
FG        = "#111111"   # primary text
FG_DIM    = "#555555"   # subdued text / controls button
SEP       = "#cccccc"   # trough / divider
GREEN     = "#228B22"   # START tick + complete row fg
RED       = "#cc2222"   # STOP tick + recording indicator
AMBER_BG  = "#fff8dc"   # in-progress row background
AMBER_FG  = "#7a5800"   # in-progress row text
GREEN_BG  = "#e8f5e9"   # complete row background


def _hoverable(btn, normal=BG_DARK, hover=BG_HOVER):
    btn.bind("<Enter>", lambda _: btn.config(bg=hover))
    btn.bind("<Leave>", lambda _: btn.config(bg=normal))


class SwallowLabeler(tk.Tk):
    def __init__(self, video_path=None):
        super().__init__()
        self.title("Swallow Labeler")
        self.configure(bg=BG)

        # Placeholders — populated by load_video()
        self.cap = None
        self.video_path = None
        self.current_frame = 0
        self.fps = 30.0
        self.total_frames = 1
        self.events = []
        self.swallow_events = []
        self.is_logging_swallow = False
        self._scrubber_sync = False
        self.is_playing = False
        self.play_job = None
        self.playback_speed = 1.0

        self._build_styles()
        self._build_sidebar()
        self._build_main_area()
        self._bind_keys()

        self.after(100, lambda: self.load_video(video_path))

    # ── Video Loading ─────────────────────────────────────────────────────────

    def load_video(self, path=None):
        if path is None:
            path = filedialog.askopenfilename(
                title="Open Video",
                filetypes=[("Video files", "*.mov *.mp4 *.avi *.mkv *.MOV"), ("All files", "*.*")],
            )
        if not path:
            if self.cap is None:
                self.destroy()
            return

        new_cap = cv2.VideoCapture(path)
        if not new_cap.isOpened():
            messagebox.showerror("Error", f"Cannot open video: {path}")
            return

        if self.cap is not None:
            self.cap.release()

        self.cap = new_cap
        self.video_path = path
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # Reset session state
        self.current_frame = 0
        self.events = []
        self.swallow_events = []
        self.is_logging_swallow = False
        if self.is_playing:
            self.is_playing = False
            if self.play_job:
                self.after_cancel(self.play_job)
                self.play_job = None

        # Sync UI
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.tick_canvas.delete("all")
        self.scrubber.config(from_=0, to=self.total_frames - 1)
        self._scrubber_sync = True
        self.scrubber.set(0)
        self._scrubber_sync = False
        self._set_status()
        self._show_frame()

        print(f">>> Loaded {os.path.basename(path)} at {self.fps:.3f} FPS. "
              f"1 frame = {1 / self.fps:.4f} seconds.")

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview",
            background="white", foreground=FG,
            fieldbackground="white", rowheight=22,
            font=("Courier", 10),
        )
        style.configure("Treeview.Heading",
            background=BG_DARK, foreground=FG,
            font=("Courier", 10, "bold"),
        )
        style.map("Treeview", background=[("selected", SEP)])

    def _build_sidebar(self):
        sidebar = tk.Frame(self, bg=BG, width=240)
        sidebar.pack(side=tk.RIGHT, fill=tk.Y)
        sidebar.pack_propagate(False)

        open_btn = tk.Button(sidebar, text="📁  Open Video",
                             command=self.load_video,
                             bg=BG_DARK, fg=FG, activebackground=BG_HOVER,
                             activeforeground=FG, font=("Courier", 10),
                             relief=tk.RAISED, pady=5, bd=1)
        open_btn.pack(fill=tk.X, padx=8, pady=(8, 4))
        _hoverable(open_btn)

        tk.Label(sidebar, text="Swallow Events", bg=BG, fg=FG,
                 font=("Courier", 12, "bold"), pady=8).pack()

        tree_frame = tk.Frame(sidebar, bg=BG)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("num", "start", "stop", "duration"),
            show="headings",
            yscrollcommand=scrollbar.set,
        )
        scrollbar.config(command=self.tree.yview)

        self.tree.heading("num", text="#")
        self.tree.heading("start", text="Start")
        self.tree.heading("stop", text="Stop")
        self.tree.heading("duration", text="Dur.")
        self.tree.column("num", width=25, anchor="center", stretch=False)
        self.tree.column("start", width=62, anchor="center")
        self.tree.column("stop", width=62, anchor="center")
        self.tree.column("duration", width=62, anchor="center")

        self.tree.tag_configure("in_progress", background=AMBER_BG, foreground=AMBER_FG)
        self.tree.tag_configure("complete", background=GREEN_BG, foreground=GREEN)

        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_event_click)

        for text, cmd in [
            ("Delete Selected Event", self.delete_event),
            ("Export to CSV",         self.save_to_csv),
            ("? Controls",            self.show_instructions),
        ]:
            btn = tk.Button(sidebar, text=text, command=cmd,
                            bg=BG_DARK, fg=FG, activebackground=BG_HOVER,
                            activeforeground=FG, font=("Courier", 10),
                            relief=tk.RAISED, pady=5, bd=1)
            btn.pack(fill=tk.X, padx=8, pady=2)
            _hoverable(btn)

    def _build_main_area(self):
        left_frame = tk.Frame(self, bg="black")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Pack bottom-to-top
        self.status_label = tk.Label(
            left_frame, bg=BG_DARK, fg=FG, font=("Courier", 14), anchor="w", padx=8, pady=6
        )
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        self.tick_canvas = tk.Canvas(left_frame, height=10, bg=BG_DARK, highlightthickness=0)
        self.tick_canvas.pack(side=tk.BOTTOM, fill=tk.X)
        self.tick_canvas.bind("<Configure>", lambda _: self.redraw_ticks())

        self.scrubber = tk.Scale(
            left_frame, orient=tk.HORIZONTAL,
            from_=0, to=self.total_frames - 1,
            showvalue=0, command=self.on_scrub,
            bg=BG_DARK, troughcolor=SEP,
            highlightthickness=0, bd=0, sliderlength=12,
        )
        self.scrubber.pack(side=tk.BOTTOM, fill=tk.X)

        self.status_indicator = tk.Label(
            left_frame, text="Status: IDLE",
            bg=BG_DARK, fg=FG, font=("Courier", 14, "bold"),
            anchor="w", padx=8, pady=8,
        )
        self.status_indicator.pack(side=tk.BOTTOM, fill=tk.X)

        self.label = tk.Label(left_frame, bg="black")
        self.label.pack(fill=tk.BOTH, expand=True)

    def _bind_keys(self):
        self.bind("<Left>",      lambda _: self.step_frame(-1))
        self.bind("<Right>",     lambda _: self.step_frame(1))
        self.bind("<comma>",     lambda _: self.step_frame(-int(self.fps)))
        self.bind("<period>",    lambda _: self.step_frame(int(self.fps)))
        self.bind("s",           lambda _: self.log_start())
        self.bind("S",           lambda _: self.log_start())
        self.bind("d",           lambda _: self.log_stop())
        self.bind("D",           lambda _: self.log_stop())
        self.bind("<Delete>",    lambda _: self.delete_event())
        self.bind("<BackSpace>",  lambda _: self.delete_event())
        self.bind("<space>",      lambda _: self.toggle_play())
        self.bind("r",            lambda _: self.toggle_speed())
        self.bind("R",            lambda _: self.toggle_speed())
        self.bind("<Control-z>",  lambda _: self.undo_last_action())
        self.bind("<Command-z>",  lambda _: self.undo_last_action())

    # ── Navigation ────────────────────────────────────────────────────────────

    def toggle_play(self):
        self.is_playing = not self.is_playing
        if self.is_playing:
            self.play_loop()
        elif self.play_job is not None:
            self.after_cancel(self.play_job)
            self.play_job = None

    def play_loop(self):
        if not self.is_playing:
            return
        if self.current_frame >= self.total_frames - 1:
            self.is_playing = False
            self.play_job = None
            return
        self.current_frame += 1
        self._show_frame()
        self.play_job = self.after(int((1000 / self.fps) / self.playback_speed), self.play_loop)

    def toggle_speed(self):
        speeds = [1.0, 0.5, 0.25]
        self.playback_speed = speeds[(speeds.index(self.playback_speed) + 1) % len(speeds)]
        print(f">>> Playback speed set to {self.playback_speed}x")
        self._set_status()

    def _set_status(self):
        speed_tag = "" if self.playback_speed == 1.0 else f"  |  Speed: {self.playback_speed}x"
        if self.is_logging_swallow:
            self.status_indicator.config(text=f"● RECORDING SWALLOW{speed_tag}", fg=RED)
        else:
            self.status_indicator.config(text=f"Status: IDLE{speed_tag}", fg=FG)

    def on_event_click(self, _event):
        selected = self.tree.selection()
        if not selected:
            return
        tree_id = selected[0]
        swallow = next((e for e in self.swallow_events if e.get("tree_id") == tree_id), None)
        if swallow is None:
            return
        self.current_frame = swallow["start_frame"]
        self._show_frame()
        print(f">>> Jumping to Event #{swallow['num']} (Frame: {swallow['start_frame']})")
        self._flash_tick(swallow["start_frame"])

    def _flash_tick(self, frame):
        tag = f"START_{frame}"
        self.tick_canvas.itemconfig(tag, fill="black", width=3)
        self.after(600, lambda: self.tick_canvas.itemconfig(tag, fill=GREEN, width=2))

    def step_frame(self, count):
        self.current_frame = max(0, min(self.current_frame + count, self.total_frames - 1))
        self._show_frame()

    def on_scrub(self, value):
        if self._scrubber_sync:
            return
        self.current_frame = int(float(value))
        self._show_frame()

    # ── Logging ───────────────────────────────────────────────────────────────

    def log_start(self):
        if self.is_logging_swallow:
            print("Already logging — press D to mark STOP first.")
            return
        self.is_logging_swallow = True
        timestamp = self.current_frame / self.fps
        event_num = len(self.swallow_events) + 1

        swallow = {
            "num": event_num,
            "start_frame": self.current_frame,
            "start_time": timestamp,
            "stop_frame": None,
            "stop_time": None,
        }
        self.swallow_events.append(swallow)
        self.events.append({"frame": self.current_frame, "time": timestamp, "type": "START"})

        tree_id = self.tree.insert("", tk.END,
            values=(event_num, self._format_time(timestamp), "LOGGING...", "—"),
            tags=("in_progress",),
        )
        swallow["tree_id"] = tree_id
        self.tree.see(tree_id)

        if self.is_playing:
            self.toggle_play()
        print(f">>> [START] Frame {self.current_frame} | Time: {timestamp:.3f}s")
        self.draw_tick(self.current_frame, "START")
        self._set_status()
        self._blink()

    def log_stop(self):
        if not self.is_logging_swallow:
            print("No active swallow — press S to mark START first.")
            return
        self.is_logging_swallow = False
        if self.is_playing:
            self.toggle_play()
        timestamp = self.current_frame / self.fps

        swallow = self.swallow_events[-1]
        swallow["stop_frame"] = self.current_frame
        swallow["stop_time"] = timestamp
        duration = timestamp - swallow["start_time"]

        self.tree.item(swallow["tree_id"],
            values=(swallow["num"],
                    self._format_time(swallow["start_time"]),
                    self._format_time(timestamp),
                    f"{duration:.2f}s"),
            tags=("complete",),
        )
        self.tree.see(swallow["tree_id"])

        self.events.append({"frame": self.current_frame, "time": timestamp, "type": "STOP"})

        print(f">>> [STOP]  Frame {self.current_frame} | Time: {timestamp:.3f}s")
        print(f"    Event {swallow['num']} Summary: "
              f"{self._format_time(swallow['start_time'])} to {self._format_time(timestamp)} "
              f"| Total Duration: {duration:.2f}s")

        self.draw_tick(self.current_frame, "STOP")
        self._set_status()

    def undo_last_action(self):
        if not self.swallow_events:
            print(">>> Nothing to undo.")
            return

        swallow = self.swallow_events[-1]

        if swallow["stop_frame"] is None:
            # Open event — remove it entirely
            self.swallow_events.pop()
            self.tree.delete(swallow["tree_id"])
            self.is_logging_swallow = False
            print(f">>> Undo: removed open Event #{swallow['num']}.")
        else:
            # Closed event — re-open it: clear stop, restore in-progress state
            swallow["stop_frame"] = None
            swallow["stop_time"] = None
            self.is_logging_swallow = True
            self.tree.item(swallow["tree_id"],
                values=(swallow["num"], self._format_time(swallow["start_time"]), "LOGGING...", "—"),
                tags=("in_progress",),
            )
            self.tree.see(swallow["tree_id"])
            self._blink()
            print(f">>> Undo: re-opened Event #{swallow['num']} — waiting for STOP.")

        # Rebuild flat event list and sync timeline
        self.events = []
        for s in self.swallow_events:
            self.events.append({"frame": s["start_frame"], "time": s["start_time"], "type": "START"})
            if s["stop_frame"] is not None:
                self.events.append({"frame": s["stop_frame"], "time": s["stop_time"], "type": "STOP"})

        self.redraw_ticks()
        self._set_status()

    def delete_event(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Select an event in the sidebar first.")
            return

        tree_id = selected[0]
        swallow = next((e for e in self.swallow_events if e.get("tree_id") == tree_id), None)
        if swallow is None:
            return

        if not messagebox.askyesno("Confirm Delete",
                                   f"Delete Event #{swallow['num']}? This cannot be undone."):
            return

        if swallow["stop_frame"] is None:
            self.is_logging_swallow = False

        self.swallow_events.remove(swallow)
        self.tree.delete(tree_id)

        self.events = []
        for s in self.swallow_events:
            self.events.append({"frame": s["start_frame"], "time": s["start_time"], "type": "START"})
            if s["stop_frame"] is not None:
                self.events.append({"frame": s["stop_frame"], "time": s["stop_time"], "type": "STOP"})

        self.redraw_ticks()
        self._set_status()
        print(f">>> Event #{swallow['num']} deleted. Remaining events: {len(self.swallow_events)}")

    def save_to_csv(self):
        completed = [s for s in self.swallow_events if s["stop_frame"] is not None]
        if not completed:
            messagebox.showwarning("No Data", "No completed swallow events to export.")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Save swallow events",
        )
        if not path:
            return

        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Event_ID", "Start_Frame", "Stop_Frame",
                             "Start_Time_Sec", "Stop_Time_Sec", "Duration_Sec", "Video_Source"])
            source = os.path.basename(self.video_path)
            for s in completed:
                duration = (s["stop_frame"] - s["start_frame"]) / self.fps
                writer.writerow([
                    s["num"],
                    s["start_frame"],
                    s["stop_frame"],
                    round(s["start_time"], 4),
                    round(s["stop_time"], 4),
                    round(duration, 4),
                    source,
                ])

        messagebox.showinfo("Saved", f"Data saved successfully to {path}")
        print(f">>> Exported {len(completed)} events to {path}")

    def _blink(self):
        if not self.is_logging_swallow:
            return
        current_fg = self.status_indicator.cget("fg")
        self.status_indicator.config(fg=RED if current_fg == BG_DARK else BG_DARK)
        self.after(500, self._blink)

    # ── Tick Canvas ───────────────────────────────────────────────────────────

    def draw_tick(self, frame, event_type):
        canvas_w = self.tick_canvas.winfo_width()
        if canvas_w <= 1:
            return
        x = (frame / max(self.total_frames - 1, 1)) * canvas_w
        color = GREEN if event_type == "START" else RED
        self.tick_canvas.create_line(x, 0, x, 10, fill=color, width=2, tags=f"{event_type}_{frame}")

    def redraw_ticks(self):
        self.tick_canvas.delete("all")
        for event in self.events:
            self.draw_tick(event["frame"], event["type"])

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _show_frame(self):
        if self.cap is None:
            return
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
        ret, frame = self.cap.read()
        if not ret:
            print("Failed to grab frame")
            return

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)

        target_w, target_h = 800, 600
        img_w, img_h = img.size
        ratio = min(target_w / img_w, target_h / img_h)
        img = img.resize((int(img_w * ratio), int(img_h * ratio)), Image.Resampling.LANCZOS)

        self._photo = ImageTk.PhotoImage(img)
        self.label.config(image=self._photo)

        timestamp = self.current_frame / self.fps
        total_duration = self.total_frames / self.fps
        self.status_label.config(
            text=f"  Frame: {self.current_frame} / {self.total_frames - 1}"
                 f"  |  {self._format_time(timestamp)} / {self._format_time(total_duration)}"
        )

        self._scrubber_sync = True
        self.scrubber.set(self.current_frame)
        self._scrubber_sync = False

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _format_time(self, timestamp):
        minutes = int(timestamp // 60)
        seconds = timestamp % 60
        return f"{minutes:02d}:{seconds:05.2f}"

    def show_instructions(self):
        win = tk.Toplevel(self)
        win.title("Keyboard Shortcuts")
        win.geometry("320x450")
        win.resizable(False, False)
        win.configure(bg=BG)

        tk.Label(win, text="Controls", bg=BG, fg=FG,
                 font=("Courier", 13, "bold"), pady=12).pack()

        controls = [
            ("Space",         "Play / Pause"),
            ("→  /  ←",       "Step ±1 frame"),
            (".  /  ,",       "Skip ±1 second"),
            ("S",             "Mark START of swallow"),
            ("D",             "Mark STOP of swallow"),
            ("Click sidebar", "Jump to event"),
            ("Delete",        "Remove selected event"),
            ("Ctrl+Z",        "Undo last mark"),
            ("R",             "Toggle speed 1x→0.5x→0.25x"),
        ]

        frame = tk.Frame(win, bg=BG, padx=16)
        frame.pack(fill=tk.X)

        for key, desc in controls:
            row = tk.Frame(frame, bg=BG, pady=4)
            row.pack(fill=tk.X)
            tk.Label(row, text=f"{key:<14}", bg=BG, fg="#8b6914",
                     font=("Courier", 11), anchor="w", width=14).pack(side=tk.LEFT)
            tk.Label(row, text=desc, bg=BG, fg=FG,
                     font=("Courier", 11), anchor="w").pack(side=tk.LEFT)

        close_btn = tk.Button(win, text="Close", command=win.destroy,
                              bg=BG_DARK, fg=FG, activebackground=BG_HOVER,
                              font=("Courier", 10), relief=tk.RAISED, bd=1, pady=6)
        close_btn.pack(fill=tk.X, padx=16, pady=16)
        _hoverable(close_btn)

    def __del__(self):
        if hasattr(self, "cap"):
            self.cap.release()


if __name__ == "__main__":
    arg_path = sys.argv[1] if len(sys.argv) > 1 else None
    app = SwallowLabeler(arg_path)
    app.geometry("1100x700")
    app.mainloop()
