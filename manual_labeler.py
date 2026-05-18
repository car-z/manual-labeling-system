import os
import sys
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import csv
import cv2
from PIL import Image, ImageTk

# ── Palette ───────────────────────────────────────────────────────────────────
BG        = "#f0f0f0"
BG_DARK   = "#e1e1e1"
BG_HOVER  = "#c8c8c8"
FG        = "#111111"
FG_DIM    = "#555555"
SEP       = "#cccccc"
GREEN     = "#228B22"
RED       = "#cc2222"
AMBER_BG  = "#fff8dc"
AMBER_FG  = "#7a5800"
GREEN_BG  = "#e8f5e9"

MM_W, MM_H = 150, 110

# Pastel background colours cycled across tag categories (dark FG assumed)
TAG_COLORS = [
    "#E3F2FD",  # soft blue
    "#FCE4EC",  # soft rose
    "#E8F5E9",  # soft green
    "#FFF9C4",  # soft yellow
    "#F3E5F5",  # soft lavender
    "#FBE9E7",  # soft peach
    "#E0F7FA",  # soft cyan
    "#F1F8E9",  # soft lime
]


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
        self.play_btn = None          # transport panel center button
        self.playback_start_time = 0.0
        self.playback_start_frame = 0

        # Zoom / pan state (normalized coordinates)
        self.zoom_level = 1.0
        self.pan_x = 0.5
        self.pan_y = 0.5
        self._drag_last_x = 0
        self._drag_last_y = 0
        self._mm_thumb_size = (MM_W, MM_H)
        self.frame_w = 1
        self.frame_h = 1
        self._view_x0 = 0.0
        self._view_x1 = 1.0
        self._view_y0 = 0.0
        self._view_y1 = 1.0

        # Tags
        self.tag_options = self._load_tag_options()
        self._suppress_jump = False   # prevents frame-jump when auto-selecting a row
        self._inline_combo = None     # floating in-cell combobox, when active

        self._build_styles()
        self._build_sidebar()
        self._build_main_area()
        self._bind_keys()

        self.after(100, lambda: self.load_video(video_path))

    # ── Tag Config ────────────────────────────────────────────────────────────

    def _load_tag_options(self):
        tags_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tags.txt")
        if os.path.exists(tags_path):
            with open(tags_path, "r") as f:
                tags = [line.strip() for line in f if line.strip()]
            if tags:
                return tags
        msg = (
            "tags.txt must contain at least one tag (one per line).\n\n"
            f"Expected location: {tags_path}"
        )
        print(f"ERROR: {msg}")
        messagebox.showerror("Missing Tags", msg)
        self.destroy()
        sys.exit(1)

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
        self.frame_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        self.current_frame = 0
        self.events = []
        self.swallow_events = []
        self.is_logging_swallow = False
        self.zoom_level = 1.0
        self.pan_x = 0.5
        self.pan_y = 0.5
        if self.is_playing:
            self.is_playing = False
            if self.play_job:
                self.after_cancel(self.play_job)
                self.play_job = None

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
        sidebar = tk.Frame(self, bg=BG, width=265)
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
            columns=("num", "start", "stop", "duration", "tag"),
            show="headings",
            yscrollcommand=scrollbar.set,
        )
        scrollbar.config(command=self.tree.yview)

        self.tree.heading("num",      text="#")
        self.tree.heading("start",    text="Start")
        self.tree.heading("stop",     text="Stop")
        self.tree.heading("duration", text="Dur.")
        self.tree.heading("tag",      text="Tag  ✎")
        self.tree.column("num",      width=22,  anchor="center", stretch=False)
        self.tree.column("start",    width=50,  anchor="center", stretch=False)
        self.tree.column("stop",     width=50,  anchor="center", stretch=False)
        self.tree.column("duration", width=42,  anchor="center", stretch=False)
        self.tree.column("tag",      width=68,  anchor="center", stretch=True)

        self.tree.tag_configure("in_progress", background=AMBER_BG, foreground=AMBER_FG)
        # Per-category colour tags — one per line in tags.txt, cycling the palette
        for i, opt in enumerate(self.tag_options):
            self.tree.tag_configure(
                f"cat_{opt}",
                background=TAG_COLORS[i % len(TAG_COLORS)],
                foreground=FG,
            )

        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_event_click)
        self.tree.bind("<Button-1>",         self.on_tree_click)

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

        # ── Transport control panel ────────────────────────────────────────────
        ctrl = tk.Frame(left_frame, bg=BG_DARK, pady=2)
        ctrl.pack(side=tk.BOTTOM, fill=tk.X)

        # Inner frame so the button cluster sits centered rather than left-flush
        btn_row = tk.Frame(ctrl, bg=BG_DARK)
        btn_row.pack(expand=True)

        btn_cfg = dict(bg=BG_DARK, fg=FG,
                       activebackground=BG_DARK, activeforeground=FG,
                       font=("Courier", 11),
                       relief=tk.FLAT, bd=0, highlightthickness=0,
                       pady=2)

        btn_prev_1s = tk.Button(btn_row, text="⏪ -1s",
                                command=lambda: self.step_frame(-int(self.fps)), **btn_cfg)
        btn_prev_1f = tk.Button(btn_row, text="◀ -1f",
                                command=lambda: self.step_frame(-1), **btn_cfg)

        self.play_btn = tk.Button(btn_row, text="▶ Play",
                                  command=self.toggle_play,
                                  bg=BG_DARK, fg=FG,
                                  activebackground=BG_DARK, activeforeground=FG,
                                  font=("Courier", 11, "bold"),
                                  relief=tk.FLAT, bd=0, highlightthickness=0,
                                  pady=2)

        btn_next_1f = tk.Button(btn_row, text="+1f ▶",
                                command=lambda: self.step_frame(1), **btn_cfg)
        btn_next_1s = tk.Button(btn_row, text="+1s ⏩",
                                command=lambda: self.step_frame(int(self.fps)), **btn_cfg)

        for btn in (btn_prev_1s, btn_prev_1f, self.play_btn, btn_next_1f, btn_next_1s):
            _hoverable(btn, normal=BG_DARK, hover=BG_HOVER)

        btn_prev_1s.pack(side=tk.LEFT, padx=10, pady=2)
        btn_prev_1f.pack(side=tk.LEFT, padx=10, pady=2)
        self.play_btn.pack(side=tk.LEFT, padx=15, pady=2)
        btn_next_1f.pack(side=tk.LEFT, padx=10, pady=2)
        btn_next_1s.pack(side=tk.LEFT, padx=10, pady=2)
        # ── End transport panel ───────────────────────────────────────────────

        self.status_indicator = tk.Label(
            left_frame, text="Status: IDLE",
            bg=BG_DARK, fg=FG, font=("Courier", 14, "bold"),
            anchor="w", padx=8, pady=8,
        )
        self.status_indicator.pack(side=tk.BOTTOM, fill=tk.X)

        video_container = tk.Frame(left_frame, bg="black")
        video_container.pack(fill=tk.BOTH, expand=True)

        self.label = tk.Label(video_container, bg="black")
        self.label.pack(fill=tk.BOTH, expand=True)

        self.minimap = tk.Canvas(
            video_container, width=MM_W, height=MM_H,
            bg="#1a1a1a", highlightthickness=2, highlightbackground="yellow",
            cursor="crosshair",
        )
        self.minimap.bind("<Button-1>", self._on_minimap_click)

    def _bind_keys(self):
        self.bind("<Left>",       lambda _: self.step_frame(-1))
        self.bind("<Right>",      lambda _: self.step_frame(1))
        self.bind("<comma>",      lambda _: self.step_frame(-int(self.fps)))
        self.bind("<period>",     lambda _: self.step_frame(int(self.fps)))
        self.bind("s",            lambda _: self.log_start())
        self.bind("S",            lambda _: self.log_start())
        self.bind("d",            lambda _: self.log_stop())
        self.bind("D",            lambda _: self.log_stop())
        self.bind("<Delete>",     lambda _: self.delete_event())
        self.bind("<BackSpace>",  lambda _: self.delete_event())
        self.bind("<space>",      lambda _: self.toggle_play())
        self.bind("<Control-z>",  lambda _: self.undo_last_action())
        self.bind("<Command-z>",  lambda _: self.undo_last_action())
        self.bind("<Escape>",     lambda _: self._reset_zoom())

        self.label.bind("<MouseWheel>",    self._on_zoom)
        self.label.bind("<ButtonPress-1>", self._on_pan_start)
        self.label.bind("<B1-Motion>",     self._on_pan_move)

    # ── Navigation ────────────────────────────────────────────────────────────

    def toggle_play(self):
        self.is_playing = not self.is_playing
        if self.is_playing:
            self.playback_start_time  = time.time()
            self.playback_start_frame = self.current_frame
            self._sync_play_btn(playing=True)
            self.play_loop()
        else:
            if self.play_job is not None:
                self.after_cancel(self.play_job)
                self.play_job = None
            self._sync_play_btn(playing=False)

    def _sync_play_btn(self, playing):
        if self.play_btn is None:
            return
        if playing:
            self.play_btn.config(text="⏸ Pause", fg=GREEN, activeforeground=GREEN)
        else:
            self.play_btn.config(text="▶ Play", fg=FG, activeforeground=FG)

    def play_loop(self):
        if not self.is_playing:
            return

        elapsed = time.time() - self.playback_start_time
        target_frame = int(self.playback_start_frame + elapsed * self.fps)
        target_frame = min(target_frame, self.total_frames - 1)

        if target_frame >= self.total_frames - 1:
            self.current_frame = self.total_frames - 1
            self._show_frame()
            self.is_playing = False
            self.play_job = None
            self._sync_play_btn(playing=False)
            return

        if target_frame != self.current_frame:
            self.current_frame = target_frame
            self._show_frame()

        self.play_job = self.after(5, self.play_loop)

    def _set_status(self):
        zoom_tag = f"  |  Zoom: {self.zoom_level:.2f}x" if self.zoom_level > 1.0 else ""
        if self.is_logging_swallow:
            self.status_indicator.config(text=f"● RECORDING SWALLOW{zoom_tag}", fg=RED)
        else:
            self.status_indicator.config(text=f"Status: IDLE{zoom_tag}", fg=FG)

    def on_event_click(self, *_):
        selected = self.tree.selection()
        if not selected:
            return
        tree_id = selected[0]
        swallow = next((e for e in self.swallow_events if e.get("tree_id") == tree_id), None)
        if swallow is None:
            return
        if not self._suppress_jump:
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

    # ── In-Cell Tag Editor ────────────────────────────────────────────────────

    def on_tree_click(self, event):
        # Only act on clicks in the Tag column cell region
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) != "#5":
            return
        item = self.tree.identify_row(event.y)
        if not item:
            return
        swallow = next((e for e in self.swallow_events if e.get("tree_id") == item), None)
        if swallow is None:
            return

        bbox = self.tree.bbox(item, "#5")
        if not bbox:
            return
        x, y, w, h = bbox

        # Dismiss any stale inline editor before creating a new one
        self._cancel_inline_tag()

        current_tag = swallow.get("tag", self.tag_options[0])
        self._inline_item = item
        self._inline_var  = tk.StringVar()

        combo = ttk.Combobox(self.tree, textvariable=self._inline_var,
                             state="readonly", font=("Courier", 10))
        # Pre-populate and set value BEFORE placing so the widget is fully
        # initialised — this prevents the blank-dropdown symptom.
        combo["values"] = self.tag_options
        combo.set(current_tag)
        combo.place(x=x, y=y, width=w, height=h)
        combo.focus_set()
        self._inline_combo = combo

        # Simulate a click on the combo arrow to open the list immediately.
        # Capture `combo` in the closure so a rapid second click can't destroy
        # a *different* widget than the one this callback belongs to.
        combo.after(10, lambda: combo.event_generate("<Button-1>")
                                if self._inline_combo is combo else None)

        combo.bind("<<ComboboxSelected>>", lambda _: self._commit_inline_tag())
        combo.bind("<Return>",             lambda _: self._commit_inline_tag())
        combo.bind("<Escape>",             lambda _: self._cancel_inline_tag())
        # after_idle lets <<ComboboxSelected>> win the race; the closure-
        # captured `combo` ref ensures we never destroy a newer editor.
        combo.bind("<FocusOut>",
                   lambda _: self.after_idle(lambda: self._cancel_if_still(combo)))

        # Stop the event reaching the Treeview class handler (row select →
        # <<TreeviewSelect>> → unwanted frame jump).
        return "break"

    def _commit_inline_tag(self):
        if self._inline_combo is None:
            return
        new_tag = self._inline_var.get()
        item    = self._inline_item
        self._inline_combo.destroy()
        self._inline_combo = None

        swallow = next((e for e in self.swallow_events if e.get("tree_id") == item), None)
        if swallow is None:
            return
        swallow["tag"] = new_tag
        self._refresh_tree_row(swallow)

    def _cancel_inline_tag(self):
        if self._inline_combo is None:
            return
        self._inline_combo.destroy()
        self._inline_combo = None

    def _cancel_if_still(self, combo_ref):
        """Only cancel if the stored combo is still the one we were watching."""
        if self._inline_combo is combo_ref:
            self._cancel_inline_tag()

    def _refresh_tree_row(self, swallow):
        tid = swallow["tree_id"]
        if swallow["stop_frame"] is None:
            self.tree.item(tid,
                values=(swallow["num"],
                        self._format_time(swallow["start_time"]),
                        "LOGGING...", "—",
                        swallow["tag"]),
                tags=("in_progress",),
            )
        else:
            duration = swallow["stop_time"] - swallow["start_time"]
            self.tree.item(tid,
                values=(swallow["num"],
                        self._format_time(swallow["start_time"]),
                        self._format_time(swallow["stop_time"]),
                        f"{duration:.2f}s",
                        swallow["tag"]),
                tags=(f"cat_{swallow['tag']}",),
            )

    # ── Zoom / Pan ────────────────────────────────────────────────────────────

    def _on_zoom(self, event):
        if event.delta > 0:
            self.zoom_level = min(5.0, round(self.zoom_level + 0.1, 1))
        else:
            self.zoom_level = max(1.0, round(self.zoom_level - 0.1, 1))
        self._set_status()
        self._show_frame()

    def _on_pan_start(self, event):
        self._drag_last_x = event.x
        self._drag_last_y = event.y

    def _on_pan_move(self, event):
        if self.zoom_level <= 1.0 or self.frame_w <= 1:
            return
        target_w = self.label.winfo_width()
        target_h = self.label.winfo_height()
        if target_w <= 1 or target_h <= 1:
            return

        dx = event.x - self._drag_last_x
        dy = event.y - self._drag_last_y
        self._drag_last_x = event.x
        self._drag_last_y = event.y

        crop_w_px = self.frame_w / self.zoom_level
        crop_h_px = self.frame_h / self.zoom_level
        scale = max(target_w / crop_w_px, target_h / crop_h_px)

        self.pan_x -= dx / (scale * self.frame_w)
        self.pan_y -= dy / (scale * self.frame_h)
        self.pan_x = max(0.0, min(1.0, self.pan_x))
        self.pan_y = max(0.0, min(1.0, self.pan_y))
        self._show_frame()

    def _reset_zoom(self):
        self.zoom_level = 1.0
        self.pan_x = 0.5
        self.pan_y = 0.5
        self._set_status()
        self._show_frame()

    # ── Mini-Map ──────────────────────────────────────────────────────────────

    def _update_minimap(self, full_img):
        if self.zoom_level <= 1.0:
            self.minimap.place_forget()
            return

        thumb = full_img.copy()
        thumb.thumbnail((MM_W, MM_H), Image.Resampling.LANCZOS)
        t_w, t_h = thumb.size
        self._mm_thumb_size = (t_w, t_h)
        off_x = (MM_W - t_w) // 2
        off_y = (MM_H - t_h) // 2

        self.minimap.delete("all")
        self._mm_photo = ImageTk.PhotoImage(thumb)
        self.minimap.create_image(off_x, off_y, anchor="nw", image=self._mm_photo)

        rx1 = max(off_x,       off_x + self._view_x0 * t_w)
        ry1 = max(off_y,       off_y + self._view_y0 * t_h)
        rx2 = min(off_x + t_w, off_x + self._view_x1 * t_w)
        ry2 = min(off_y + t_h, off_y + self._view_y1 * t_h)
        self.minimap.create_rectangle(rx1, ry1, rx2, ry2, outline="red", width=2)

        self.minimap.place(relx=1.0, rely=0.0, anchor="ne", x=-5, y=5)

    def _on_minimap_click(self, event):
        t_w, t_h = self._mm_thumb_size
        off_x = (MM_W - t_w) // 2
        off_y = (MM_H - t_h) // 2
        tx = event.x - off_x
        ty = event.y - off_y
        if not (0 <= tx <= t_w and 0 <= ty <= t_h):
            return
        half_w = 0.5 / self.zoom_level
        half_h = 0.5 / self.zoom_level
        self.pan_x = max(half_w, min(1.0 - half_w, tx / t_w))
        self.pan_y = max(half_h, min(1.0 - half_h, ty / t_h))
        self._show_frame()

    # ── Logging ───────────────────────────────────────────────────────────────

    def log_start(self):
        if self.is_logging_swallow:
            print("Already logging — press D to mark STOP first.")
            return
        self.is_logging_swallow = True
        timestamp = self.current_frame / self.fps
        event_num = len(self.swallow_events) + 1
        default_tag = self.tag_options[0] if self.tag_options else "Unlabeled"

        swallow = {
            "num":         event_num,
            "start_frame": self.current_frame,
            "start_time":  timestamp,
            "stop_frame":  None,
            "stop_time":   None,
            "tag":         default_tag,
        }
        self.swallow_events.append(swallow)
        self.events.append({"frame": self.current_frame, "time": timestamp, "type": "START"})

        tree_id = self.tree.insert("", tk.END,
            values=(event_num, self._format_time(timestamp), "LOGGING...", "—", default_tag),
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
        swallow["stop_time"]  = timestamp
        duration = timestamp - swallow["start_time"]

        self._refresh_tree_row(swallow)
        self.tree.see(swallow["tree_id"])
        self.events.append({"frame": self.current_frame, "time": timestamp, "type": "STOP"})

        print(f">>> [STOP]  Frame {self.current_frame} | Time: {timestamp:.3f}s")
        print(f"    Event {swallow['num']} Summary: "
              f"{self._format_time(swallow['start_time'])} to {self._format_time(timestamp)} "
              f"| Total Duration: {duration:.2f}s")

        self.draw_tick(self.current_frame, "STOP")
        self._set_status()

        # Highlight the completed row without jumping to its start frame.
        # Reset the flag via after_idle so it stays True for the full dispatch
        # of the <<TreeviewSelect>> virtual event (which Tk may queue rather
        # than fire synchronously inside selection_set).
        self._suppress_jump = True
        self.tree.selection_set(swallow["tree_id"])
        self.after_idle(lambda: setattr(self, '_suppress_jump', False))

    def undo_last_action(self):
        if not self.swallow_events:
            print(">>> Nothing to undo.")
            return

        swallow = self.swallow_events[-1]

        if swallow["stop_frame"] is None:
            self.swallow_events.pop()
            self.tree.delete(swallow["tree_id"])
            self.is_logging_swallow = False
            print(f">>> Undo: removed open Event #{swallow['num']}.")
        else:
            swallow["stop_frame"] = None
            swallow["stop_time"]  = None
            self.is_logging_swallow = True
            self._refresh_tree_row(swallow)
            self.tree.see(swallow["tree_id"])
            self._blink()
            print(f">>> Undo: re-opened Event #{swallow['num']} — waiting for STOP.")

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
                             "Start_Time_Sec", "Stop_Time_Sec", "Duration_Sec",
                             "Tag", "Video_Source"])
            source = os.path.basename(self.video_path)
            for s in completed:
                duration = (s["stop_frame"] - s["start_frame"]) / self.fps
                writer.writerow([
                    s["num"],
                    s["start_frame"],
                    s["stop_frame"],
                    round(s["start_time"], 4),
                    round(s["stop_time"],  4),
                    round(duration,        4),
                    s.get("tag", ""),
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
        full_img = Image.fromarray(frame_rgb)
        img_w, img_h = full_img.size

        if self.zoom_level > 1.0:
            crop_w = img_w / self.zoom_level
            crop_h = img_h / self.zoom_level
            left = max(0.0, min(img_w - crop_w, self.pan_x * img_w - crop_w / 2))
            top  = max(0.0, min(img_h - crop_h, self.pan_y * img_h - crop_h / 2))
            self.pan_x = (left + crop_w / 2) / img_w
            self.pan_y = (top  + crop_h / 2) / img_h
            display_img = full_img.crop(
                (int(left), int(top), int(left + crop_w), int(top + crop_h))
            )
        else:
            display_img = full_img

        target_w = self.label.winfo_width()
        target_h = self.label.winfo_height()
        if target_w <= 1: target_w = 800
        if target_h <= 1: target_h = 600

        dw, dh = display_img.size
        if self.zoom_level > 1.0:
            scale = max(target_w / dw, target_h / dh)
            vis_frac_x = min(1.0, target_w / (scale * dw))
            vis_frac_y = min(1.0, target_h / (scale * dh))
            half_x = vis_frac_x / (2.0 * self.zoom_level)
            half_y = vis_frac_y / (2.0 * self.zoom_level)
            self._view_x0 = max(0.0, self.pan_x - half_x)
            self._view_x1 = min(1.0, self.pan_x + half_x)
            self._view_y0 = max(0.0, self.pan_y - half_y)
            self._view_y1 = min(1.0, self.pan_y + half_y)
        else:
            scale = min(target_w / dw, target_h / dh)
            self._view_x0, self._view_x1 = 0.0, 1.0
            self._view_y0, self._view_y1 = 0.0, 1.0

        display_img = display_img.resize(
            (int(dw * scale), int(dh * scale)), Image.Resampling.LANCZOS
        )

        self._photo = ImageTk.PhotoImage(display_img)
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

        self._update_minimap(full_img)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _format_time(self, timestamp):
        minutes = int(timestamp // 60)
        seconds = timestamp % 60
        return f"{minutes:02d}:{seconds:05.2f}"

    def show_instructions(self):
        win = tk.Toplevel(self)
        win.title("Keyboard Shortcuts")
        win.geometry("360x640")
        win.resizable(False, False)
        win.configure(bg=BG)

        tk.Label(win, text="Controls", bg=BG, fg=FG,
                 font=("Courier", 13, "bold"), pady=12).pack()

        controls = [
            ("Space",         "Play / Pause"),
            ("▶ Play button", "Play / Pause (on-screen)"),
            ("⏪ / ⏩",        "Skip ±1 second (on-screen)"),
            ("◀ / ▶",         "Step ±1 frame (on-screen)"),
            ("→  /  ←",       "Step ±1 frame (keyboard)"),
            (".  /  ,",       "Skip ±1 second (keyboard)"),
            ("S",             "Mark START of swallow"),
            ("D",             "Mark STOP of swallow"),
            ("Click Tag cell","Edit event type in-place"),
            ("Click sidebar", "Jump to event start"),
            ("Delete",        "Remove selected event"),
            ("Ctrl+Z",        "Undo last mark"),
            ("Wheel",         "Zoom in / out (max 5x)"),
            ("Click-Drag",    "Pan when zoomed"),
            ("Escape",        "Reset zoom & center view"),
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
