import tkinter as tk
from tkinter import ttk, messagebox
import threading
from core.vehicle import VehicleConnection
from core.protocols import FORD_MODULES
from modules.security import SecurityAccess, FORD_SESSIONS, BruteforceResult


class SecurityPanel(ttk.Frame):
    def __init__(self, parent, get_vehicle: callable):
        super().__init__(parent)
        self.get_vehicle = get_vehicle
        self._build_ui()

    def _build_ui(self):
        config = ttk.LabelFrame(self, text="Security Access Configuration", padding=10)
        config.pack(fill="x", padx=5, pady=(0, 5))

        row1 = ttk.Frame(config)
        row1.pack(fill="x", pady=2)

        ttk.Label(row1, text="Target Module:").pack(side="left", padx=(0, 5))
        self.module_var = tk.StringVar()
        module_names = [f"{m.abbreviation} — {m.name}" for m in FORD_MODULES]
        self.module_combo = ttk.Combobox(
            row1, textvariable=self.module_var,
            values=module_names, width=35, state="readonly",
        )
        self.module_combo.pack(side="left", padx=(0, 15))
        if module_names:
            self.module_combo.current(0)

        ttk.Label(row1, text="Session:").pack(side="left", padx=(0, 5))
        self.session_var = tk.StringVar()
        session_names = list(FORD_SESSIONS.keys())
        self.session_combo = ttk.Combobox(
            row1, textvariable=self.session_var,
            values=session_names, width=25, state="readonly",
        )
        self.session_combo.pack(side="left", padx=(0, 15))
        self.session_combo.current(2)

        ttk.Label(row1, text="Security Level:").pack(side="left", padx=(0, 5))
        self.level_var = tk.StringVar(value="0x01 — Read/Unlock")
        level_values = [
            "0x01 — Read/Unlock",
            "0x03 — Write/Program",
            "0x11 — Module Config",
            "0x61 — Factory/EOL",
        ]
        level_combo = ttk.Combobox(
            row1, textvariable=self.level_var,
            values=level_values, width=20, state="readonly",
        )
        level_combo.pack(side="left")

        row2 = ttk.Frame(config)
        row2.pack(fill="x", pady=(5, 0))

        self.brute_btn = ttk.Button(
            row2, text="Bruteforce Security Access",
            command=self._start_bruteforce, width=28,
        )
        self.brute_btn.pack(side="left", padx=2)

        self.brute_all_btn = ttk.Button(
            row2, text="Scan All Modules",
            command=self._scan_all, width=18,
        )
        self.brute_all_btn.pack(side="left", padx=2)

        self.progress = ttk.Progressbar(row2, mode="determinate", length=200)
        self.progress.pack(side="left", padx=10)

        self.status_label = ttk.Label(row2, text="")
        self.status_label.pack(side="right")

        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=5, pady=5)

        left = ttk.LabelFrame(paned, text="Results", padding=5)
        paned.add(left, weight=2)

        columns = ("module", "session", "level", "seed", "key", "status")
        self.tree = ttk.Treeview(left, columns=columns, show="headings", height=18)
        self.tree.heading("module", text="Module")
        self.tree.heading("session", text="Session")
        self.tree.heading("level", text="Level")
        self.tree.heading("seed", text="Seed")
        self.tree.heading("key", text="Key Found")
        self.tree.heading("status", text="Status")

        self.tree.column("module", width=70, anchor="center")
        self.tree.column("session", width=60, anchor="center")
        self.tree.column("level", width=50, anchor="center")
        self.tree.column("seed", width=80, anchor="center")
        self.tree.column("key", width=120)
        self.tree.column("status", width=200)

        self.tree.tag_configure("unlocked", foreground="#55ff55")
        self.tree.tag_configure("locked", foreground="#ff4444")
        self.tree.tag_configure("error", foreground="#ffaa00")

        tree_scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

        right = ttk.LabelFrame(paned, text="Log", padding=5)
        paned.add(right, weight=1)

        self.log_text = tk.Text(right, wrap="word", font=("Consolas", 9), state="disabled")
        log_scroll = ttk.Scrollbar(right, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

    def _log(self, message: str):
        def _append():
            self.log_text.config(state="normal")
            self.log_text.insert("end", message + "\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        self.after(0, _append)

    def _get_selected_module(self):
        idx = self.module_combo.current()
        if idx < 0 or idx >= len(FORD_MODULES):
            return None
        return FORD_MODULES[idx]

    def _get_session(self) -> int:
        name = self.session_var.get()
        return FORD_SESSIONS.get(name, 0x01)

    def _get_level(self) -> int:
        return int(self.level_var.get().split(" ")[0], 16)

    def _set_buttons(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.brute_btn.config(state=state)
        self.brute_all_btn.config(state=state)

    def _add_result(self, result: BruteforceResult):
        if result.success:
            tag = "unlocked"
            key_str = result.key_found.decode("ascii", errors="replace") if result.key_found else ""
            status = f"UNLOCKED ({result.attempts} attempts)"
        elif result.error:
            tag = "error"
            key_str = ""
            status = result.error
        else:
            tag = "locked"
            key_str = ""
            status = f"LOCKED ({result.attempts} tried)"

        seed_str = f"0x{result.seed:06X}" if result.seed else "--"

        self.tree.insert("", "end", values=(
            result.module.abbreviation,
            f"0x{result.session:02X}",
            f"0x{result.security_level:02X}",
            seed_str,
            key_str,
            status,
        ), tags=(tag,))

    def _start_bruteforce(self):
        vehicle = self.get_vehicle()
        if not vehicle:
            return
        module = self._get_selected_module()
        if not module:
            return

        session = self._get_session()
        level = self._get_level()

        self._set_buttons(False)
        self._log(f"--- Bruteforcing {module.abbreviation} session=0x{session:02X} level=0x{level:02X} ---")

        def brute_thread():
            sa = SecurityAccess(vehicle)
            result = sa.bruteforce_module(
                module, session=session, level=level, callback=self._log,
            )
            self.after(0, lambda: self._add_result(result))
            if result.success:
                self._log(f"SUCCESS: {module.abbreviation} unlocked with key "
                          f"{result.key_found.decode('ascii', errors='replace')}")
            else:
                self._log(f"FAILED: {result.error}")
            self.after(0, lambda: self._set_buttons(True))
            self.after(0, lambda: self.status_label.config(
                text=f"{'UNLOCKED' if result.success else 'Failed'}: {module.abbreviation}"
            ))

        threading.Thread(target=brute_thread, daemon=True).start()

    def _scan_all(self):
        vehicle = self.get_vehicle()
        if not vehicle:
            return

        session = self._get_session()
        level = self._get_level()

        common = [m for m in FORD_MODULES if m.abbreviation in (
            "PCM", "TCM", "ABS", "RCM", "IPC", "BCM", "SCCM", "HVAC",
            "ACM", "APIM", "DDM", "PDM", "PAM", "GWM", "EPAS", "PSCM",
        )]

        self._set_buttons(False)
        self.tree.delete(*self.tree.get_children())
        self.progress["value"] = 0
        self._log(f"--- Scanning {len(common)} modules session=0x{session:02X} level=0x{level:02X} ---")

        def scan_thread():
            sa = SecurityAccess(vehicle)
            for i, module in enumerate(common):
                pct = (i / len(common)) * 100
                self.after(0, lambda p=pct: self.progress.config(value=p))
                self.after(0, lambda n=module.abbreviation: self.status_label.config(
                    text=f"Trying {n}..."
                ))
                self._log(f"\n[{module.abbreviation}] {module.name}")

                result = sa.bruteforce_module(
                    module, session=session, level=level, callback=self._log,
                )
                self.after(0, lambda r=result: self._add_result(r))

            self.after(0, lambda: self.progress.config(value=100))
            self.after(0, lambda: self._set_buttons(True))
            self.after(0, lambda: self.status_label.config(text="Scan complete"))
            self._log("--- Scan complete ---")

        threading.Thread(target=scan_thread, daemon=True).start()
