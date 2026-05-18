# Swallow Labeler

A desktop tool for manually annotating swallow events in video recordings.

## Video Tutorial
https://drive.google.com/file/d/17mh3YVx6ckWsswSk26-hhjuddndQVM-y/view?usp=sharing 

## Requirements

Python 3.9+ with the following packages:

```bash
pip install opencv-python pillow
```

Tkinter is included with Python on most systems. On macOS, if you see a deprecation warning about the system Tk, install a proper version:

```bash
brew install python-tk@3.9
```

## Running

```bash
# Open a specific video directly
python manual_labeler.py path/to/video.mov

# Open a file picker on launch
python manual_labeler.py
```

## Tag Configuration

Event types are loaded from `tags.txt` in the same directory as the script. Put one tag per line:

```
water
food
```

At least one tag is required — the app will show an error and exit if the file is missing or empty. Tags are assigned a distinct pastel row color in the sidebar automatically, cycling through up to 8 colors.

## Controls

### Keyboard

| Key | Action |
|-----|--------|
| `Space` | Play / Pause |
| `→` / `←` | Step ±1 frame |
| `.` / `,` | Skip ±1 second |
| `S` | Mark START of swallow |
| `D` | Mark STOP of swallow |
| `Ctrl+Z` | Undo last mark (re-opens a finished event) |
| `Delete` / `Backspace` | Remove selected event |
| `Escape` | Reset zoom and re-center view |
| Mouse wheel | Zoom in / out (up to 5x) |
| Click + drag | Pan when zoomed in |

### On-Screen Transport Panel

Located directly above the scrubber:

| Button | Action |
|--------|--------|
| ⏪ -1s | Skip back 1 second |
| ◀ -1f | Step back 1 frame |
| ▶ Play / ⏸ Pause | Toggle playback (text and color update on state change) |
| +1f ▶ | Step forward 1 frame |
| +1s ⏩ | Skip forward 1 second |

### Sidebar

| Action | Result |
|--------|--------|
| Click a row | Jump video to that event's start frame |
| Click the **Tag ✎** cell | Open an in-place dropdown to change the event tag |

## Workflow

1. Open a video (via command line or the **📁 Open Video** button).
2. Play or scrub to a swallow event. Use the transport panel or keyboard shortcuts.
3. Press **S** to mark the start, then **D** to mark the stop. Playback stops automatically when you mark.
4. Repeat. Each completed event appears in the sidebar color-coded by tag category.
5. Click a **Tag ✎** cell to reassign the event type inline.
6. Use **Ctrl+Z** to re-open or remove the last event if you make a mistake.
7. Click **Export to CSV** when done.

## Zoom and Pan

- Scroll the mouse wheel over the video to zoom in (max 5x). The view fills the container — no black bars at zoom > 1x.
- Click and drag to pan when zoomed.
- A **mini-map** appears in the top-right corner of the video at zoom > 1x, showing your current viewport as a red rectangle. Click anywhere on the mini-map to jump the view.
- Press **Escape** to reset zoom and re-center.

## Output

The CSV contains one row per completed event:

| Column | Description |
|--------|-------------|
| `Event_ID` | Sequential event number |
| `Start_Frame` | Frame index of swallow onset |
| `Stop_Frame` | Frame index of swallow offset |
| `Start_Time_Sec` | Onset time in seconds |
| `Stop_Time_Sec` | Offset time in seconds |
| `Duration_Sec` | `(Stop_Frame - Start_Frame) / FPS` |
| `Tag` | Event category from `tags.txt` |
| `Video_Source` | Filename of the source video |
