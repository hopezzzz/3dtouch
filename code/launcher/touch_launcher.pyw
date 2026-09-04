"""Graphical launcher for the 3D Systems Touch programs.

Pick a program on the left, read what it does on the right, press 启动.

Only one program can hold the haptic device at a time, so the launcher
runs one at a time and blocks the button until it exits.

    pythonw touch_launcher.pyw     # no console window
    python touch_launcher.pyw      # same, with a console for tracebacks
    python touch_launcher.pyw --selftest   # build the UI and exit
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import font as tkfont
from tkinter import messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catalog  # noqa: E402

# Muted palette; the point is to read the descriptions, not the chrome.
BG = "#f4f5f7"
PANEL = "#ffffff"
INK = "#1c1f23"
MUTED = "#6b7280"
ACCENT = "#1a6fb4"
OK = "#15803d"
BAD = "#b91c1c"
STAR = "#b45309"

DEVICE_POLL_MS = 8000
PROC_POLL_MS = 400


def pick_font(*names, size=10, weight="normal"):
    available = set(tkfont.families())
    for n in names:
        if n in available:
            return tkfont.Font(family=n, size=size, weight=weight)
    return tkfont.Font(size=size, weight=weight)


class Launcher(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=0)
        self.items = catalog.flatten()
        # Treeview values are strings, so address entries by position rather
        # than trying to round-trip an object through the widget.
        self.index_of = {id(app): i for i, (_cat, app) in enumerate(self.items)}
        self.proc: subprocess.Popen | None = None
        self.running_app: catalog.App | None = None
        self.selected: catalog.App | None = None
        self._device_q: queue.Queue = queue.Queue()

        self.ui_font = pick_font("Microsoft YaHei UI", "Microsoft YaHei",
                                 "Segoe UI", size=10)
        self.bold_font = pick_font("Microsoft YaHei UI", "Microsoft YaHei",
                                   "Segoe UI", size=10, weight="bold")
        self.title_font = pick_font("Microsoft YaHei UI", "Microsoft YaHei",
                                    "Segoe UI", size=15, weight="bold")
        self.mono_font = pick_font("Consolas", "Courier New", size=9)

        self._build_styles()
        self._build_ui()
        self._populate()
        self.pack(fill="both", expand=True)

        self.after(200, self._poll_device_queue)
        self._refresh_device()

    # ---------------------------------------------------------------- chrome

    def _build_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=self.ui_font, background=BG, foreground=INK)
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=INK)
        style.configure("Panel.TLabel", background=PANEL, foreground=INK)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED)
        style.configure("Title.TLabel", font=self.title_font, background=BG)
        style.configure("Head.TLabel", font=self.title_font, background=PANEL)
        style.configure("TButton", padding=(14, 7))
        style.configure("Go.TButton", font=self.bold_font, padding=(20, 9))
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                        rowheight=25, font=self.ui_font)
        style.configure("Treeview.Heading", font=self.bold_font)
        style.map("Treeview", background=[("selected", ACCENT)],
                  foreground=[("selected", "#ffffff")])

    def _build_ui(self):
        # ---- header
        header = ttk.Frame(self, padding=(16, 12, 16, 8))
        header.pack(fill="x")
        ttk.Label(header, text="3D Systems Touch 启动器",
                  style="Title.TLabel").pack(side="left")

        self.device_label = ttk.Label(header, text="● 正在检测设备…",
                                      style="Muted.TLabel")
        self.device_label.pack(side="right")

        # ---- body: list | detail
        body = ttk.Frame(self, padding=(16, 0, 16, 8))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3, minsize=300)
        body.columnconfigure(1, weight=4, minsize=330)
        body.rowconfigure(1, weight=1)

        # search row
        search_row = ttk.Frame(body)
        search_row.grid(row=0, column=0, sticky="ew", pady=(0, 6), padx=(0, 8))
        ttk.Label(search_row, text="搜索").pack(side="left", padx=(0, 6))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._populate())
        entry = ttk.Entry(search_row, textvariable=self.search_var)
        entry.pack(side="left", fill="x", expand=True)
        self.picks_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(search_row, text="只看推荐 ★", variable=self.picks_var,
                        command=self._populate).pack(side="left", padx=(8, 0))

        # tree
        tree_wrap = ttk.Frame(body)
        tree_wrap.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        tree_wrap.rowconfigure(0, weight=1)
        tree_wrap.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(tree_wrap, show="tree", selectmode="browse")
        self.tree.grid(row=0, column=0, sticky="nsew")
        bar = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree.yview)
        bar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.tag_configure("category", font=self.bold_font, foreground=MUTED)
        self.tree.tag_configure("pick", foreground=STAR)
        self.tree.tag_configure("missing", foreground=BAD)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda _e: self.launch())
        self.tree.bind("<Return>", lambda _e: self.launch())

        # detail panel
        detail = ttk.Frame(body, style="Panel.TFrame", padding=16)
        detail.grid(row=0, column=1, rowspan=2, sticky="nsew")
        detail.columnconfigure(0, weight=1)
        detail.rowconfigure(2, weight=1)

        self.detail_title = ttk.Label(detail, text="选一个程序",
                                      style="Head.TLabel", anchor="w")
        self.detail_title.grid(row=0, column=0, sticky="ew")

        self.detail_kind = ttk.Label(detail, text="", style="PanelMuted.TLabel",
                                     anchor="w")
        self.detail_kind.grid(row=1, column=0, sticky="ew", pady=(2, 10))

        self.detail_text = tk.Text(detail, wrap="word", height=9, relief="flat",
                                   background=PANEL, foreground=INK,
                                   font=self.ui_font, borderwidth=0,
                                   highlightthickness=0, cursor="arrow")
        self.detail_text.grid(row=2, column=0, sticky="nsew")
        self.detail_text.configure(state="disabled")

        self.path_label = ttk.Label(detail, text="", style="PanelMuted.TLabel",
                                    font=self.mono_font, anchor="w",
                                    justify="left", wraplength=380)
        self.path_label.grid(row=3, column=0, sticky="ew", pady=(10, 12))

        btn_row = ttk.Frame(detail, style="Panel.TFrame")
        btn_row.grid(row=4, column=0, sticky="ew")
        self.launch_btn = ttk.Button(btn_row, text="启动", style="Go.TButton",
                                     command=self.launch, state="disabled")
        self.launch_btn.pack(side="left")
        self.stop_btn = ttk.Button(btn_row, text="关闭运行中的程序",
                                   command=self.stop_running, state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))
        ttk.Button(btn_row, text="打开所在文件夹",
                   command=self.open_folder).pack(side="right")

        # ---- status bar
        status = ttk.Frame(self, padding=(16, 6, 16, 10))
        status.pack(fill="x")
        self.status_label = ttk.Label(status, text="就绪", style="Muted.TLabel")
        self.status_label.pack(side="left")
        ttk.Label(status, text=f"驱动目录 {catalog.ROOT}",
                  style="Muted.TLabel", font=self.mono_font).pack(side="right")

    # ---------------------------------------------------------------- list

    def _populate(self):
        needle = self.search_var.get().strip().lower()
        picks_only = self.picks_var.get()
        self.tree.delete(*self.tree.get_children())

        shown = 0
        for category, apps in catalog.CATALOGUE:
            matches = []
            for app in apps:
                if picks_only and not app.pick:
                    continue
                if needle and needle not in (app.name + " " + app.desc).lower():
                    continue
                matches.append(app)
            if not matches:
                continue
            node = self.tree.insert("", "end", text=category, open=True,
                                    tags=("category",))
            for app in matches:
                label = ("★ " if app.pick else "   ") + app.name
                tags = []
                if not app.exists:
                    label += "  [缺失]"
                    tags.append("missing")
                elif app.pick:
                    tags.append("pick")
                if app.console:
                    label += "  [无图形]"
                self.tree.insert(node, "end", text=label, tags=tuple(tags),
                                 values=(self.index_of[id(app)],))
                shown += 1

        self._set_status(f"共 {shown} 个程序" if shown else "没有匹配的程序")

    def _on_select(self, _event=None):
        app = self._current_app()
        self.selected = app
        if app is None:
            self.detail_title.configure(text="选一个程序")
            self.detail_kind.configure(text="")
            self._set_detail("")
            self.path_label.configure(text="")
            self.launch_btn.configure(state="disabled")
            return

        self.detail_title.configure(text=app.name)
        kind = "控制台程序，没有 3D 窗口" if app.console else "图形程序"
        if not app.exists:
            kind = "文件缺失"
        self.detail_kind.configure(text=kind + ("　★ 推荐" if app.pick else ""))
        self._set_detail(app.desc)
        self.path_label.configure(
            text=f"程序  {app.exe}\n目录  {app.workdir}"
        )
        self.launch_btn.configure(
            state=("normal" if app.exists and self.proc is None else "disabled")
        )

    def _current_app(self):
        sel = self.tree.selection()
        if not sel:
            return None
        values = self.tree.item(sel[0], "values")
        if not values:
            return None
        return self.items[int(values[0])][1]

    def _set_detail(self, text):
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", text)
        self.detail_text.configure(state="disabled")

    def _set_status(self, text):
        self.status_label.configure(text=text)

    # ---------------------------------------------------------------- launch

    def launch(self):
        app = self.selected
        if app is None or not app.exists:
            return
        if self.proc is not None:
            messagebox.showinfo(
                "设备已被占用",
                f"「{self.running_app.name}」还在运行。\n\n"
                "设备一次只能被一个程序占用，请先关掉它。")
            return
        try:
            self.proc = catalog.spawn(app)
        except OSError as exc:
            messagebox.showerror("启动失败", f"{app.name}\n\n{exc}")
            self.proc = None
            return

        self.running_app = app
        self.launch_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self._set_status(f"正在运行：{app.name}")
        self.after(PROC_POLL_MS, self._poll_proc)

    def _poll_proc(self):
        if self.proc is None:
            return
        if self.proc.poll() is None:
            self.after(PROC_POLL_MS, self._poll_proc)
            return
        code = self.proc.returncode
        name = self.running_app.name if self.running_app else "程序"
        self.proc = None
        self.running_app = None
        self.stop_btn.configure(state="disabled")
        self._on_select()
        # GLUT demos routinely exit non-zero when you just close the window.
        self._set_status(f"「{name}」已退出" + (f"（退出码 {code}）" if code else ""))

    def stop_running(self):
        if self.proc is None:
            return
        try:
            self.proc.terminate()
        except OSError:
            pass

    def open_folder(self):
        app = self.selected
        target = app.workdir if app else catalog.ROOT
        if os.path.isdir(target):
            webbrowser.open(target)

    # ---------------------------------------------------------------- device

    def _refresh_device(self):
        threading.Thread(target=self._device_worker, daemon=True).start()
        self.after(DEVICE_POLL_MS, self._refresh_device)

    def _device_worker(self):
        try:
            self._device_q.put(catalog.device_status())
        except Exception as exc:          # never kill the poll thread
            self._device_q.put((False, f"检测出错: {exc}"))

    def _poll_device_queue(self):
        try:
            while True:
                online, text = self._device_q.get_nowait()
                self.device_label.configure(
                    text=("● 设备在线 · " + text) if online else ("● " + text),
                    foreground=(OK if online else BAD),
                )
        except queue.Empty:
            pass
        self.after(200, self._poll_device_queue)


def main():
    root = tk.Tk()
    root.title("3D Systems Touch 启动器")
    root.configure(background=BG)
    root.geometry("1000x640")
    root.minsize(820, 520)
    Launcher(root)

    if "--selftest" in sys.argv:
        root.update_idletasks()
        print("UI built OK;", len(catalog.flatten()), "entries")
        root.destroy()
        return 0

    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
