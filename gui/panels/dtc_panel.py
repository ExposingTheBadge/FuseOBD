import tkinter as tk
from tkinter import ttk, messagebox
import threading
import webbrowser

from core.vehicle import VehicleConnection
from core.protocols import FORD_MODULES, FordModule
from modules.dtc import DTCReader, DTC, ModuleDTCs
from modules.vehicle_info import decode_vin, format_vehicle_summary, get_vehicle_image_url
from data.dtc_definitions import lookup_dtc


class DTCPanel(ttk.Frame):
    def __init__(self, parent, get_vehicle: callable):
        super().__init__(parent)
        self.get_vehicle = get_vehicle
        self.all_dtcs: list[ModuleDTCs] = []
        self.vehicle_info: dict = {}
        self.chat = None  # MechanicChat instance
        self.photo = None  # Keep reference to prevent GC
        self._build_ui()

    # ═══════════════════════════════════════════════════════════════
    # UI Construction
    # ═══════════════════════════════════════════════════════════════

    def _build_ui(self):
        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 5))

        self.read_btn = ttk.Button(toolbar, text="Read All Faults", command=self._read_all)
        self.read_btn.pack(side="left", padx=2)

        self.clear_btn = ttk.Button(toolbar, text="Clear All Faults", command=self._clear_all)
        self.clear_btn.pack(side="left", padx=2)

        self.ai_btn = ttk.Button(toolbar, text="AI Mechanic", command=self._start_ai_session)
        self.ai_btn.pack(side="left", padx=(15, 2))
        self.ai_btn.config(state="disabled")

        self.progress = ttk.Progressbar(toolbar, mode="determinate", length=150)
        self.progress.pack(side="left", padx=10)

        self.count_label = ttk.Label(toolbar, text="")
        self.count_label.pack(side="right")

        self.status_label = ttk.Label(self, text="Ready")
        self.status_label.pack(fill="x")

        # Main horizontal split: left (tree+chat) | right (vehicle)
        main_pane = ttk.PanedWindow(self, orient="horizontal")
        main_pane.pack(fill="both", expand=True)

        # ── LEFT SIDE ──
        left_frame = ttk.Frame(main_pane)

        # Fault tree
        tree_frame = ttk.Frame(left_frame)
        columns = ("module", "code", "description", "status", "flags")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=8)

        self.tree.heading("module", text="Module")
        self.tree.heading("code", text="Code")
        self.tree.heading("description", text="Description")
        self.tree.heading("status", text="Status")
        self.tree.heading("flags", text="Details")

        self.tree.column("module", width=60)
        self.tree.column("code", width=70, anchor="center")
        self.tree.column("description", width=200)
        self.tree.column("status", width=65, anchor="center")
        self.tree.column("flags", width=180)

        self.tree.tag_configure("active", foreground="#ff4444")
        self.tree.tag_configure("pending", foreground="#ffaa00")
        self.tree.tag_configure("stored", foreground="#999999")
        self.tree.tag_configure("root_cause", foreground="#ff4444", font=("Segoe UI", 9, "bold"))
        self.tree.tag_configure("cascade", foreground="#ff8800")
        self.tree.tag_configure("isolated", foreground="#44aaff")

        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        tree_frame.pack(fill="both", expand=True, padx=(0, 0))

        # Chat area
        chat_frame = ttk.Frame(left_frame)
        chat_header = ttk.Frame(chat_frame)
        chat_header.pack(fill="x")
        ttk.Label(chat_header, text="AI Mechanic Chat", font=("Segoe UI", 10, "bold")).pack(side="left", padx=5, pady=(5, 0))
        self.chat_status = ttk.Label(chat_header, text="", font=("Segoe UI", 9))
        self.chat_status.pack(side="right", padx=5, pady=(5, 0))

        self.chat_text = tk.Text(chat_frame, wrap="word", font=("Segoe UI", 10), padx=10, pady=10,
                                 bg="#1a1a1a", fg="#e0e0e0", height=8, state="disabled",
                                 relief="flat", borderwidth=0)
        chat_scroll = ttk.Scrollbar(chat_frame, orient="vertical", command=self.chat_text.yview)
        self.chat_text.configure(yscrollcommand=chat_scroll.set)
        self.chat_text.pack(side="left", fill="both", expand=True, padx=(5, 0), pady=5)
        chat_scroll.pack(side="right", fill="y", padx=(0, 5), pady=5)

        self.chat_text.tag_configure("mechanic", foreground="#ff8800", font=("Segoe UI", 10, "bold"))
        self.chat_text.tag_configure("user", foreground="#44aaff", font=("Segoe UI", 10, "bold"))
        self.chat_text.tag_configure("system", foreground="#888888", font=("Segoe UI", 9, "italic"))
        self.chat_text.tag_configure("error", foreground="#ff4444")

        # Chat input
        input_frame = ttk.Frame(chat_frame)
        input_frame.pack(fill="x", padx=5, pady=(0, 5))
        self.chat_input = ttk.Entry(input_frame)
        self.chat_input.pack(side="left", fill="x", expand=True)
        self.chat_input.bind("<Return>", lambda e: self._send_chat())
        self.chat_input.config(state="disabled")
        ttk.Button(input_frame, text="Send", command=self._send_chat, width=8).pack(side="right", padx=(5, 0))

        left_frame.pack(fill="both", expand=True)
        main_pane.add(left_frame, weight=3)

        # ── RIGHT SIDE (Vehicle Info) ──
        right_frame = ttk.Frame(main_pane, width=320)
        right_frame.pack_propagate(False)

        # Vehicle image — clickable link that opens in browser
        img_frame = ttk.Frame(right_frame, height=200, width=300)
        img_frame.pack_propagate(False)
        img_frame.pack(fill="x", padx=10, pady=(10, 5))
        self.vehicle_image_label = tk.Label(img_frame,
            text="Vehicle Image\n\nConnect & scan a vehicle\nto look up photos",
            anchor="center", bg="#1a1a1a", fg="#888888",
            font=("Segoe UI", 9), cursor="hand2", relief="flat")
        self.vehicle_image_label.pack(fill="both", expand=True)
        self._vehicle_image_url = None

        # Vehicle info text
        info_header = ttk.Frame(right_frame)
        info_header.pack(fill="x", padx=10)
        ttk.Label(info_header, text="Vehicle Information", font=("Segoe UI", 10, "bold")).pack(side="left")
        self.vin_label = ttk.Label(info_header, text="", font=("Consolas", 9), foreground="#888888")
        self.vin_label.pack(side="right")

        self.vehicle_info_text = tk.Text(right_frame, wrap="word", font=("Segoe UI", 9), padx=10, pady=10,
                                         bg="#1a1a1a", fg="#e0e0e0", height=14, state="disabled",
                                         relief="flat", borderwidth=0)
        info_scroll = ttk.Scrollbar(right_frame, orient="vertical", command=self.vehicle_info_text.yview)
        self.vehicle_info_text.configure(yscrollcommand=info_scroll.set)
        self.vehicle_info_text.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=5)
        info_scroll.pack(side="right", fill="y", padx=(0, 10), pady=5)

        # Info text tags
        self.vehicle_info_text.tag_configure("heading", font=("Segoe UI", 11, "bold"), foreground="#ff8800")
        self.vehicle_info_text.tag_configure("label", font=("Segoe UI", 9, "bold"), foreground="#cc6600")
        self.vehicle_info_text.tag_configure("value", font=("Segoe UI", 9))
        self.vehicle_info_text.tag_configure("loading", font=("Segoe UI", 9, "italic"), foreground="#888888")

        right_frame.pack(fill="both", expand=False)
        main_pane.add(right_frame, weight=1)

    # ═══════════════════════════════════════════════════════════════
    # Fault Reading
    # ═══════════════════════════════════════════════════════════════

    def _read_all(self):
        vehicle = self.get_vehicle()
        if not vehicle:
            return

        self.read_btn.config(state="disabled")
        self.clear_btn.config(state="disabled")
        self.ai_btn.config(state="disabled")
        self.tree.delete(*self.tree.get_children())
        self.progress["value"] = 0
        self.all_dtcs = []

        # Try to read VIN in parallel
        def read_thread():
            # Read VIN first
            try:
                vin = vehicle.read_vin()
            except Exception:
                vin = ""

            if vin:
                self.after(0, lambda: self._load_vehicle_info(vin))

            all_dtcs: list[ModuleDTCs] = []
            modules = [m for m in FORD_MODULES if m.abbreviation in (
                "PCM", "TCM", "ABS", "RCM", "IPC", "BCM", "EPAS", "HVAC",
                "ACM", "APIM", "DDM", "PDM", "PAM", "GWM", "TPMS", "HCM",
                "PSCM", "ACC", "FSCM",
            )]

            for i, module in enumerate(modules):
                pct = (i / len(modules)) * 100
                self.after(0, lambda p=pct: self.progress.config(value=p))
                self.after(0, lambda n=module.name: self.status_label.config(text=f"Reading {n}..."))

                try:
                    client = vehicle.get_uds_client(module)
                    reader = DTCReader(client)
                    dtcs = reader.read_dtcs()
                    if dtcs:
                        all_dtcs.append(ModuleDTCs(
                            module_name=module.name,
                            module_abbrev=module.abbreviation,
                            dtcs=dtcs,
                        ))
                except Exception:
                    pass

            self.all_dtcs = all_dtcs
            total = sum(m.count for m in all_dtcs)
            self.after(0, lambda: self._populate_results(all_dtcs))
            self.after(0, lambda: self.count_label.config(text=f"{total} faults found"))
            self.after(0, lambda: self.status_label.config(text=f"Read complete. {total} faults. Click AI Mechanic to diagnose."))
            self.after(0, lambda: self.progress.config(value=100))
            self.after(0, lambda: self.read_btn.config(state="normal"))
            self.after(0, lambda: self.clear_btn.config(state="normal"))
            self.after(0, lambda: self.ai_btn.config(state="normal"))

        threading.Thread(target=read_thread, daemon=True).start()

    def _clear_all(self):
        vehicle = self.get_vehicle()
        if not vehicle:
            return
        if not messagebox.askyesno("Clear Faults", "Clear ALL fault codes from ALL modules?"):
            return
        self.clear_btn.config(state="disabled")

        def clear_thread():
            modules = [m for m in FORD_MODULES if m.abbreviation in ("PCM", "TCM", "ABS", "BCM")]
            cleared = 0
            for module in modules:
                try:
                    client = vehicle.get_uds_client(module)
                    reader = DTCReader(client)
                    reader.clear_dtcs()
                    cleared += 1
                except Exception:
                    pass
            self.after(0, lambda: self.status_label.config(text=f"Faults cleared on {cleared} modules. Re-read to verify."))
            self.after(0, lambda: self.clear_btn.config(state="normal"))

        threading.Thread(target=clear_thread, daemon=True).start()

    def _populate_results(self, all_dtcs: list[ModuleDTCs]):
        self.tree.delete(*self.tree.get_children())
        for mod in all_dtcs:
            for dtc in mod.dtcs:
                if dtc.is_active:
                    tag, status = "active", "ACTIVE"
                elif dtc.is_pending:
                    tag, status = "pending", "PENDING"
                else:
                    tag, status = "stored", "STORED"
                description = lookup_dtc(dtc.code)
                self.tree.insert("", "end", values=(
                    mod.module_abbrev, dtc.code, description, status, dtc.status_text,
                ), tags=(tag,))

    # ═══════════════════════════════════════════════════════════════
    # Vehicle Info
    # ═══════════════════════════════════════════════════════════════

    def _load_vehicle_info(self, vin: str):
        self.vin_label.config(text=f"VIN: {vin}")

        # Show loading
        self.vehicle_info_text.config(state="normal")
        self.vehicle_info_text.delete("1.0", "end")
        self.vehicle_info_text.insert("end", "Decoding VIN...\n", "loading")
        self.vehicle_info_text.config(state="disabled")

        def load_thread():
            info = decode_vin(vin)
            self.after(0, lambda: self._display_vehicle_info(info))
            # Load image if available
            img_url = get_vehicle_image_url(vin, info.get("make", ""), info.get("model", ""), info.get("year", ""))
            if img_url:
                self.after(0, lambda: self._load_vehicle_image(img_url))

        threading.Thread(target=load_thread, daemon=True).start()

    def _display_vehicle_info(self, info: dict):
        self.vehicle_info = info
        self.vehicle_info_text.config(state="normal")
        self.vehicle_info_text.delete("1.0", "end")

        if info.get("error"):
            self.vehicle_info_text.insert("end", f"VIN: {info.get('vin', '?')}\n", "label")
            self.vehicle_info_text.insert("end", f"Could not decode: {info['error']}\n", "loading")
            self.vehicle_info_text.config(state="disabled")
            return

        # VIN breakdown
        self.vehicle_info_text.insert("end", "VIN Breakdown\n", "heading")
        self.vehicle_info_text.insert("end", f"  VIN: ", "label")
        self.vehicle_info_text.insert("end", f"{info.get('vin','?')}\n\n")

        # Vehicle identity
        year = info.get("year", "?")
        make = info.get("make", "?")
        model = info.get("model", "?")
        self.vehicle_info_text.insert("end", f"  {year} {make} {model}\n\n", "heading")

        sections = [
            ("Drivetrain", [
                ("Engine", info.get("engine")),
                ("Displacement", info.get("displacement_l") and f"{info['displacement_l']}L"),
                ("Cylinders", info.get("cylinders")),
                ("Horsepower", info.get("horsepower") and f"{info['horsepower']} hp"),
                ("Transmission", info.get("transmission")),
                ("Drive Type", info.get("drive_type")),
                ("Fuel Type", info.get("fuel_type")),
            ]),
            ("Body", [
                ("Type", info.get("body_class")),
                ("Doors", info.get("doors")),
                ("Trim", info.get("trim")),
                ("GVWR", info.get("gvwr") and f"{info['gvwr']} lbs"),
            ]),
            ("Manufacturing", [
                ("Built At", info.get("built_at")),
                ("Plant", info.get("plant_name")),
                ("Country", info.get("plant_country")),
            ]),
            ("Safety", [
                ("Brake Type", info.get("brake_type")),
                ("Front Airbags", info.get("airbags_front")),
                ("Side Airbags", info.get("airbags_side")),
            ]),
        ]

        for heading, fields in sections:
            visible = [(label, val) for label, val in fields if val]
            if not visible:
                continue
            self.vehicle_info_text.insert("end", f"\n{heading}\n", "label")
            for label, val in visible:
                self.vehicle_info_text.insert("end", f"  {label}: ", "label")
                self.vehicle_info_text.insert("end", f"{val}\n", "value")

        if info.get("notes"):
            self.vehicle_info_text.insert("end", f"\nNotes: {info['notes']}\n", "value")

        self.vehicle_info_text.config(state="disabled")

    def _load_vehicle_image(self, url: str):
        self._vehicle_image_url = url
        # Update label to show clickable prompt
        if url.endswith(".jpg") or url.endswith(".png"):
            self.vehicle_image_label.config(
                text="🖼  Vehicle Image Found\n\nClick to view in browser",
                fg="#44aaff", cursor="hand2")
        else:
            self.vehicle_image_label.config(
                text="🔍  Vehicle Lookup Page\n\nClick to open in browser",
                fg="#44aaff", cursor="hand2")
        self.vehicle_image_label.bind("<Button-1>", lambda e: self._open_vehicle_url())

    # ═══════════════════════════════════════════════════════════════
    # AI Mechanic Chat
    # ═══════════════════════════════════════════════════════════════

    def _open_vehicle_url(self):
        if self._vehicle_image_url:
            webbrowser.open(self._vehicle_image_url)

    def _start_ai_session(self):
        self.ai_btn.config(state="disabled")
        self.chat_input.config(state="normal")
        self.chat_text.config(state="normal")
        self.chat_text.delete("1.0", "end")
        self.chat_text.insert("end", "Starting AI Mechanic session...\n", "system")
        self.chat_status.config(text="Connecting...")

        def init_chat():
            try:
                from modules.ai_chat import MechanicChat

                dtc_data = []
                for mod in self.all_dtcs:
                    mod_dtcs = []
                    for dtc in mod.dtcs:
                        desc = lookup_dtc(dtc.code)
                        mod_dtcs.append({
                            "code": dtc.code,
                            "description": desc,
                            "status": "ACTIVE" if dtc.is_active else ("PENDING" if dtc.is_pending else "STORED"),
                            "status_text": dtc.status_text,
                        })
                    dtc_data.append({
                        "module_name": mod.module_name,
                        "module_abbrev": mod.module_abbrev,
                        "dtcs": mod_dtcs,
                    })

                self.chat = MechanicChat()
                self.chat.start_session(self.vehicle_info, dtc_data)
                if dtc_data:
                    response = self.chat.send_message("Start the diagnosis. What do you see?")
                else:
                    response = self.chat.send_message("Introduce yourself briefly and ask what I'd like help with today.")

                self.after(0, lambda: self._append_chat("mechanic", response))
                self.after(0, lambda: self.chat_status.config(text="Connected — ask anything"))
                self.after(0, lambda: self.ai_btn.config(state="normal"))
            except Exception as e:
                self.after(0, lambda: self._append_chat("error", f"Failed to start AI session: {str(e)}"))
                self.after(0, lambda: self.chat_status.config(text="Error"))
                self.after(0, lambda: self.ai_btn.config(state="normal"))

        threading.Thread(target=init_chat, daemon=True).start()

    def _send_chat(self):
        if not self.chat:
            return
        user_text = self.chat_input.get().strip()
        if not user_text:
            return

        self.chat_input.delete(0, "end")
        self.chat_input.config(state="disabled")
        self._append_chat("user", user_text)
        self.chat_status.config(text="Thinking...")

        def get_response():
            try:
                response = self.chat.send_message(user_text)
                self.after(0, lambda: self._append_chat("mechanic", response))
                self.after(0, lambda: self.chat_status.config(text="Connected — ask anything"))
            except Exception as e:
                self.after(0, lambda: self._append_chat("error", f"Error: {str(e)}"))
                self.after(0, lambda: self.chat_status.config(text="Error"))
            finally:
                self.after(0, lambda: self.chat_input.config(state="normal"))
                self.after(0, lambda: self.chat_input.focus())

        threading.Thread(target=get_response, daemon=True).start()

    def _append_chat(self, role: str, text: str):
        self.chat_text.config(state="normal")
        if role == "mechanic":
            self.chat_text.insert("end", "\n🔧 Mechanic:\n", "mechanic")
        elif role == "user":
            self.chat_text.insert("end", "\n👤 You:\n", "user")
        elif role == "error":
            self.chat_text.insert("end", "\n⚠ ", "error")
        else:
            self.chat_text.insert("end", "\n", "system")
        self.chat_text.insert("end", text + "\n")
        self.chat_text.see("end")
        self.chat_text.config(state="disabled")
