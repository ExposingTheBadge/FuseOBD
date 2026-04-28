import tkinter as tk
from tkinter import ttk

DARK = {
    "bg": "#2b2b2b",
    "bg1": "#333333",
    "bg2": "#3c3c3c",
    "bg3": "#4a4a4a",
    "border": "#555555",
    "green": "#55ff55",
    "red": "#ff4444",
    "amber": "#ffaa00",
    "cyan": "#66ccff",
    "blue": "#5599dd",
    "text": "#ffffff",
    "dim": "#bbbbbb",
    "select_bg": "#4477aa",
    "select_fg": "#ffffff",
    "entry_bg": "#333333",
    "tree_row_alt": "#343434",
}

LIGHT = {
    "bg": "#f0f0f0",
    "bg1": "#ffffff",
    "bg2": "#fafafa",
    "bg3": "#e8e8e8",
    "border": "#cccccc",
    "green": "#28a745",
    "red": "#dc3545",
    "amber": "#e67e00",
    "cyan": "#0077b6",
    "blue": "#0066cc",
    "text": "#1a1a1a",
    "dim": "#666666",
    "select_bg": "#0066cc",
    "select_fg": "#ffffff",
    "entry_bg": "#ffffff",
    "tree_row_alt": "#f5f5f5",
}

_current = "light"


def current_theme() -> str:
    return _current


def apply_theme(root: tk.Tk, name: str):
    global _current
    _current = name
    c = DARK if name == "dark" else LIGHT
    style = ttk.Style(root)
    style.theme_use("clam")

    root.configure(bg=c["bg"])

    style.configure(".", background=c["bg"], foreground=c["text"],
                     bordercolor=c["border"], focuscolor=c["blue"],
                     troughcolor=c["bg1"])
    style.configure("TFrame", background=c["bg"])
    style.configure("TLabel", background=c["bg"], foreground=c["text"])
    style.configure("TLabelframe", background=c["bg"], foreground=c["text"],
                     bordercolor=c["border"])
    style.configure("TLabelframe.Label", background=c["bg"], foreground=c["blue"])
    style.configure("TButton", background=c["bg2"], foreground=c["text"],
                     bordercolor=c["border"], padding=(8, 4))
    style.map("TButton",
              background=[("active", c["bg3"]), ("pressed", c["bg3"])],
              foreground=[("active", c["text"])])
    style.configure("TNotebook", background=c["bg"], bordercolor=c["border"],
                     tabmargins=[2, 5, 2, 0])
    style.configure("TNotebook.Tab", background=c["bg1"], foreground=c["dim"],
                     padding=(12, 6), bordercolor=c["border"])
    style.map("TNotebook.Tab",
              background=[("selected", c["bg2"])],
              foreground=[("selected", c["text"])])
    style.configure("Treeview", background=c["bg1"], foreground=c["text"],
                     fieldbackground=c["bg1"], bordercolor=c["border"],
                     rowheight=24)
    style.configure("Treeview.Heading", background=c["bg2"], foreground=c["dim"],
                     bordercolor=c["border"], relief="flat")
    style.map("Treeview",
              background=[("selected", c["select_bg"])],
              foreground=[("selected", c["select_fg"])])
    style.map("Treeview.Heading",
              background=[("active", c["bg3"])])
    style.configure("TCombobox", fieldbackground=c["entry_bg"],
                     background=c["bg2"], foreground=c["text"],
                     bordercolor=c["border"], arrowcolor=c["dim"],
                     selectbackground=c["select_bg"],
                     selectforeground=c["select_fg"])
    style.map("TCombobox",
              fieldbackground=[("readonly", c["entry_bg"]),
                               ("readonly focus", c["entry_bg"])],
              foreground=[("readonly", c["text"])],
              selectbackground=[("readonly", c["entry_bg"])],
              selectforeground=[("readonly", c["text"])],
              bordercolor=[("focus", c["blue"])])
    style.configure("TEntry", fieldbackground=c["entry_bg"],
                     foreground=c["text"], bordercolor=c["border"],
                     selectbackground=c["select_bg"],
                     selectforeground=c["select_fg"])
    style.map("TEntry", bordercolor=[("focus", c["blue"])])
    style.configure("TProgressbar", background=c["blue"], troughcolor=c["bg1"],
                     bordercolor=c["border"])
    style.configure("TPanedwindow", background=c["bg"])
    style.configure("Sash", sashthickness=4, gripcount=0,
                     background=c["border"])
    style.configure("TSeparator", background=c["border"])
    style.configure("TScrollbar", background=c["bg2"], troughcolor=c["bg"],
                     bordercolor=c["border"], arrowcolor=c["dim"])
    style.map("TScrollbar",
              background=[("active", c["bg3"]), ("pressed", c["bg3"])])
    style.configure("TCheckbutton", background=c["bg"], foreground=c["text"],
                     indicatorcolor=c["entry_bg"])
    style.map("TCheckbutton",
              background=[("active", c["bg"])],
              indicatorcolor=[("selected", c["blue"])])
    style.configure("TRadiobutton", background=c["bg"], foreground=c["text"],
                     indicatorcolor=c["entry_bg"])
    style.map("TRadiobutton",
              background=[("active", c["bg"])],
              indicatorcolor=[("selected", c["blue"])])

    root.option_add("*TCombobox*Listbox.background", c["entry_bg"])
    root.option_add("*TCombobox*Listbox.foreground", c["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", c["select_bg"])
    root.option_add("*TCombobox*Listbox.selectForeground", c["select_fg"])

    _apply_to_widget_tree(root, c)


def _apply_to_widget_tree(widget, c):
    wclass = widget.winfo_class()

    if wclass == "Text":
        widget.configure(bg=c["bg1"], fg=c["text"],
                         insertbackground=c["text"],
                         selectbackground=c["select_bg"],
                         selectforeground=c["select_fg"])
    elif wclass == "Listbox":
        widget.configure(bg=c["bg1"], fg=c["text"],
                         selectbackground=c["select_bg"],
                         selectforeground=c["select_fg"],
                         highlightbackground=c["border"])
    elif wclass in ("Label", "Frame"):
        try:
            widget.configure(bg=c["bg"])
            if wclass == "Label":
                current_fg = str(widget.cget("fg"))
                if current_fg not in ("red", "#ff0000", "green", "#00ff00",
                                      "#008000", "#2070c0"):
                    widget.configure(fg=c["text"])
        except tk.TclError:
            pass
    elif wclass == "Toplevel":
        try:
            widget.configure(bg=c["bg"])
        except tk.TclError:
            pass
    elif wclass == "Menu":
        widget.configure(bg=c["bg1"], fg=c["text"],
                         activebackground=c["select_bg"],
                         activeforeground=c["select_fg"],
                         borderwidth=0)
    elif wclass == "Canvas":
        try:
            widget.configure(bg=c["bg"])
        except tk.TclError:
            pass

    for child in widget.winfo_children():
        _apply_to_widget_tree(child, c)
