import tkinter as tk
from tkinter import ttk, messagebox
import threading
from core.vehicle import VehicleConnection
from modules.pats import PATSManager, PATSInfo
from utils.ford_crypto import compute_incode, PATSType


class PATSPanel(ttk.Frame):
    def __init__(self, parent, get_vehicle: callable):
        super().__init__(parent)
        self.get_vehicle = get_vehicle
        self.pats_manager: PATSManager | None = None
        self._build_ui()

    def _build_ui(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 5))

        self.read_btn = ttk.Button(toolbar, text="Read PATS Info", command=self._read_info)
        self.read_btn.pack(side="left", padx=2)

        self.program_btn = ttk.Button(toolbar, text="Program Key", command=self._program_key)
        self.program_btn.pack(side="left", padx=2)

        self.erase_btn = ttk.Button(toolbar, text="Erase All Keys", command=self._erase_keys)
        self.erase_btn.pack(side="left", padx=2)

        self.status_label = ttk.Label(self, text="Connect to vehicle and read PATS info first")
        self.status_label.pack(fill="x", pady=5)

        calc_frame = ttk.LabelFrame(self, text="Incode → Outcode Calculator (Offline)", padding=8)
        calc_frame.pack(fill="x", padx=5, pady=(0, 5))

        row_a = ttk.Frame(calc_frame)
        row_a.pack(fill="x", pady=2)

        ttk.Label(row_a, text="Incode (hex):").pack(side="left", padx=(0, 5))
        self.calc_incode_var = tk.StringVar()
        self.calc_incode_entry = ttk.Entry(
            row_a, textvariable=self.calc_incode_var, width=20, font=("Consolas", 10),
        )
        self.calc_incode_entry.pack(side="left", padx=(0, 15))

        ttk.Label(row_a, text="PATS Type:").pack(side="left", padx=(0, 5))
        self.calc_pats_var = tk.StringVar(value="Auto (from vehicle)")
        pats_choices = [
            "Auto (from vehicle)",
            "PATS I/II (1996-2005)",
            "PATS III (2005-2010)",
            "PATS IV/V (2010+)",
        ]
        self.calc_pats_combo = ttk.Combobox(
            row_a, textvariable=self.calc_pats_var,
            values=pats_choices, width=22, state="readonly",
        )
        self.calc_pats_combo.pack(side="left", padx=(0, 15))

        row_b = ttk.Frame(calc_frame)
        row_b.pack(fill="x", pady=2)

        ttk.Label(row_b, text="Module ID (hex):").pack(side="left", padx=(0, 5))
        self.calc_modid_var = tk.StringVar(value="0000")
        ttk.Entry(
            row_b, textvariable=self.calc_modid_var, width=8, font=("Consolas", 10),
        ).pack(side="left", padx=(0, 15))

        ttk.Label(row_b, text="Algo Variant:").pack(side="left", padx=(0, 5))
        self.calc_algo_var = tk.StringVar(value="0")
        ttk.Entry(
            row_b, textvariable=self.calc_algo_var, width=6, font=("Consolas", 10),
        ).pack(side="left", padx=(0, 15))

        self.calc_btn = ttk.Button(row_b, text="Calculate Outcode", command=self._calc_outcode, width=20)
        self.calc_btn.pack(side="left", padx=(10, 15))

        ttk.Label(row_b, text="Outcode:").pack(side="left", padx=(0, 5))
        self.calc_result_var = tk.StringVar(value="----")
        ttk.Label(
            row_b, textvariable=self.calc_result_var,
            font=("Consolas", 14, "bold"), foreground="#55ff55",
        ).pack(side="left")

        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left = ttk.LabelFrame(paned, text="PATS Configuration", padding=10)
        paned.add(left, weight=1)

        self.info_fields: dict[str, ttk.Label] = {}
        fields = [
            ("PATS Type", "pats_type"),
            ("PATS Enabled", "pats_enabled"),
            ("Master Key", "master_key"),
            ("Min Keys Required", "min_keys"),
            ("Keys Programmed", "num_keys_programmed"),
            ("Spare Key Available", "spare_key"),
            ("Unlock Key", "unlock_key"),
            ("Anti-Scan", "anti_scan"),
            ("Timed Delay (min)", "timed_delay"),
            ("Cycle Key Time (sec)", "cycle_key_time"),
            ("Reset Type", "reset_type"),
            ("PCM ID", "pcm_id"),
            ("Algorithm Variant", "algo_variant"),
        ]

        for i, (label_text, field_name) in enumerate(fields):
            ttk.Label(left, text=f"{label_text}:").grid(row=i, column=0, sticky="w", pady=2, padx=(0, 10))
            val_label = ttk.Label(left, text="--", font=("Consolas", 10))
            val_label.grid(row=i, column=1, sticky="w", pady=2)
            self.info_fields[field_name] = val_label

        right = ttk.LabelFrame(paned, text="Key Programming Log", padding=10)
        paned.add(right, weight=1)

        self.log_text = tk.Text(right, wrap="word", font=("Consolas", 9), state="disabled")
        log_scroll = ttk.Scrollbar(right, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)

        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

    def _calc_outcode(self):
        raw = self.calc_incode_var.get().strip().replace(" ", "")
        if not raw:
            messagebox.showwarning("Calculator", "Enter an incode value")
            return
        try:
            incode_int = int(raw, 16)
        except ValueError:
            messagebox.showwarning("Calculator", "Incode must be hex (e.g. A3F1)")
            return

        pats_sel = self.calc_pats_var.get()
        if pats_sel.startswith("Auto"):
            if self.pats_manager and self.pats_manager.pats_info.pats_type > 0:
                ptype = self.pats_manager.pats_info.pats_type
            else:
                ptype = PATSType.PATS_3
        elif "I/II" in pats_sel:
            ptype = PATSType.PATS_1
        elif "III" in pats_sel:
            ptype = PATSType.PATS_3
        else:
            ptype = PATSType.PATS_4

        try:
            mod_id = int(self.calc_modid_var.get().strip(), 16)
        except ValueError:
            mod_id = 0
        try:
            algo = int(self.calc_algo_var.get().strip())
        except ValueError:
            algo = 0

        try:
            outcode = compute_incode(incode_int, ptype, mod_id, algo)
            if ptype in (PATSType.PATS_4, PATSType.PATS_5):
                self.calc_result_var.set(f"{outcode:08X}")
            else:
                self.calc_result_var.set(f"{outcode:04X}")
            self._log(f"Incode 0x{raw.upper()} → Outcode 0x{self.calc_result_var.get()}  "
                       f"(PATS {ptype}, mod=0x{mod_id:04X}, algo={algo})")
        except Exception as e:
            self.calc_result_var.set("ERROR")
            self._log(f"Calculator error: {e}")

    def _log(self, message: str):
        def _append():
            self.log_text.config(state="normal")
            self.log_text.insert("end", message + "\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        self.after(0, _append)

    def _read_info(self):
        vehicle = self.get_vehicle()
        if not vehicle:
            return

        self.read_btn.config(state="disabled")
        self.status_label.config(text="Reading PATS configuration...")

        def read_thread():
            try:
                self.pats_manager = PATSManager(vehicle)
                info = self.pats_manager.read_pats_info()
                self.after(0, lambda: self._display_info(info))
                self.after(0, lambda: self.status_label.config(text="PATS info read successfully"))
                self._log("PATS configuration read successfully")
            except Exception as e:
                self.after(0, lambda: self.status_label.config(text=f"Error: {e}"))
                self._log(f"Error reading PATS: {e}")
            finally:
                self.after(0, lambda: self.read_btn.config(state="normal"))

        threading.Thread(target=read_thread, daemon=True).start()

    def _display_info(self, info: PATSInfo):
        def fmt(val, special=None):
            if val == -1:
                return "N/A"
            if special == "bool":
                return "Yes" if val == 1 else "No" if val == 0 else str(val)
            if special == "hex":
                return f"0x{val:04X}" if val > 0 else str(val)
            return str(val)

        self.info_fields["pats_type"].config(
            text=PATSManager.pats_type_name(info.pats_type)
        )
        self.info_fields["pats_enabled"].config(text=fmt(info.pats_enabled, "bool"))
        self.info_fields["master_key"].config(text=fmt(info.master_key, "bool"))
        self.info_fields["min_keys"].config(text=fmt(info.min_keys))
        self.info_fields["num_keys_programmed"].config(text=fmt(info.num_keys_programmed))
        self.info_fields["spare_key"].config(text=fmt(info.spare_key, "bool"))
        self.info_fields["unlock_key"].config(text=fmt(info.unlock_key, "bool"))
        self.info_fields["anti_scan"].config(text=fmt(info.anti_scan, "bool"))
        self.info_fields["timed_delay"].config(text=fmt(info.timed_delay))
        self.info_fields["cycle_key_time"].config(text=fmt(info.cycle_key_time))
        self.info_fields["reset_type"].config(text=fmt(info.reset_type))
        self.info_fields["pcm_id"].config(text=fmt(info.pcm_id, "hex"))
        self.info_fields["algo_variant"].config(text=fmt(info.algo_variant))

        if info.pcm_id > 0:
            self.calc_modid_var.set(f"{info.pcm_id:04X}")
        if info.algo_variant >= 0:
            self.calc_algo_var.set(str(info.algo_variant))
        if info.pats_type > 0:
            pats_map = {1: "PATS I/II (1996-2005)", 2: "PATS I/II (1996-2005)",
                        3: "PATS III (2005-2010)", 4: "PATS IV/V (2010+)",
                        5: "PATS IV/V (2010+)"}
            label = pats_map.get(info.pats_type, "Auto (from vehicle)")
            self.calc_pats_var.set(label)

    def _program_key(self):
        if not self.pats_manager:
            messagebox.showwarning("PATS", "Read PATS info first")
            return

        msg = (
            "KEY PROGRAMMING PROCEDURE\n\n"
            "1. Make sure you have the new key ready\n"
            "2. Security access will be requested\n"
            "3. You will need to cycle the ignition with the new key\n"
            "4. Follow the on-screen instructions\n\n"
            "Continue?"
        )
        if not messagebox.askyesno("Program Key", msg):
            return

        self.program_btn.config(state="disabled")
        self.erase_btn.config(state="disabled")

        def program_thread():
            try:
                self.pats_manager.program_key(callback=self._log)
                self._log("Key programming sequence initiated successfully")
                self.after(0, lambda: messagebox.showinfo(
                    "Success",
                    "Key learn initiated. Cycle the ignition with the new key now."
                ))
            except Exception as e:
                self._log(f"Key programming failed: {e}")
                self.after(0, lambda: messagebox.showerror("Failed", str(e)))
            finally:
                self.after(0, lambda: self.program_btn.config(state="normal"))
                self.after(0, lambda: self.erase_btn.config(state="normal"))

        threading.Thread(target=program_thread, daemon=True).start()

    def _erase_keys(self):
        if not self.pats_manager:
            messagebox.showwarning("PATS", "Read PATS info first")
            return

        msg = (
            "WARNING: ERASE ALL KEYS\n\n"
            "This will erase ALL programmed keys from the vehicle.\n"
            "You MUST have at least 2 keys ready to program afterward.\n"
            "If you lose all keys, the vehicle will not start.\n\n"
            "Are you absolutely sure?"
        )
        if not messagebox.askyesno("Erase Keys", msg, icon="warning"):
            return
        if not messagebox.askyesno("Final Confirmation",
                                    "Last chance. Erase ALL keys?", icon="warning"):
            return

        self.program_btn.config(state="disabled")
        self.erase_btn.config(state="disabled")

        def erase_thread():
            try:
                self.pats_manager.erase_keys(callback=self._log)
                self._log("All keys erased successfully")
            except Exception as e:
                self._log(f"Key erase failed: {e}")
                self.after(0, lambda: messagebox.showerror("Failed", str(e)))
            finally:
                self.after(0, lambda: self.program_btn.config(state="normal"))
                self.after(0, lambda: self.erase_btn.config(state="normal"))

        threading.Thread(target=erase_thread, daemon=True).start()
