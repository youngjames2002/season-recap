# Season Recap

A desktop tool for Super Smash Bros. Ultimate ranking panels. Given a list of start.gg event URLs and a list of players, it pulls all their results via the start.gg API and produces a formatted season recap — placements, win rates, head-to-head records, wins, and losses — ready for panel discussion.

Outputs a `.csv` (for editing) and a `.html` (for sharing) with the same data.

![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

---

## What it produces

- **H2H table** — full grid of every contender vs every other contender, colour-coded by win% in the HTML, ordered by contenders win%
- **Per-player recaps** — overall win%, contenders win%, placements (ordered by event size) with average, full wins list, full losses list
- Players ordered by overall win% throughout

---

## Requirements

- Python 3.10 or later — [python.org](https://www.python.org/downloads/)
- A start.gg API key (free) — [developer.start.gg](https://developer.start.gg/docs/authentication)
- The `requests` library — installed automatically by `run.bat`

---

## Setup

1. **Download** the three files and put them in the same folder:
   - `app.py`
   - `core.py`
   - `run.bat`

2. **Get a start.gg API key**
   - Go to [developer.start.gg](https://developer.start.gg/docs/authentication)
   - Sign in, create a new token, and copy it

3. **Double-click `run.bat`** — it checks for Python, installs `requests` if needed, and opens the app

---

## Usage

### Event URLs
Paste one start.gg event URL per line into the left box. These should be direct links to the singles bracket, not the tournament page:
```
https://www.start.gg/tournament/big-fish-137/event/ult-singles
https://www.start.gg/tournament/some-tournament/event/ultimate-singles
```

### Players
Paste one player per line into the right box in the format `Tag, start.gg player ID`:
```
Sparg0, 1234567
Tweek, 7654321
```

To find a player's ID, go to their start.gg profile page — the number in the URL (`start.gg/user/12345`) is their ID. The ID is used as the primary lookup; the tag is used as a fallback if the ID doesn't match.

### Output
Set an output folder and filename (no extension needed), then hit **Run**. Two files are written:
- `filename.csv` — structured data, easy to open in any spreadsheet app
- `filename.html` — styled page, open in any browser, easy to share

Your API key, inputs, folder, and filename are saved automatically and restored next time you open the app.

---

## How it works

1. Fetches event info and standings for each event (once per event, cached)
2. For each player, looks them up in the standings and fetches all their sets
3. Computes stats — win%, placements, H2H vs other contenders, full wins/losses lists
4. DQ sets are automatically excluded
5. Writes CSV and HTML

For 10 players across 15 events, expect roughly 1–2 minutes depending on bracket sizes.

---

## Files

| File | Purpose |
|------|---------|
| `app.py` | Tkinter GUI — input fields, run button, log panel |
| `core.py` | All API calls, stats computation, CSV and HTML output |
| `run.bat` | Windows launcher — checks Python, installs deps, opens app |

All customisation lives in `core.py`. The output format, stat calculations, and sorting are all in clearly labelled sections at the bottom of the file.

---

## Notes

- **API rate limits** — start.gg's free tier allows ~80 requests/minute. The script paces calls at 0.15s apart and backs off automatically if rate limited
- **Player IDs** — if a player recently changed their tag, make sure the ID is correct as tag matching is only a fallback
- **State file** — your inputs and API key are saved to `.season_recap_state` next to the script. This file is listed in `.gitignore` and should never be shared or committed
- **log.txt** — a log of the last run is written next to the script, useful for debugging

---

## Contributing

Issues and pull requests welcome. If you have feature ideas or find bugs, open an issue.

---

## Licence

MIT — see `LICENSE`.