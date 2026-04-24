import tkinter as tk
from tkinter import ttk, messagebox
import cv2
from PIL import Image, ImageTk


class SwallowLabeler(tk.Tk):
    def __init__(self, video_path):
        super().__init__()
        self.title("Swallow Labeler")

        self.cap = cv2.VideoCapture(video_path)
        if not self.cap.isOpened():
            messagebox.showerror("Error", f"Cannot open video: {video_path}")
            self.destroy()
            return

        self.current_frame = 0
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.events = []          # flat list used by tick canvas and CSV export
        self.swallow_events = []  # paired start/stop records for the Treeview
        self.is_logging_swallow = False
        self._scrubber_sync = False

        self._build_styles()
        self._build_sidebar()
        self._build_main_area()
        self._bind_keys()

        self.after(100, self._show_frame)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview",
            background="#2b2b2b", foreground="white",
            fieldbackground="#2b2b2b", rowheight=22,
            font=("Courier", 10),
        )
        style.configure("Treeview.Heading",
            background="#1e1e1e", foreground="#aaaaaa",
            font=("Courier", 10, "bold"),
        )
        style.map("Treeview", background=[("selected", "#444444")])

    def _build_sidebar(self):
        sidebar = tk.Frame(self, bg="#1e1e1e", width=240)
        sidebar.pack(side=tk.RIGHT, fill=tk.Y)
        sidebar.pack_propagate(False)

        tk.Label(sidebar, text="Swallow Events", bg="#1e1e1e", fg="white",
                 font=("Courier", 12, "bold"), pady=8).pack()

        tree_frame = tk.Frame(sidebar, bg="#1e1e1e")
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

        self.tree.tag_configure("in_progress", background="#3a3000", foreground="#ffdd00")
        self.tree.tag_configure("complete", background="#1a3a1a", foreground="#00dd66")

        self.tree.pack(fill=tk.BOTH, expand=True)

    def _build_main_area(self):
        left_frame = tk.Frame(self, bg="black")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Pack bottom-to-top so expanding video label fills whatever remains
        self.status_label = tk.Label(
            left_frame, bg="#222222", fg="white", font=("Courier", 11), anchor="w", padx=8
        )
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        self.tick_canvas = tk.Canvas(left_frame, height=10, bg="#333333", highlightthickness=0)
        self.tick_canvas.pack(side=tk.BOTTOM, fill=tk.X)
        self.tick_canvas.bind("<Configure>", lambda _: self.redraw_ticks())

        self.scrubber = tk.Scale(
            left_frame, orient=tk.HORIZONTAL,
            from_=0, to=self.total_frames - 1,
            showvalue=0, command=self.on_scrub,
            bg="#333333", troughcolor="#555555",
            highlightthickness=0, bd=0, sliderlength=12,
        )
        self.scrubber.pack(side=tk.BOTTOM, fill=tk.X)

        self.status_indicator = tk.Label(
            left_frame, text="Status: IDLE",
            bg="#111111", fg="white", font=("Courier", 11, "bold"),
            anchor="w", padx=8, pady=3,
        )
        self.status_indicator.pack(side=tk.BOTTOM, fill=tk.X)

        self.label = tk.Label(left_frame, bg="black")
        self.label.pack(fill=tk.BOTH, expand=True)

    def _bind_keys(self):
        self.bind("<Left>",   lambda _: self.step_frame(-1))
        self.bind("<Right>",  lambda _: self.step_frame(1))
        self.bind("<comma>",  lambda _: self.step_frame(-int(self.fps)))
        self.bind("<period>", lambda _: self.step_frame(int(self.fps)))
        self.bind("s", lambda _: self.log_start())
        self.bind("S", lambda _: self.log_start())
        self.bind("d", lambda _: self.log_stop())
        self.bind("D", lambda _: self.log_stop())

    # ── Navigation ────────────────────────────────────────────────────────────

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

        print(f">>> [START] Frame {self.current_frame} | Time: {timestamp:.3f}s")
        self.draw_tick(self.current_frame, "START")
        self.status_indicator.config(text="● RECORDING SWALLOW", fg="#ff3333")
        self._blink()

    def log_stop(self):
        if not self.is_logging_swallow:
            print("No active swallow — press S to mark START first.")
            return
        self.is_logging_swallow = False
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
        self.status_indicator.config(text="Status: IDLE", fg="white")

    def _blink(self):
        if not self.is_logging_swallow:
            return
        current_fg = self.status_indicator.cget("fg")
        self.status_indicator.config(fg="#ff3333" if current_fg == "#111111" else "#111111")
        self.after(500, self._blink)

    # ── Tick Canvas ───────────────────────────────────────────────────────────

    def draw_tick(self, frame, event_type):
        canvas_w = self.tick_canvas.winfo_width()
        if canvas_w <= 1:
            return
        x = (frame / max(self.total_frames - 1, 1)) * canvas_w
        color = "#00dd66" if event_type == "START" else "#ff5555"
        self.tick_canvas.create_line(x, 0, x, 10, fill=color, width=2, tags=f"{event_type}_{frame}")

    def redraw_ticks(self):
        self.tick_canvas.delete("all")
        for event in self.events:
            self.draw_tick(event["frame"], event["type"])

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _show_frame(self):
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

    def __del__(self):
        if hasattr(self, "cap"):
            self.cap.release()


if __name__ == "__main__":
    import os
    video_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test.MOV")
    app = SwallowLabeler(video_path)
    app.geometry("1100x700")
    app.mainloop()
