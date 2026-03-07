"""
TASBot GUI — Learnfun / Playfun launcher.

Place this script alongside learnfun.exe and playfun.exe.
All paths are relative to the script's own directory.
"""

import os
import re
import sys
import time
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

# Regex to strip ANSI escape sequences (colors, cursor movement, etc.)
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')

# Resolve the directory this script lives in (portable).
APP_DIR = Path(__file__).resolve().parent

LEARNFUN = APP_DIR / "learnfun.exe"
PLAYFUN = APP_DIR / "playfun.exe"
CONFIG = APP_DIR / "config.txt"


class TASBotGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("TASBot — Learnfun / Playfun")
        self.root.resizable(True, True)
        self.root.minsize(640, 480)

        self.process: subprocess.Popen | None = None
        self.helper_procs: list[subprocess.Popen] = []
        self.stop_event = threading.Event()

        self._build_ui()
        self._check_executables()

    # ── UI construction ──────────────────────────────────────────────

    def _build_ui(self):
        # Main container
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill="both", expand=True)

        # ── ROM selector ─────────────────────────────────────────────
        rom_frame = ttk.LabelFrame(main, text="ROM (.nes)", padding=6)
        rom_frame.pack(fill="x", pady=(0, 6))

        self.rom_var = tk.StringVar()
        ttk.Entry(rom_frame, textvariable=self.rom_var, state="readonly"
                  ).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(rom_frame, text="Browse…", command=self._browse_rom
                   ).pack(side="right")

        # ── Movie / Replay selector ──────────────────────────────────
        movie_frame = ttk.LabelFrame(main, text="Movie / Replay (.fm2)", padding=6)
        movie_frame.pack(fill="x", pady=(0, 6))

        self.movie_var = tk.StringVar()
        ttk.Entry(movie_frame, textvariable=self.movie_var, state="readonly"
                  ).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(movie_frame, text="Browse…", command=self._browse_movie
                   ).pack(side="right")

        # ── MARIONET options ──────────────────────────────────────────
        opt_frame = ttk.LabelFrame(main, text="MARIONET Options", padding=6)
        opt_frame.pack(fill="x", pady=(0, 6))

        # Row 1: helpers count
        row1 = ttk.Frame(opt_frame)
        row1.pack(fill="x", pady=(0, 4))

        ttk.Label(row1, text="Helper threads:").pack(side="left")
        self.helpers_var = tk.StringVar(value="auto")
        helpers_spin = ttk.Spinbox(
            row1, from_=1, to=128, width=5,
            textvariable=self.helpers_var)
        helpers_spin.set("auto")
        helpers_spin.pack(side="left", padx=(4, 0))
        ttk.Label(row1, text='("auto" = CPU cores \u2212 1)'
                  ).pack(side="left", padx=(6, 0))

        # Row 2: port range
        row2 = ttk.Frame(opt_frame)
        row2.pack(fill="x")

        ttk.Label(row2, text="Start port:").pack(side="left")
        self.port_var = tk.IntVar(value=8000)
        port_spin = ttk.Spinbox(
            row2, from_=1024, to=65535, width=6,
            textvariable=self.port_var)
        port_spin.pack(side="left", padx=(4, 0))
        self.port_label = ttk.Label(row2, text="")
        self.port_label.pack(side="left", padx=(6, 0))

        # Update port range preview when values change
        self.helpers_var.trace_add("write", lambda *_: self._update_port_label())
        self.port_var.trace_add("write", lambda *_: self._update_port_label())
        self._update_port_label()

        # ── Action buttons ───────────────────────────────────────────
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill="x", pady=(0, 6))

        self.btn_learn = ttk.Button(
            btn_frame, text="▶  Pretrain  (learnfun)",
            command=self._run_learnfun)
        self.btn_learn.pack(side="left", padx=(0, 6))

        self.btn_play = ttk.Button(
            btn_frame, text="▶  Play  (playfun)",
            command=self._run_playfun)
        self.btn_play.pack(side="left", padx=(0, 6))

        self.btn_stop = ttk.Button(
            btn_frame, text="■  Stop", command=self._stop_process,
            state="disabled")
        self.btn_stop.pack(side="left")

        # ── Log / output area ────────────────────────────────────────
        log_frame = ttk.LabelFrame(main, text="Output", padding=4)
        log_frame.pack(fill="both", expand=True)

        self.log = tk.Text(log_frame, wrap="word", state="disabled",
                           bg="#1e1e1e", fg="#cccccc",
                           font=("Consolas", 9), insertbackground="#ccc")
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)

        # Tag for error text
        self.log.tag_configure("err", foreground="#ff6b6b")
        self.log.tag_configure("info", foreground="#69db7c")

        # ── Status bar ───────────────────────────────────────────────
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(main, textvariable=self.status_var, relief="sunken",
                  anchor="w").pack(fill="x", pady=(6, 0))

        # ── Auto-detect files already in folder ──────────────────────
        self._auto_detect()

    # ── File browsing ────────────────────────────────────────────────

    def _browse_rom(self):
        path = filedialog.askopenfilename(
            title="Select NES ROM",
            filetypes=[("NES ROMs", "*.nes"), ("All files", "*.*")],
            initialdir=str(APP_DIR))
        if path:
            local = self._ensure_local(path)
            if local:
                self.rom_var.set(local.name)

    def _browse_movie(self):
        path = filedialog.askopenfilename(
            title="Select FM2 Movie / Replay",
            filetypes=[("FM2 movies", "*.fm2"), ("All files", "*.*")],
            initialdir=str(APP_DIR))
        if path:
            local = self._ensure_local(path)
            if local:
                self.movie_var.set(local.name)

    def _ensure_local(self, filepath: str) -> Path | None:
        """Copy the file into APP_DIR if it isn't there already.
        Returns the local Path, or None on failure."""
        src = Path(filepath).resolve()
        dest = APP_DIR / src.name
        if src == dest:
            return dest
        if dest.exists():
            overwrite = messagebox.askyesno(
                "File exists",
                f"{dest.name} already exists in the app folder.\n"
                "Overwrite with the selected file?")
            if not overwrite:
                return dest  # use existing
        try:
            shutil.copy2(src, dest)
            self._log(f"Copied {src.name} into app folder.\n", "info")
        except Exception as exc:
            messagebox.showerror("Copy failed", str(exc))
            return None
        return dest

    # ── Auto-detect *.nes / *.fm2 already present ────────────────────

    def _auto_detect(self):
        nes = sorted(APP_DIR.glob("*.nes")) + sorted(APP_DIR.glob("*.NES"))
        fm2 = sorted(APP_DIR.glob("*.fm2")) + sorted(APP_DIR.glob("*.FM2"))
        # deduplicate (case-insensitive Windows may return same file)
        seen_nes, seen_fm2 = set(), set()
        nes_unique, fm2_unique = [], []
        for p in nes:
            low = p.name.lower()
            if low not in seen_nes:
                seen_nes.add(low)
                nes_unique.append(p)
        for p in fm2:
            low = p.name.lower()
            if low not in seen_fm2:
                seen_fm2.add(low)
                fm2_unique.append(p)

        if len(nes_unique) == 1:
            self.rom_var.set(nes_unique[0].name)
        if len(fm2_unique) == 1:
            self.movie_var.set(fm2_unique[0].name)

    # ── Checks ───────────────────────────────────────────────────────

    def _check_executables(self):
        missing = []
        if not LEARNFUN.exists():
            missing.append("learnfun.exe")
        if not PLAYFUN.exists():
            missing.append("playfun.exe")
        if missing:
            self._log(
                f"WARNING: {', '.join(missing)} not found in app folder!\n",
                "err")

    def _validate_inputs(self) -> bool:
        rom = self.rom_var.get().strip()
        movie = self.movie_var.get().strip()
        if not rom:
            messagebox.showwarning("Missing ROM", "Please select a ROM file.")
            return False
        if not movie:
            messagebox.showwarning("Missing Movie",
                                   "Please select a movie / replay file.")
            return False
        if not (APP_DIR / rom).exists():
            messagebox.showerror("ROM not found",
                                 f"{rom} not found in app folder.")
            return False
        if not (APP_DIR / movie).exists():
            messagebox.showerror("Movie not found",
                                 f"{movie} not found in app folder.")
            return False
        return True

    # ── Config file ──────────────────────────────────────────────────

    def _write_config(self):
        rom = self.rom_var.get().strip()
        movie = self.movie_var.get().strip()
        # "game" = ROM filename without extension (case-preserved)
        game = Path(rom).stem
        CONFIG.write_text(f"game {game}\nmovie {movie}\n", encoding="utf-8")
        self._log(f"Wrote config.txt  (game={game}, movie={movie})\n", "info")

    # ── Process execution ────────────────────────────────────────────

    def _set_running(self, running: bool):
        state = "disabled" if running else "normal"
        self.btn_learn.configure(state=state)
        self.btn_play.configure(state=state)
        self.btn_stop.configure(state="normal" if running else "disabled")

    def _run_learnfun(self):
        if not self._validate_inputs():
            return
        if not LEARNFUN.exists():
            messagebox.showerror("Not found", "learnfun.exe not found.")
            return
        self._write_config()
        self._exec([str(LEARNFUN)], "Learnfun (Pretrain)")

    def _get_num_helpers(self) -> int:
        """Resolve helper count: 'auto' → cpu_count-1, otherwise the int."""
        h = self.helpers_var.get().strip().lower()
        if h == "auto" or not h:
            n = (os.cpu_count() or 2) - 1
            return max(n, 1)
        try:
            return max(int(h), 1)
        except ValueError:
            return max((os.cpu_count() or 2) - 1, 1)

    def _update_port_label(self):
        """Show the effective port range in the UI."""
        try:
            start = self.port_var.get()
        except tk.TclError:
            start = 8000
        n = self._get_num_helpers()
        end = start + n - 1
        self.port_label.configure(
            text=f"(ports {start}\u2013{end}  \u2192  {n} helper(s))")

    def _run_playfun(self):
        if not self._validate_inputs():
            return
        if not PLAYFUN.exists():
            messagebox.showerror("Not found", "playfun.exe not found.")
            return
        self._write_config()

        num_helpers = self._get_num_helpers()
        try:
            start_port = self.port_var.get()
        except tk.TclError:
            start_port = 8000

        ports = [start_port + i for i in range(num_helpers)]
        self._exec_playfun(ports)

    # ── Single-process execution (learnfun) ──────────────────────────

    def _exec(self, cmd: list[str], label: str):
        self._clear_log()
        self._log(f"─── Starting {label} ───\n", "info")
        self._log(f"$ {' '.join(cmd)}\n\n")
        self.status_var.set(f"Running {label}…")
        self.stop_event.clear()
        self._set_running(True)
        t = threading.Thread(target=self._reader_thread,
                             args=(cmd, label), daemon=True)
        t.start()

    def _reader_thread(self, cmd: list[str], label: str):
        try:
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                cwd=str(APP_DIR),
                creationflags=subprocess.CREATE_NO_WINDOW)

            for raw_line in iter(self.process.stdout.readline, b""):
                if self.stop_event.is_set():
                    break
                line = raw_line.decode("utf-8", errors="replace")
                self.root.after(0, self._log, line)

            self.process.stdout.close()
            rc = self.process.wait()
            tag = "info" if rc == 0 else "err"
            msg = f"\n─── {label} exited with code {rc} ───\n"
            self.root.after(0, self._log, msg, tag)
        except Exception as exc:
            self.root.after(0, self._log, f"\nERROR: {exc}\n", "err")
        finally:
            self.process = None
            self.root.after(0, self._set_running, False)
            self.root.after(0, self.status_var.set, "Ready.")

    # ── Multi-process execution (playfun helpers + master) ───────────

    def _exec_playfun(self, ports: list[int]):
        self._clear_log()
        self.stop_event.clear()
        self._set_running(True)

        self._log(f"─── Starting Playfun ───\n", "info")
        self._log(f"Helpers: {len(ports)}   Ports: "
                  f"{ports[0]}\u2013{ports[-1]}\n\n", "info")
        self.status_var.set(f"Running Playfun ({len(ports)} helpers)…")

        t = threading.Thread(target=self._playfun_thread,
                             args=(ports,), daemon=True)
        t.start()

    def _playfun_thread(self, ports: list[int]):
        exe = str(PLAYFUN)
        cwd = str(APP_DIR)

        # Match the working start.cmd exactly: "start /low call playfun.exe
        # --helper PORT".  Each helper gets its own console with full I/O
        # — no handle redirection at all.
        CREATE_NEW_CONSOLE = 0x00000010
        IDLE_PRIORITY_CLASS = 0x00000040  # same as "start /low"

        # 1. Spawn helper processes (each gets its own console window)
        for port in ports:
            if self.stop_event.is_set():
                break
            cmd = [exe, "--helper", str(port)]
            self.root.after(0, self._log, f"  Spawning helper on port {port}\n")
            try:
                p = subprocess.Popen(
                    cmd,
                    cwd=cwd,
                    creationflags=CREATE_NEW_CONSOLE | IDLE_PRIORITY_CLASS)
                self.helper_procs.append(p)
            except Exception as exc:
                self.root.after(0, self._log,
                                f"Failed to start helper on port {port}: "
                                f"{exc}\n", "err")

        if self.stop_event.is_set():
            self._cleanup_helpers()
            return

        # 2. Wait for helpers to bind their ports (same as --auto: 3 s)
        self.root.after(0, self._log,
                        "Waiting for helpers to initialize…\n", "info")
        for _ in range(30):  # 3 s in 100 ms steps
            if self.stop_event.is_set():
                self._cleanup_helpers()
                return
            time.sleep(0.1)

        # Check that helpers are still alive
        dead = [i for i, p in enumerate(self.helper_procs)
                if p.poll() is not None]
        if dead:
            self.root.after(0, self._log,
                            f"WARNING: {len(dead)} helper(s) exited during "
                            f"startup!\n", "err")

        # Bring the GUI back to the foreground (helper consoles buried it)
        self.root.after(0, self._raise_window)

        # 3. Start master (piped so we can show its output)
        port_args = [str(p) for p in ports]
        cmd = [exe, "--master"] + port_args
        self.root.after(0, self._log,
                        f"\n$ {' '.join(cmd)}\n\n")

        try:
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=cwd,
                creationflags=subprocess.CREATE_NO_WINDOW)

            for raw_line in iter(self.process.stdout.readline, b""):
                if self.stop_event.is_set():
                    break
                line = raw_line.decode("utf-8", errors="replace")
                self.root.after(0, self._log, line)

            self.process.stdout.close()
            rc = self.process.wait()
            tag = "info" if rc == 0 else "err"
            msg = f"\n─── Master exited with code {rc} ───\n"
            self.root.after(0, self._log, msg, tag)
        except Exception as exc:
            self.root.after(0, self._log, f"\nERROR: {exc}\n", "err")
        finally:
            self.process = None
            self._cleanup_helpers()
            self.root.after(0, self._set_running, False)
            self.root.after(0, self.status_var.set, "Ready.")

    def _cleanup_helpers(self):
        """Terminate all helper processes."""
        for p in self.helper_procs:
            try:
                p.terminate()
            except OSError:
                pass
        for p in self.helper_procs:
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    p.kill()
                except OSError:
                    pass
        self.helper_procs.clear()

    def _stop_process(self):
        self.stop_event.set()
        self._log("\nStopping all processes…\n", "err")
        if self.process:
            try:
                self.process.terminate()
            except OSError:
                pass
        self._cleanup_helpers()

    # ── Log widget helpers ───────────────────────────────────────────

    def _log(self, text: str, tag: str | None = None):
        # Strip ANSI escape codes (colored progress bars etc.)
        text = _ANSI_RE.sub('', text)
        self.log.configure(state="normal")
        if tag:
            self.log.insert("end", text, tag)
        else:
            self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _raise_window(self):
        """Bring the GUI window to the foreground."""
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.after(100, lambda: self.root.attributes('-topmost', False))
        self.root.focus_force()


def main():
    root = tk.Tk()
    # Set DPI awareness for sharp text on HiDPI displays
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    TASBotGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
