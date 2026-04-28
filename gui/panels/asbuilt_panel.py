import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
from core.vehicle import VehicleConnection
from core.protocols import FORD_MODULES
from modules.asbuilt import AsBuiltReader, ModuleAsBuilt


class AsBuiltPanel(ttk.Frame):
    def __init__(self, parent, get_vehicle: callable):
        super().__init__(parent)
        self.get_vehicle = get_vehicle
        self.asbuilt_data: list[ModuleAsBuilt] = []
        self._build_ui()

    def _build_ui(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 5))

        self.read_btn = ttk.Button(toolbar, text="Read Factory Settings", command=self._read_all)
        self.read_btn.pack(side="left", padx=2)

        self.export_btn = ttk.Button(toolbar, text="Export", command=self._export)
        self.export_btn.pack(side="left", padx=2)

        self.import_btn = ttk.Button(toolbar, text="Import & Write", command=self._import_write)
        self.import_btn.pack(side="left", padx=2)

        self.progress = ttk.Progressbar(toolbar, mode="determinate", length=200)
        self.progress.pack(side="left", padx=10)

        self.status_label = ttk.Label(self, text="Ready")
        self.status_label.pack(fill="x")

        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)

        self.module_list = tk.Listbox(left_frame, width=25, font=("Consolas", 10))
        mod_scroll = ttk.Scrollbar(left_frame, orient="vertical", command=self.module_list.yview)
        self.module_list.configure(yscrollcommand=mod_scroll.set)
        self.module_list.pack(side="left", fill="both", expand=True)
        mod_scroll.pack(side="right", fill="y")
        self.module_list.bind("<<ListboxSelect>>", self._on_module_select)

        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=3)

        self.data_text = tk.Text(right_frame, wrap="none", font=("Consolas", 10))
        data_scroll_y = ttk.Scrollbar(right_frame, orient="vertical", command=self.data_text.yview)
        data_scroll_x = ttk.Scrollbar(right_frame, orient="horizontal", command=self.data_text.xview)
        self.data_text.configure(yscrollcommand=data_scroll_y.set, xscrollcommand=data_scroll_x.set)

        data_scroll_y.pack(side="right", fill="y")
        data_scroll_x.pack(side="bottom", fill="x")
        self.data_text.pack(fill="both", expand=True)

    def _read_all(self):
        vehicle = self.get_vehicle()
        if not vehicle:
            return

        self.read_btn.config(state="disabled")
        self.progress["value"] = 0

        def read_thread():
            try:
                reader = AsBuiltReader(vehicle)

                def progress_cb(name, current, total):
                    pct = (current / total) * 100
                    self.after(0, lambda: self.progress.config(value=pct))
                    self.after(0, lambda: self.status_label.config(text=f"Reading {name}..."))

                self.asbuilt_data = reader.read_all_modules(callback=progress_cb)

                self.after(0, self._populate_module_list)
                self.after(0, lambda: self.status_label.config(
                    text=f"Read {len(self.asbuilt_data)} modules"
                ))
            except Exception as e:
                self.after(0, lambda: self.status_label.config(text=f"Error: {e}"))
            finally:
                self.after(0, lambda: self.read_btn.config(state="normal"))
                self.after(0, lambda: self.progress.config(value=100))

        threading.Thread(target=read_thread, daemon=True).start()

    def _populate_module_list(self):
        self.module_list.delete(0, "end")
        for mod in self.asbuilt_data:
            self.module_list.insert("end", f"{mod.module_abbrev} ({len(mod.blocks)} blocks)")

    def _on_module_select(self, event):
        sel = self.module_list.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < len(self.asbuilt_data):
            mod = self.asbuilt_data[idx]
            self.data_text.delete("1.0", "end")
            self.data_text.insert("1.0", mod.to_forscan_format())

    def _export(self):
        if not self.asbuilt_data:
            messagebox.showwarning("Export", "Read factory settings first")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".abt",
            filetypes=[("As-Built Profile", "*.abt"), ("Text", "*.txt"), ("All", "*.*")],
            title="Export Factory Settings",
        )
        if not path:
            return

        try:
            profile = AsBuiltReader.export_profile(self.asbuilt_data)
            with open(path, "w") as f:
                f.write(profile)
            self.status_label.config(text=f"Exported to {path}")
        except Exception as e:
            messagebox.showerror("Export Failed", str(e))

    def _import_write(self):
        vehicle = self.get_vehicle()
        if not vehicle:
            return

        path = filedialog.askopenfilename(
            filetypes=[("As-Built Profile", "*.abt"), ("Text", "*.txt"), ("All", "*.*")],
            title="Import Factory Settings",
        )
        if not path:
            return

        try:
            with open(path, "r") as f:
                text = f.read()
            profile = AsBuiltReader.parse_profile(text)
        except Exception as e:
            messagebox.showerror("Import Failed", str(e))
            return

        module_list = ", ".join(profile.keys())
        block_count = sum(len(v) for v in profile.values())
        msg = (
            f"Write factory settings to vehicle?\n\n"
            f"Modules: {module_list}\n"
            f"Total blocks: {block_count}\n\n"
            f"WARNING: Writing incorrect factory settings can cause modules to malfunction."
        )
        if not messagebox.askyesno("Write Factory Settings", msg, icon="warning"):
            return

        self.import_btn.config(state="disabled")

        def write_thread():
            reader = AsBuiltReader(vehicle)
            written = 0
            errors = 0
            for abbrev, blocks in profile.items():
                module = next((m for m in FORD_MODULES if m.abbreviation == abbrev), None)
                if not module:
                    self.after(0, lambda a=abbrev: self.status_label.config(
                        text=f"Unknown module: {a}"
                    ))
                    continue
                for did, data in blocks:
                    try:
                        reader.write_block(module, did, data)
                        written += 1
                    except Exception as e:
                        errors += 1

            self.after(0, lambda: self.status_label.config(
                text=f"Written {written} blocks, {errors} errors"
            ))
            self.after(0, lambda: self.import_btn.config(state="normal"))

        threading.Thread(target=write_thread, daemon=True).start()
