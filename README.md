# Swallow Labeler

A desktop tool for manually annotating swallow events in video recordings.

## Requirements

Python 3.9+ with the following packages:

```bash
pip install opencv-python pillow
```

Tkinter is included with Python on most systems. On macOS, if you see a deprecation warning about the system Tk, install a proper version (I had this issue and had to fix):

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

## Controls

| Key | Action |
|-----|--------|
| `Space` | Play / Pause |
| `→` / `←` | Step ±1 frame |
| `.` / `,` | Skip ±1 second |
| `S` | Mark START of swallow |
| `D` | Mark STOP of swallow |
| `Ctrl+Z` | Undo last mark (re-opens a finished event) |
| `R` | Toggle playback speed (1x → 0.5x → 0.25x) |
| Click sidebar row | Jump video to that event's start frame |
| `Delete` | Remove selected event |

## Workflow

1. Open a video (via command line or the **📁 Open Video** button).
2. Play or scrub to a swallow event.
3. Press **S** to mark the start, then **D** to mark the stop.
4. Repeat. Each completed event appears in the sidebar with its start time, stop time, and duration.
5. Use **Ctrl+Z** to re-open or remove the last event if you make a mistake.
6. Click **Export to CSV** when done.

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
| `Video_Source` | Filename of the source video |
