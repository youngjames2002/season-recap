"""
app.py
======
Tkinter GUI for smash_scout.
Run directly or via run.bat.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import importlib
import os

import core

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PLACEHOLDER_EVENTS = (
    "Paste event URLs here, one per line\n"
    "e.g. https://www.start.gg/tournament/big-fish-137/event/ult-singles"
)

PLACEHOLDER_PLAYERS = (
    "Paste players here, one per line\n"
    "Format:  Tag, start.gg player ID\n"
    "e.g.\n"
    "Sparg0, 1234567\n"
    "Tweek, 7654321"
)


def add_placeholder(widget, text):
    """Attach placeholder behaviour to a Text widget."""
    widget._placeholder = text
    widget._has_placeholder = False

    def _set():
        widget.config(fg="grey")
        widget.insert("1.0", text)
        widget._has_placeholder = True

    def _clear(event=None):
        if widget._has_placeholder:
            widget.delete("1.0", tk.END)
            widget.config(fg="black")
            widget._has_placeholder = False

    def _restore(event=None):
        if not widget.get("1.0", tk.END).strip():
            _set()

    widget.bind("<FocusIn>", _clear)
    widget.bind("<FocusOut>", _restore)
    _set()


def get_text(widget) -> str:
    """Get text from a widget, returning empty string if it only has the placeholder."""
    if widget._has_placeholder:
        return ""
    return widget.get("1.0", tk.END).strip()


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Season Recap")
        self.resizable(True, True)
        self.minsize(700, 600)
        self._build_ui()
        self._load_saved_state()

    def _build_ui(self):
        pad = {"padx": 10, "pady": 5}

        # ── API key ──────────────────────────────────────────────────────────
        key_frame = tk.Frame(self)
        key_frame.pack(fill="x", **pad)
        tk.Label(key_frame, text="start.gg API Key:", width=16, anchor="w").pack(side="left")
        self.api_key_var = tk.StringVar()
        self.api_key_entry = tk.Entry(key_frame, textvariable=self.api_key_var, show="•", width=50)
        self.api_key_entry.pack(side="left", fill="x", expand=True)
        tk.Button(key_frame, text="Show", command=self._toggle_key_visibility, width=5).pack(side="left", padx=(4, 0))

        # ── Output path ──────────────────────────────────────────────────────
        out_frame = tk.Frame(self)
        out_frame.pack(fill="x", **pad)
        tk.Label(out_frame, text="Output folder:", width=16, anchor="w").pack(side="left")
        self.out_path_var = tk.StringVar(value=os.path.expanduser("~\\Desktop"))
        tk.Entry(out_frame, textvariable=self.out_path_var, width=44).pack(side="left", fill="x", expand=True)
        tk.Button(out_frame, text="Browse…", command=self._browse_output).pack(side="left", padx=(4, 0))

        # ── Output filename ──────────────────────────────────────────────────
        name_frame = tk.Frame(self)
        name_frame.pack(fill="x", **pad)
        tk.Label(name_frame, text="Output filename:", width=16, anchor="w").pack(side="left")
        self.out_name_var = tk.StringVar(value="season_recap")
        tk.Entry(name_frame, textvariable=self.out_name_var, width=30).pack(side="left")
        tk.Label(name_frame, text=".csv  /  .html", fg="grey").pack(side="left", padx=(4, 0))

        # ── Two text boxes side by side ──────────────────────────────────────
        boxes_frame = tk.Frame(self)
        boxes_frame.pack(fill="both", expand=True, padx=10, pady=5)
        boxes_frame.columnconfigure(0, weight=1)
        boxes_frame.columnconfigure(1, weight=1)
        boxes_frame.rowconfigure(1, weight=1)

        tk.Label(boxes_frame, text="Event URLs (one per line)").grid(row=0, column=0, sticky="w")
        tk.Label(boxes_frame, text="Players  (Tag, ID — one per line)").grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.events_box = tk.Text(boxes_frame, wrap="word", width=40, height=14, fg="grey")
        self.events_box.grid(row=1, column=0, sticky="nsew")
        add_placeholder(self.events_box, PLACEHOLDER_EVENTS)

        self.players_box = tk.Text(boxes_frame, wrap="word", width=40, height=14, fg="grey")
        self.players_box.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        add_placeholder(self.players_box, PLACEHOLDER_PLAYERS)

        # Scrollbars
        ev_scroll = ttk.Scrollbar(boxes_frame, command=self.events_box.yview)
        ev_scroll.grid(row=1, column=0, sticky="nse")
        self.events_box.config(yscrollcommand=ev_scroll.set)

        pl_scroll = ttk.Scrollbar(boxes_frame, command=self.players_box.yview)
        pl_scroll.grid(row=1, column=1, sticky="nse", padx=(10, 0))
        self.players_box.config(yscrollcommand=pl_scroll.set)

        # ── Run button + progress ────────────────────────────────────────────
        btn_frame = tk.Frame(self)
        btn_frame.pack(fill="x", padx=10, pady=5)
        self.run_btn = tk.Button(btn_frame, text="Run", command=self._run, bg="#2e7d32", fg="white",
                                  font=("Segoe UI", 10, "bold"), padx=20, pady=4)
        self.run_btn.pack(side="left")
        self.status_label = tk.Label(btn_frame, text="", fg="grey")
        self.status_label.pack(side="left", padx=10)

        # ── Log output ───────────────────────────────────────────────────────
        tk.Label(self, text="Log", anchor="w").pack(fill="x", padx=10)
        self.log_box = scrolledtext.ScrolledText(self, height=10, state="disabled",
                                                  bg="#1e1e1e", fg="#d4d4d4",
                                                  font=("Consolas", 9))
        self.log_box.pack(fill="both", expand=False, padx=10, pady=(0, 10))

    # ── Key visibility toggle ────────────────────────────────────────────────

    def _toggle_key_visibility(self):
        current = self.api_key_entry.cget("show")
        self.api_key_entry.config(show="" if current == "•" else "•")

    # ── Browse output folder ─────────────────────────────────────────────────

    def _browse_output(self):
        folder = filedialog.askdirectory(initialdir=self.out_path_var.get())
        if folder:
            self.out_path_var.set(folder)

    # ── Persist API key and last-used inputs across sessions ─────────────────

    def _state_path(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), ".season_recap_state")

    def _load_saved_state(self):
        try:
            with open(self._state_path(), "r", encoding="utf-8") as f:
                import json
                state = json.load(f)
            if state.get("api_key"):
                self.api_key_var.set(state["api_key"])
            if state.get("output_path"):
                self.out_path_var.set(state["output_path"])
            if state.get("output_name"):
                self.out_name_var.set(state["output_name"])
            if state.get("events"):
                self.events_box.delete("1.0", tk.END)
                self.events_box.config(fg="black")
                self.events_box._has_placeholder = False
                self.events_box.insert("1.0", state["events"])
            if state.get("players"):
                self.players_box.delete("1.0", tk.END)
                self.players_box.config(fg="black")
                self.players_box._has_placeholder = False
                self.players_box.insert("1.0", state["players"])
        except Exception:
            pass  # First run or corrupt file — just use defaults

    def _save_state(self):
        import json
        state = {
            "api_key": self.api_key_var.get(),
            "output_path": self.out_path_var.get(),
            "output_name": self.out_name_var.get(),
            "events": get_text(self.events_box),
            "players": get_text(self.players_box),
        }
        try:
            with open(self._state_path(), "w", encoding="utf-8") as f:
                json.dump(state, f)
        except Exception:
            pass

    # ── Logging ──────────────────────────────────────────────────────────────

    def _log(self, msg: str):
        """Append a line to the log box (thread-safe via after())."""
        def _append():
            self.log_box.config(state="normal")
            self.log_box.insert(tk.END, msg + "\n")
            self.log_box.see(tk.END)
            self.log_box.config(state="disabled")
        self.after(0, _append)

    def _set_status(self, msg: str, colour: str = "grey"):
        self.after(0, lambda: self.status_label.config(text=msg, fg=colour))

    # ── Run ──────────────────────────────────────────────────────────────────

    def _run(self):
        api_key = self.api_key_var.get().strip()
        if not api_key:
            messagebox.showerror("Missing API key", "Please enter your start.gg API key.")
            return

        events_raw = get_text(self.events_box)
        players_raw = get_text(self.players_box)

        if not events_raw:
            messagebox.showerror("No events", "Please paste at least one event URL.")
            return
        if not players_raw:
            messagebox.showerror("No players", "Please paste at least one player.")
            return

        out_dir = self.out_path_var.get().strip()
        if not os.path.isdir(out_dir):
            messagebox.showerror("Bad output path", f"Output folder does not exist:\n{out_dir}")
            return

        out_name = self.out_name_var.get().strip() or "recap"
        # Strip any extension the user may have typed — core.run adds .csv and .html
        out_name = os.path.splitext(out_name)[0]
        out_file = os.path.join(out_dir, out_name)

        csv_file  = out_file + ".csv"
        html_file = out_file + ".html"

        # Save state so inputs persist next time
        self._save_state()

        # Clear log
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", tk.END)
        self.log_box.config(state="disabled")

        self.run_btn.config(state="disabled", text="Running…")
        self._set_status("Running…", "orange")

        def worker():
            try:
                importlib.reload(core)
                core.run(
                    api_key=api_key,
                    event_urls=events_raw,
                    players_raw=players_raw,
                    output_path=out_file,
                    log=self._log,
                )
                self._set_status(f"Done → {out_name}.csv / .html", "#2e7d32")
                self.after(0, lambda: messagebox.showinfo(
                    "Done",
                    f"Files saved to:\n\n{csv_file}\n{html_file}"
                ))
            except Exception as e:
                self._log(f"\nERROR: {e}")
                self._set_status("Failed — see log", "red")
                self.after(0, lambda: messagebox.showerror("Error", str(e)))
            finally:
                self.after(0, lambda: self.run_btn.config(state="normal", text="Run"))

        threading.Thread(target=worker, daemon=True).start()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = App()
    app.mainloop()