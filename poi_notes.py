#!/usr/bin/env python3
"""POI Notes — two-level campus map annotations with per-hour rich notes."""

import datetime
import json
import os
import shutil
import uuid
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk

BLD_COLORS = ["#E74C3C", "#27AE60", "#2980B9", "#F39C12"]
BLD_HANDLE = 7
BLD_MIN    = 0.005

DEFAULT_RECTS = [
    (0.05, 0.05, 0.25, 0.25),
    (0.75, 0.05, 0.95, 0.25),
    (0.05, 0.75, 0.25, 0.95),
    (0.75, 0.75, 0.95, 0.95),
]

CORNER_KEYS = [
    ("rx1", "ry1"), ("rx2", "ry1"),
    ("rx1", "ry2"), ("rx2", "ry2"),
]

SUB_COLOR     = "#8E44AD"
SUB_RADIUS    = 14
DEFAULT_SUB   = [(0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75)]
MAX_IMG_WIDTH = 400


class MediaEditor(tk.Toplevel):
    """Per-hour rich text + image editor for a sub-marker."""

    def __init__(self, parent, window_title, subtitle, marker_title, content, media_dir, on_save):
        super().__init__(parent)
        self.title(window_title)
        self.geometry("500x500")
        self.resizable(True, True)
        self.grab_set()

        self.media_dir = media_dir
        self.on_save   = on_save
        self._photos   = {}  # tk image name -> PhotoImage (prevent GC)
        self._paths    = {}  # tk image name -> filename relative to media_dir

        tk.Label(self, text=window_title, font=("Helvetica", 13, "bold"), fg=SUB_COLOR).pack(pady=(10, 0))
        tk.Label(self, text=subtitle,     font=("Helvetica", 9),          fg="#888888").pack(pady=(2, 6))

        # Title field
        title_row = tk.Frame(self)
        title_row.pack(fill="x", padx=12, pady=(0, 6))
        tk.Label(title_row, text="Title:", font=("Helvetica", 10, "bold"), width=6, anchor="w").pack(side="left")
        self._title_var = tk.StringVar(value=marker_title)
        tk.Entry(title_row, textvariable=self._title_var,
                 font=("Helvetica", 11)).pack(side="left", fill="x", expand=True)

        # Toolbar
        toolbar = tk.Frame(self, pady=2)
        toolbar.pack(fill="x", padx=12)
        tk.Button(toolbar, text="Insert Image", command=self._add_image).pack(side="left")

        # Text + scrollbar
        frm = tk.Frame(self)
        frm.pack(fill="both", expand=True, padx=12, pady=4)
        sb = tk.Scrollbar(frm)
        sb.pack(side="right", fill="y")
        self.txt = tk.Text(frm, wrap="word", font=("Helvetica", 11), yscrollcommand=sb.set)
        self.txt.pack(fill="both", expand=True)
        sb.config(command=self.txt.yview)

        # Buttons
        row = tk.Frame(self)
        row.pack(fill="x", padx=12, pady=(0, 10))
        tk.Button(row, text="Cancel", width=9, command=self.destroy).pack(side="right", padx=(4, 0))
        tk.Button(row, text="Save",   width=9, command=self._save,
                  bg=SUB_COLOR, fg="white").pack(side="right")

        self._load_content(content)
        self._title_var.trace_add("write", lambda *_: None)  # keep StringVar alive
        self.txt.focus_set()
        self.bind("<Escape>",         lambda _: self.destroy())
        self.bind("<Control-Return>", lambda _: self._save())

    def _load_content(self, content):
        for item in content:
            if item["type"] == "text":
                self.txt.insert(tk.END, item["value"])
            elif item["type"] == "image":
                full = os.path.join(self.media_dir, item["path"])
                if os.path.exists(full):
                    self._insert_photo(full, item["path"])

    def _insert_photo(self, full_path, rel_filename):
        try:
            img = Image.open(full_path)
            if img.width > MAX_IMG_WIDTH:
                img = img.resize(
                    (MAX_IMG_WIDTH, int(img.height * MAX_IMG_WIDTH / img.width)),
                    Image.LANCZOS,
                )
            photo = ImageTk.PhotoImage(img)
            name  = str(photo)
            self._photos[name] = photo
            self._paths[name]  = rel_filename
            self.txt.insert(tk.END, "\n")
            self.txt.image_create(tk.END, image=photo)
            self.txt.insert(tk.END, "\n")
        except Exception:
            pass

    def _add_image(self):
        path = filedialog.askopenfilename(
            title="Select image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"), ("All", "*.*")],
        )
        if not path:
            return
        os.makedirs(self.media_dir, exist_ok=True)
        ext      = os.path.splitext(path)[1].lower() or ".png"
        filename = uuid.uuid4().hex + ext
        shutil.copy2(path, os.path.join(self.media_dir, filename))
        self._insert_photo(os.path.join(self.media_dir, filename), filename)

    def _get_content(self):
        items = []
        buf   = ""
        for key, value, _ in self.txt.dump("1.0", tk.END, text=True, image=True):
            if key == "text":
                buf += value
            elif key == "image":
                if buf.strip():
                    items.append({"type": "text", "value": buf.strip()})
                buf = ""
                rel = self._paths.get(value)
                if rel:
                    items.append({"type": "image", "path": rel})
        if buf.strip():
            items.append({"type": "text", "value": buf.strip()})
        return items

    def _save(self):
        self.on_save(self._title_var.get().strip(), self._get_content())
        self.destroy()


