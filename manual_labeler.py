import tkinter as tk
from tkinter import messagebox
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
        self.events = []
        self.is_logging_swallow = False
        self._scrubber_sync = False

        # Sidebar (pack first to claim the right edge before left_frame expands)
        sidebar = tk.Frame(self, bg="#1e1e1e", width=200)
        sidebar.pack(side=tk.RIGHT, fill=tk.Y)
        sidebar.pack_propagate(False)

        tk.Label(sidebar, text="Logged Events", bg="#1e1e1e", fg="white",
                 font=("Courier", 12, "bold"), pady=8).pack()

        scrollbar = tk.Scrollbar(sidebar)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.event_listbox = tk.Listbox(
            sidebar, yscrollcommand=scrollbar.set,
            bg="#2b2b2b", fg="white", font=("Courier", 11),
            selectbackground="#444", bd=0, highlightthickness=0,
        )
        self.event_listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.event_listbox.yview)

        # Left frame: video + scrubber + status bar
        left_frame = tk.Frame(self, bg="black")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Pack order (BOTTOM stacks upward): status → ticks → scrubber → video
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

        self.label = tk.Label(left_frame, bg="black")
        self.label.pack(fill=tk.BOTH, expand=True)

        self.bind("<Left>", lambda _: self.step_frame(-1))
        self.bind("<Right>", lambda _: self.step_frame(1))
        self.bind("<comma>", lambda _: self.step_frame(-int(self.fps)))
        self.bind("<period>", lambda _: self.step_frame(int(self.fps)))
        self.bind("s", lambda _: self.log_start())
        self.bind("S", lambda _: self.log_start())
        self.bind("d", lambda _: self.log_stop())
        self.bind("D", lambda _: self.log_stop())

        self.after(100, self._show_frame)

    def step_frame(self, count):
        self.current_frame = max(0, min(self.current_frame + count, self.total_frames - 1))
        self._show_frame()

    def on_scrub(self, value):
        if self._scrubber_sync:
            return
        self.current_frame = int(float(value))
        self._show_frame()

    def _format_time(self, timestamp):
        minutes = int(timestamp // 60)
        seconds = timestamp % 60
        return f"{minutes:02d}:{seconds:05.2f}"

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

    def log_start(self):
        if self.is_logging_swallow:
            print("Already logging — press D to mark STOP first.")
            return
        self.is_logging_swallow = True
        timestamp = self.current_frame / self.fps
        self.events.append({"frame": self.current_frame, "time": timestamp, "type": "START"})
        print(f">>> [START] Frame {self.current_frame} | Time: {timestamp:.3f}s")
        self.event_listbox.insert(tk.END, f"  [START] {self._format_time(timestamp)}  -  Frame {self.current_frame}")
        self.event_listbox.itemconfig(tk.END, fg="#00dd66")
        self.event_listbox.see(tk.END)
        self.draw_tick(self.current_frame, "START")

    def log_stop(self):
        if not self.is_logging_swallow:
            print("No active swallow — press S to mark START first.")
            return
        self.is_logging_swallow = False
        timestamp = self.current_frame / self.fps
        self.events.append({"frame": self.current_frame, "time": timestamp, "type": "STOP"})
        print(f">>> [STOP]  Frame {self.current_frame} | Time: {timestamp:.3f}s")
        self.event_listbox.insert(tk.END, f"  [STOP]  {self._format_time(timestamp)}  -  Frame {self.current_frame}")
        self.event_listbox.itemconfig(tk.END, fg="#ff5555")
        self.event_listbox.see(tk.END)
        self.draw_tick(self.current_frame, "STOP")

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

    def __del__(self):
        if hasattr(self, "cap"):
            self.cap.release()


if __name__ == "__main__":
    import os
    video_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test.MOV")
    app = SwallowLabeler(video_path)
    app.geometry("900x700")
    app.mainloop()