class POIApp:
    def __init__(self, root, image_path):
        self.root       = root
        self.image_path = image_path
        self.data_path  = os.path.splitext(image_path)[0] + "_poi.json"
        self.media_dir  = os.path.splitext(image_path)[0] + "_poi_media"

        root.title(f"POI Notes — {os.path.basename(image_path)}")

        self.orig_image  = Image.open(image_path)
        self.tk_img      = None
        self._resize_job = None
        self.dw = 1
        self.dh = 1
        self.ox = 0
        self.oy = 0

        self.view       = "main"
        self.active_bld = None
        self.zoom_image = None

        now           = datetime.datetime.now()
        self.sel_date = now.date()
        self.sel_hour = now.hour

        # ── top bar: two centred rows (date / time) ───────────────────────────
        top = tk.Frame(root, relief="raised", bd=1, pady=8)
        top.pack(fill="x", side="top")
        top.columnconfigure(1, weight=1)

        # Date row
        tk.Button(top, text="◀", width=3,
                  command=lambda: self._shift_day(-1)).grid(row=0, column=0, padx=12, pady=2)
        self._date_lbl = tk.Label(top, font=("Helvetica", 14, "bold"), anchor="center")
        self._date_lbl.grid(row=0, column=1, sticky="ew")
        tk.Button(top, text="▶", width=3,
                  command=lambda: self._shift_day(1)).grid(row=0, column=2, padx=12, pady=2)

        # Time row
        tk.Button(top, text="◀", width=3,
                  command=lambda: self._shift_hour(-1)).grid(row=1, column=0, padx=12, pady=2)
        self._time_lbl = tk.Label(top, font=("Helvetica", 13), anchor="center")
        self._time_lbl.grid(row=1, column=1, sticky="ew")
        tk.Button(top, text="▶", width=3,
                  command=lambda: self._shift_hour(1)).grid(row=1, column=2, padx=12, pady=2)

        self._update_time_display()

        # ── tab bar ───────────────────────────────────────────────────────────
        self.active_tab = "map"
        tab_bar = tk.Frame(root, bg="#1C1C1E")
        tab_bar.pack(fill="x", side="bottom")
        tab_bar.columnconfigure(0, weight=1)
        tab_bar.columnconfigure(1, weight=1)

        self._tab_map_btn = tk.Button(
            tab_bar, text="Map", font=("Helvetica", 12, "bold"),
            bg="#1C1C1E", fg="white", activebackground="#1C1C1E",
            relief="flat", pady=8, command=self._show_map_tab,
        )
        self._tab_map_btn.grid(row=0, column=0, sticky="ew")

        self._tab_nbr_btn = tk.Button(
            tab_bar, text="Neighbors", font=("Helvetica", 12),
            bg="#1C1C1E", fg="#888888", activebackground="#1C1C1E",
            relief="flat", pady=8, command=self._show_neighbors_tab,
        )
        self._tab_nbr_btn.grid(row=0, column=1, sticky="ew")

        # ── map panel ─────────────────────────────────────────────────────────
        self.map_panel = tk.Frame(root)
        self.map_panel.pack(fill="both", expand=True)

        self.bar      = tk.Frame(self.map_panel, relief="sunken", bd=1)
        self.bar.pack(fill="x", side="bottom")
        self.back_btn = tk.Button(self.bar, text="← Back to Map", command=self._go_back)
        self.add_btn  = tk.Button(self.bar, text="+ Add Marker",  command=self._add_sub_poi)
        self.info_lbl = tk.Label(self.bar, anchor="w", padx=6)

        self.canvas = tk.Canvas(self.map_panel, bg="black")
        self.canvas.pack(fill="both", expand=True)

        # ── neighbors panel ───────────────────────────────────────────────────
        self.nbr_panel = tk.Frame(root, bg="#F2F2F7")

        tk.Label(
            self.nbr_panel, text="Neighbors", bg="#F2F2F7",
            font=("Helvetica", 20, "bold"), pady=20,
        ).pack()

        tk.Label(
            self.nbr_panel,
            text="Link your Instagram so neighbors can find you.",
            bg="#F2F2F7", fg="#555555", font=("Helvetica", 11),
        ).pack(pady=(0, 20))

        insta_row = tk.Frame(self.nbr_panel, bg="#F2F2F7")
        insta_row.pack(padx=30, fill="x")
        tk.Label(insta_row, text="@", bg="#F2F2F7",
                 font=("Helvetica", 16, "bold"), fg="#C13584").pack(side="left")
        self._insta_var = tk.StringVar()
        tk.Entry(
            insta_row, textvariable=self._insta_var,
            font=("Helvetica", 14), relief="flat", bg="white",
        ).pack(side="left", fill="x", expand=True, ipady=6, padx=(4, 0))

        tk.Button(
            self.nbr_panel, text="Save",
            bg="#C13584", fg="white", font=("Helvetica", 12, "bold"),
            relief="flat", padx=20, pady=8,
            command=self._save_instagram,
        ).pack(pady=16)

        self._insta_status = tk.Label(self.nbr_panel, text="", bg="#F2F2F7",
                                      font=("Helvetica", 10), fg="#27AE60")
        self._insta_status.pack()

        self._load_instagram()

        self._bld_items    = {}
        self._sub_items    = {}
        self._action       = None
        self._drag_origin  = (0, 0)
        self._drag_moved   = False
        self._origin_state = {}

        self.buildings = self._load()
        self._refresh()

        self.canvas.bind("<ButtonPress-1>",   self._press)
        self.canvas.bind("<B1-Motion>",       self._motion)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Configure>",       self._on_configure)

    def _show_map_tab(self):
        self.active_tab = "map"
        self._tab_map_btn.config(font=("Helvetica", 12, "bold"), fg="white")
        self._tab_nbr_btn.config(font=("Helvetica", 12), fg="#888888")
        self.nbr_panel.pack_forget()
        self.map_panel.pack(fill="both", expand=True)

    def _show_neighbors_tab(self):
        self.active_tab = "neighbors"
        self._tab_nbr_btn.config(font=("Helvetica", 12, "bold"), fg="white")
        self._tab_map_btn.config(font=("Helvetica", 12), fg="#888888")
        self.map_panel.pack_forget()
        self.nbr_panel.pack(fill="both", expand=True)

    def _save_instagram(self):
        handle = self._insta_var.get().strip().lstrip("@")
        profile = {}
        if os.path.exists(self.data_path):
            with open(self.data_path) as f:
                profile = json.load(f)
        profile["instagram"] = handle
        with open(self.data_path, "w") as f:
            json.dump(profile, f, indent=2)
        self._insta_status.config(text="Saved!" if handle else "Cleared.")

    def _load_instagram(self):
        if os.path.exists(self.data_path):
            with open(self.data_path) as f:
                data = json.load(f)
            self._insta_var.set(data.get("instagram", ""))

    def _note_key(self):
        return f"{self.sel_date.isoformat()}T{self.sel_hour:02d}"

    def _has_note(self, sp):
        content = sp.get("notes", {}).get(self._note_key(), [])
        return any(
            (item["type"] == "text" and item["value"].strip()) or item["type"] == "image"
            for item in content
        )

    def _shift_day(self, delta):
        self.sel_date += datetime.timedelta(days=delta)
        self._update_time_display()
        if self.view == "building":
            self._redraw_sub_pois()

    def _shift_hour(self, delta):
        self.sel_hour = (self.sel_hour + delta) % 24
        self._update_time_display()
        if self.view == "building":
            self._redraw_sub_pois()

    def _update_time_display(self):
        self._date_lbl.config(text=self.sel_date.strftime("%A,  %B %d  %Y"))
        h = self.sel_hour
        self._time_lbl.config(text=f"{h % 12 or 12}:00 {'AM' if h < 12 else 'PM'}")

    def selected_datetime(self):
        return datetime.datetime.combine(self.sel_date, datetime.time(self.sel_hour))

    def _update_bar(self):
        for w in (self.back_btn, self.add_btn, self.info_lbl):
            w.pack_forget()
        if self.view == "main":
            self.info_lbl.config(
                text="Click inside a box to zoom in  •  Drag box to move  •  Drag corner to resize"
            )
            self.info_lbl.pack(fill="x")
        else:
            self.back_btn.pack(side="left", padx=4, pady=3)
            self.add_btn.pack(side="left",  padx=4, pady=3)
            self.info_lbl.config(
                text=f"Building {self.active_bld + 1}  —  click a marker to open  •  drag to reposition"
            )
            self.info_lbl.pack(fill="x")

    def _refresh(self):
        self._update_bar()
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw > 1:
            self._apply_resize(cw, ch)

    def _load(self):
        def_sub = lambda: [
            {"rx": rx, "ry": ry, "title": "", "notes": {}} for rx, ry in DEFAULT_SUB
        ]
        if os.path.exists(self.data_path):
            with open(self.data_path) as f:
                stored = json.load(f).get("buildings", [])
            out = []
            for i in range(len(DEFAULT_RECTS)):
                d = stored[i] if i < len(stored) else {}
                r = DEFAULT_RECTS[i]
                subs = []
                for sp in d.get("sub_pois", []):
                    notes = sp.get("notes", {})
                    subs.append({
                        "rx":    sp.get("rx", 0.5),
                        "ry":    sp.get("ry", 0.5),
                        "title": sp.get("title", ""),
                        "notes": notes if isinstance(notes, dict) else {},
                    })
                out.append({
                    "rx1": d.get("rx1", r[0]), "ry1": d.get("ry1", r[1]),
                    "rx2": d.get("rx2", r[2]), "ry2": d.get("ry2", r[3]),
                    "sub_pois": subs or def_sub(),
                })
            return out
        return [
            {"rx1": r[0], "ry1": r[1], "rx2": r[2], "ry2": r[3], "sub_pois": def_sub()}
            for r in DEFAULT_RECTS
        ]

    def _save(self):
        with open(self.data_path, "w") as f:
            json.dump({"buildings": self.buildings}, f, indent=2)

    def _enter_building(self, idx):
        self.view       = "building"
        self.active_bld = idx
        b      = self.buildings[idx]
        iw, ih = self.orig_image.size
        self.zoom_image = self.orig_image.crop((
            int(b["rx1"] * iw), int(b["ry1"] * ih),
            int(b["rx2"] * iw), int(b["ry2"] * ih),
        ))
        self.root.title(f"POI Notes — Building {idx + 1}")
        self._refresh()

    def _go_back(self):
        self.view       = "main"
        self.active_bld = None
        self.zoom_image = None
        self.root.title(f"POI Notes — {os.path.basename(self.image_path)}")
        self._refresh()

    def _on_configure(self, e):
        if self._resize_job:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(40, lambda: self._apply_resize(e.width, e.height))

    def _apply_resize(self, cw, ch):
        self._resize_job = None
        src    = self.zoom_image if self.view == "building" else self.orig_image
        iw, ih = src.size
        scale  = min(cw / iw, ch / ih)
        self.dw = max(1, int(iw * scale))
        self.dh = max(1, int(ih * scale))
        self.ox = (cw - self.dw) // 2
        self.oy = (ch - self.dh) // 2

        self.tk_img = ImageTk.PhotoImage(src.resize((self.dw, self.dh), Image.LANCZOS))
        self.canvas.delete("all")
        self._bld_items = {}
        self._sub_items = {}
        self.canvas.create_image(self.ox, self.oy, anchor="nw", image=self.tk_img)

        if self.view == "main":
            for i in range(len(self.buildings)):
                self._draw_building(i)
        else:
            self._redraw_sub_pois()

    def _rect_xy(self, i):
        b = self.buildings[i]
        return (
            self.ox + b["rx1"] * self.dw, self.oy + b["ry1"] * self.dh,
            self.ox + b["rx2"] * self.dw, self.oy + b["ry2"] * self.dh,
        )

    def _handle_xy(self, i, corner):
        b      = self.buildings[i]
        rk, ry = CORNER_KEYS[corner]
        return self.ox + b[rk] * self.dw, self.oy + b[ry] * self.dh

    def _draw_building(self, i):
        for cid in self._bld_items.get(i, ()):
            self.canvas.delete(cid)
        color           = BLD_COLORS[i]
        x1, y1, x2, y2 = self._rect_xy(i)
        ids = [
            self.canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=3, fill=""),
            self.canvas.create_text(
                (x1 + x2) / 2, (y1 + y2) / 2,
                text=str(i + 1), font=("Helvetica", 14, "bold"), fill=color,
            ),
        ]
        for corner in range(4):
            hx, hy = self._handle_xy(i, corner)
            ids.append(self.canvas.create_oval(
                hx - BLD_HANDLE, hy - BLD_HANDLE, hx + BLD_HANDLE, hy + BLD_HANDLE,
                fill=color, outline="white", width=2,
            ))
        self._bld_items[i] = ids

    def _sub_xy(self, sub_idx):
        sp = self.buildings[self.active_bld]["sub_pois"][sub_idx]
        return self.ox + sp["rx"] * self.dw, self.oy + sp["ry"] * self.dh

    def _draw_sub_poi(self, sub_idx):
        for cid in self._sub_items.get(sub_idx, ()):
            self.canvas.delete(cid)

        sp       = self.buildings[self.active_bld]["sub_pois"][sub_idx]
        has_note = self._has_note(sp)
        title    = sp.get("title", "").strip()
        x, y     = self._sub_xy(sub_idx)
        ids      = []

        # Title badge above the circle
        if title:
            txt_id = self.canvas.create_text(
                x, y - SUB_RADIUS - 7,
                text=title,
                font=("Helvetica", 9, "bold"),
                fill="white",
                anchor="s",
            )
            bbox = self.canvas.bbox(txt_id)
            if bbox:
                pad   = 3
                bg_id = self.canvas.create_rectangle(
                    bbox[0] - pad, bbox[1] - pad,
                    bbox[2] + pad, bbox[3] + pad,
                    fill=SUB_COLOR, outline="",
                )
                self.canvas.tag_lower(bg_id, txt_id)
                ids += [bg_id, txt_id]
            else:
                ids.append(txt_id)

        # Circle
        ids.append(self.canvas.create_oval(
            x - SUB_RADIUS, y - SUB_RADIUS, x + SUB_RADIUS, y + SUB_RADIUS,
            fill=SUB_COLOR if has_note else "#FFFFFF", outline=SUB_COLOR, width=3,
        ))
        # Number
        ids.append(self.canvas.create_text(
            x, y, text=str(sub_idx + 1),
            font=("Helvetica", 10, "bold"),
            fill="white" if has_note else SUB_COLOR,
        ))

        self._sub_items[sub_idx] = ids

    def _redraw_sub_pois(self):
        sps = self.buildings[self.active_bld]["sub_pois"]
        for i in range(len(sps)):
            self._draw_sub_poi(i)

    def _add_sub_poi(self):
        if self.view != "building":
            return
        sps = self.buildings[self.active_bld]["sub_pois"]
        sps.append({"rx": 0.5, "ry": 0.5, "title": "", "notes": {}})
        self._save()
        self._draw_sub_poi(len(sps) - 1)

    def _hit_main(self, ex, ey):
        for i in range(len(self.buildings)):
            for corner in range(4):
                hx, hy = self._handle_xy(i, corner)
                if abs(ex - hx) <= BLD_HANDLE * 1.6 and abs(ey - hy) <= BLD_HANDLE * 1.6:
                    return ("resize", i, corner)
        for i in range(len(self.buildings)):
            x1, y1, x2, y2 = self._rect_xy(i)
            if x1 <= ex <= x2 and y1 <= ey <= y2:
                return ("move", i)
        return None

    def _hit_building(self, ex, ey):
        for i, _ in enumerate(self.buildings[self.active_bld]["sub_pois"]):
            x, y = self._sub_xy(i)
            if (ex - x) ** 2 + (ey - y) ** 2 <= (SUB_RADIUS * 1.5) ** 2:
                return ("sub", i)
        return None

    def _press(self, e):
        if self.view == "main":
            self._action = self._hit_main(e.x, e.y)
            if self._action:
                b = self.buildings[self._action[1]]
                self._origin_state = {k: b[k] for k in ("rx1", "ry1", "rx2", "ry2")}
        else:
            self._action = self._hit_building(e.x, e.y)
            if self._action:
                sp = self.buildings[self.active_bld]["sub_pois"][self._action[1]]
                self._origin_state = {"rx": sp["rx"], "ry": sp["ry"]}
        self._drag_origin = (e.x, e.y)
        self._drag_moved  = False

    def _motion(self, e):
        if self._action is None:
            return
        dx, dy = e.x - self._drag_origin[0], e.y - self._drag_origin[1]
        if abs(dx) > 3 or abs(dy) > 3:
            self._drag_moved = True
        if not self._drag_moved:
            return

        s   = self._origin_state
        drx = dx / self.dw
        dry = dy / self.dh

        if self._action[0] == "move":
            idx  = self._action[1]
            b    = self.buildings[idx]
            w, h = s["rx2"] - s["rx1"], s["ry2"] - s["ry1"]
            nx1  = max(0.0, min(s["rx1"] + drx, 1.0 - w))
            ny1  = max(0.0, min(s["ry1"] + dry, 1.0 - h))
            b["rx1"], b["ry1"] = nx1, ny1
            b["rx2"], b["ry2"] = nx1 + w, ny1 + h
            self._draw_building(idx)

        elif self._action[0] == "resize":
            idx    = self._action[1]
            b      = self.buildings[idx]
            rk, ry = CORNER_KEYS[self._action[2]]
            ork    = "rx2" if rk == "rx1" else "rx1"
            ory    = "ry2" if ry == "ry1" else "ry1"
            new_rx = max(0.0, min(s[rk] + drx, 1.0))
            new_ry = max(0.0, min(s[ry] + dry, 1.0))
            b[rk]  = min(new_rx, s[ork] - BLD_MIN) if rk == "rx1" else max(new_rx, s[ork] + BLD_MIN)
            b[ry]  = min(new_ry, s[ory] - BLD_MIN) if ry == "ry1" else max(new_ry, s[ory] + BLD_MIN)
            self._draw_building(idx)

        elif self._action[0] == "sub":
            sub_idx = self._action[1]
            sp = self.buildings[self.active_bld]["sub_pois"][sub_idx]
            sp["rx"] = max(0.0, min(s["rx"] + drx, 1.0))
            sp["ry"] = max(0.0, min(s["ry"] + dry, 1.0))
            self._draw_sub_poi(sub_idx)

    def _release(self, e):
        if self._action is not None:
            if self._drag_moved:
                self._save()
            elif self._action[0] == "move":
                self._enter_building(self._action[1])
            elif self._action[0] == "sub":
                self._open_note(self._action[1])
        self._action     = None
        self._drag_moved = False

    def _open_note(self, sub_idx):
        sp      = self.buildings[self.active_bld]["sub_pois"][sub_idx]
        key     = self._note_key()
        content = sp.get("notes", {}).get(key, [])

        def on_save(new_title, new_content):
            sp["title"] = new_title
            sp.setdefault("notes", {})[key] = new_content
            self._save()
            self._draw_sub_poi(sub_idx)

        MediaEditor(
            self.root,
            window_title=f"Building {self.active_bld + 1}  ·  Marker {sub_idx + 1}",
            subtitle=self.selected_datetime().strftime("%A, %B %d %Y  ·  %-I:%M %p"),
            marker_title=sp.get("title", ""),
            content=content,
            media_dir=self.media_dir,
            on_save=on_save,
        )


IMAGE_PATH = os.path.expanduser("~/Downloads/TCNJ_MAP2017.png")


def main():
    root = tk.Tk()
    if not os.path.exists(IMAGE_PATH):
        messagebox.showerror("File not found", f"Could not find:\n{IMAGE_PATH}")
        root.destroy()
        return
    POIApp(root, IMAGE_PATH)
    root.mainloop()


if __name__ == "__main__":
    main()
