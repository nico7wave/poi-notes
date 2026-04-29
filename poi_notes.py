#!/usr/bin/env python3
"""meow — campus map annotations with neighbor matching."""

import datetime
import hashlib
import json
import os
import random
import shutil
import smtplib
import uuid
import tkinter as tk
from email.mime.text import MIMEText
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk

# ── auth paths ────────────────────────────────────────────────────────────────
_DIR          = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_PATH = os.path.join(_DIR, "accounts.json")
SESSION_PATH  = os.path.join(_DIR, "session.json")
MAIL_CFG_PATH = os.path.join(_DIR, "mail_config.json")


def _hash_pw(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000).hex()

def _load_accounts() -> dict:
    if os.path.exists(ACCOUNTS_PATH):
        with open(ACCOUNTS_PATH) as f:
            return json.load(f)
    return {"users": {}}

def _save_accounts(data: dict):
    with open(ACCOUNTS_PATH, "w") as f:
        json.dump(data, f, indent=2)

def _load_session() -> str | None:
    if os.path.exists(SESSION_PATH):
        with open(SESSION_PATH) as f:
            return json.load(f).get("email")
    return None

def _save_session(email: str):
    with open(SESSION_PATH, "w") as f:
        json.dump({"email": email}, f)

def _clear_session():
    if os.path.exists(SESSION_PATH):
        os.remove(SESSION_PATH)

def _send_code(to_email: str, code: str) -> bool:
    """Send verification email. Returns False if SMTP not configured."""
    if not os.path.exists(MAIL_CFG_PATH):
        return False
    try:
        with open(MAIL_CFG_PATH) as f:
            cfg = json.load(f)
        msg = MIMEText(
            f"Hi!\n\nYour meow verification code is:\n\n"
            f"  {code}\n\n"
            f"It expires in 10 minutes. If you didn't request this, ignore this email."
        )
        msg["Subject"] = "meow — verify your email"
        msg["From"]    = cfg["sender"]
        msg["To"]      = to_email
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as s:
            s.login(cfg["sender"], cfg["password"])
            s.send_message(msg)
        return True
    except Exception:
        return False


# ── button style constants (from map-pan: larger fonts for HiDPI) ─────────────
BTN = dict(font=("Helvetica", 28, "bold"), relief="raised", bd=4,
           padx=28, pady=16, cursor="hand2")
BTN_SM = dict(font=("Helvetica", 24, "bold"), relief="raised", bd=3,
              padx=20, pady=12, cursor="hand2")

# ── mock neighbor data (backend will replace) ─────────────────────────────────
MOCK_NEIGHBORS = [
    {"dorm": "Travers Hall, Rm 214",    "instagram": "alex_tcnj",     "show_insta": True,  "show_dorm": True,  "only_to_likers": False},
    {"dorm": "Wolfe Hall, Rm 118",      "instagram": "campus_wolf",   "show_insta": True,  "show_dorm": True,  "only_to_likers": False},
    {"dorm": "Cromwell Hall, Rm 305",   "instagram": "crom_private",  "show_insta": False, "show_dorm": True,  "only_to_likers": False},
    {"dorm": "Eickhoff Hall, Rm 402",   "instagram": "eick_neighbor", "show_insta": True,  "show_dorm": False, "only_to_likers": False},
    {"dorm": "Centennial Hall, Rm 110", "instagram": "cent_hall110",  "show_insta": True,  "show_dorm": True,  "only_to_likers": True},
]
_LIKED_YOU_BACK = {0: False, 1: True, 3: True, 4: True}

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

SUB_COLOR            = "#27AE60"
SUB_RADIUS           = 14
DEFAULT_SUB          = [(0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75)]
MAX_IMG_WIDTH        = 400
ZOOM_STEP            = 1.15
ZOOM_MIN             = 0.5
ZOOM_MAX             = 10.0
ZOOM_LABEL_THRESHOLD = 2.5


class MediaEditor(tk.Toplevel):
    def __init__(self, parent, window_title, subtitle, marker_title, content, media_dir, on_save):
        super().__init__(parent)
        self.title(window_title)
        self.geometry("900x800")
        self.resizable(True, True)
        self.grab_set()

        self.media_dir = media_dir
        self.on_save   = on_save
        self._photos   = {}
        self._paths    = {}

        tk.Label(self, text=window_title, font=("Helvetica", 26, "bold"), fg=SUB_COLOR).pack(pady=(18, 0))
        tk.Label(self, text=subtitle,     font=("Helvetica", 20),         fg="#888888").pack(pady=(4, 10))

        title_row = tk.Frame(self)
        title_row.pack(fill="x", padx=20, pady=(0, 10))
        tk.Label(title_row, text="Title:", font=("Helvetica", 22, "bold"), width=6, anchor="w").pack(side="left")
        self._title_var = tk.StringVar(value=marker_title)
        tk.Entry(title_row, textvariable=self._title_var,
                 font=("Helvetica", 24)).pack(side="left", fill="x", expand=True, ipady=6)

        toolbar = tk.Frame(self, pady=6)
        toolbar.pack(fill="x", padx=20)
        tk.Button(toolbar, text="Insert Image", command=self._add_image, **BTN_SM).pack(side="left")

        frm = tk.Frame(self)
        frm.pack(fill="both", expand=True, padx=20, pady=8)
        sb = tk.Scrollbar(frm)
        sb.pack(side="right", fill="y")
        self.txt = tk.Text(frm, wrap="word", font=("Helvetica", 24), yscrollcommand=sb.set)
        self.txt.pack(fill="both", expand=True)
        sb.config(command=self.txt.yview)

        row = tk.Frame(self)
        row.pack(fill="x", padx=20, pady=(6, 18))
        tk.Button(row, text="Cancel", command=self.destroy, **BTN_SM).pack(side="right", padx=(8, 0))
        tk.Button(row, text="Save", command=self._save,
                  bg=SUB_COLOR, fg="white", **BTN_SM).pack(side="right")

        self._load_content(content)
        self._title_var.trace_add("write", lambda *_: None)
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
    def __init__(self, root, image_path, email="", name="", on_logout=None):
        self.root        = root
        self.image_path  = image_path
        self.data_path   = os.path.splitext(image_path)[0] + "_poi.json"
        self.media_dir   = os.path.splitext(image_path)[0] + "_poi_media"
        self._email      = email
        self._name       = name
        self._on_logout  = on_logout

        root.title("meow")
        root.geometry("1400x1000")
        root.minsize(1000, 700)

        self.orig_image  = Image.open(image_path)
        self.tk_img      = None
        self._resize_job = None
        self.dw = 1
        self.dh = 1
        self.ox = 0
        self.oy = 0

        self.active_bld = None
        self._zoom      = 1.0
        self._pan_x     = 0
        self._pan_y     = 0
        self._pan_last  = (0, 0)
        self._zoom_job  = None

        now           = datetime.datetime.now()
        self.sel_date = now.date()
        self.sel_hour = now.hour

        # ── bottom tab bar ────────────────────────────────────────────────────
        self.active_tab = "map"
        tab_bar = tk.Frame(root, bg="#1C1C1E", pady=0)
        tab_bar.pack(fill="x", side="bottom")
        for c in range(4):
            tab_bar.columnconfigure(c, weight=1)

        tab_cfg = dict(bg="#1C1C1E", activebackground="#2C2C2E",
                       activeforeground="white", relief="flat",
                       pady=22, cursor="hand2", bd=0)

        self._tab_map_btn = tk.Button(
            tab_bar, text="🗺  Map",
            font=("Helvetica", 26, "bold"), fg="white",
            command=self._show_map_tab, **tab_cfg)
        self._tab_map_btn.grid(row=0, column=0, sticky="ew")

        self._tab_nbr_btn = tk.Button(
            tab_bar, text="👥  Neighbors",
            font=("Helvetica", 26), fg="#666666",
            command=self._show_neighbors_tab, **tab_cfg)
        self._tab_nbr_btn.grid(row=0, column=1, sticky="ew")

        self._tab_inbox_btn = tk.Button(
            tab_bar, text="💬  Inbox",
            font=("Helvetica", 26), fg="#666666",
            command=self._show_inbox_tab, **tab_cfg)
        self._tab_inbox_btn.grid(row=0, column=2, sticky="ew")

        self._tab_acct_btn = tk.Button(
            tab_bar, text="👤  Account",
            font=("Helvetica", 26), fg="#666666",
            command=self._show_account_tab, **tab_cfg)
        self._tab_acct_btn.grid(row=0, column=3, sticky="ew")

        # ── map panel ─────────────────────────────────────────────────────────
        self.map_panel = tk.Frame(root)
        self.map_panel.pack(fill="both", expand=True)

        # compact map header
        map_hdr = tk.Frame(self.map_panel, bg="#FFFFFF",
                           highlightbackground="#E8E8E8", highlightthickness=1)
        map_hdr.pack(fill="x", side="top")

        tk.Label(map_hdr, text="meow", bg="#FFFFFF", fg="#27AE60",
                 font=("Helvetica", 20, "bold"), padx=18).pack(side="left", pady=14)

        ctrl = tk.Frame(map_hdr, bg="#FFFFFF")
        ctrl.pack(side="right", padx=16, pady=10)

        dpill = tk.Frame(ctrl, bg="#E9F7EF")
        dpill.pack(side="left", padx=(0, 8))
        tk.Button(dpill, text="◀", command=lambda: self._shift_day(-1),
                  bg="#E9F7EF", fg="#1E8449", relief="flat", bd=0,
                  font=("Helvetica", 13), padx=8, cursor="hand2").pack(side="left", ipady=6)
        self._date_lbl = tk.Label(dpill, text="", bg="#E9F7EF", fg="#145A32",
                                  font=("Helvetica", 13, "bold"), width=11, anchor="center")
        self._date_lbl.pack(side="left")
        tk.Button(dpill, text="▶", command=lambda: self._shift_day(1),
                  bg="#E9F7EF", fg="#1E8449", relief="flat", bd=0,
                  font=("Helvetica", 13), padx=8, cursor="hand2").pack(side="left", ipady=6)

        tpill = tk.Frame(ctrl, bg="#E9F7EF")
        tpill.pack(side="left")
        tk.Button(tpill, text="◀", command=lambda: self._shift_hour(-1),
                  bg="#E9F7EF", fg="#1E8449", relief="flat", bd=0,
                  font=("Helvetica", 13), padx=8, cursor="hand2").pack(side="left", ipady=6)
        self._time_lbl = tk.Label(tpill, text="", bg="#E9F7EF", fg="#145A32",
                                  font=("Helvetica", 13, "bold"), width=6, anchor="center")
        self._time_lbl.pack(side="left")
        tk.Button(tpill, text="▶", command=lambda: self._shift_hour(1),
                  bg="#E9F7EF", fg="#1E8449", relief="flat", bd=0,
                  font=("Helvetica", 13), padx=8, cursor="hand2").pack(side="left", ipady=6)

        self._update_time_display()

        self.bar     = tk.Frame(self.map_panel, relief="sunken", bd=1, pady=4)
        self.bar.pack(fill="x", side="bottom")
        self.add_btn = tk.Button(self.bar, text="+ Marker", command=self._add_sub_poi,
                                 bg="#27AE60", fg="white", **BTN)
        self.info_lbl = tk.Label(self.bar, anchor="w", padx=8, font=("Helvetica", 22))

        self.canvas = tk.Canvas(self.map_panel, bg="white")
        self.canvas.pack(fill="both", expand=True)

        # ── neighbors panel ───────────────────────────────────────────────────
        self.nbr_panel = tk.Frame(root, bg="#F2F2F7")

        nbr_nav = tk.Frame(self.nbr_panel, bg="#F2F2F7")
        nbr_nav.pack(fill="x", padx=20, pady=(18, 0))
        self._nbr_view = "browse"

        self._nbr_profile_btn = tk.Button(
            nbr_nav, text="My Profile", bg="#27AE60", fg="white",
            command=self._show_nbr_profile, **BTN_SM)
        self._nbr_profile_btn.pack(side="left", padx=(0, 14))

        self._nbr_browse_btn = tk.Button(
            nbr_nav, text="Browse", bg="#CCCCCC", fg="#333333",
            command=self._show_nbr_browse, **BTN_SM)
        self._nbr_browse_btn.pack(side="left")

        # ── profile sub-view ──────────────────────────────────────────────────
        self._profile_view = tk.Frame(self.nbr_panel, bg="#F2F2F7")

        tk.Label(self._profile_view, text="My Profile", bg="#F2F2F7",
                 font=("Helvetica", 34, "bold"), pady=14).pack()

        form = tk.Frame(self._profile_view, bg="#F2F2F7")
        form.pack(padx=40, fill="x")

        insta_hdr = tk.Frame(form, bg="#F2F2F7")
        insta_hdr.pack(fill="x", pady=(0, 6))
        tk.Label(insta_hdr, text="Instagram", bg="#F2F2F7",
                 font=("Helvetica", 24, "bold")).pack(side="left")
        self._pub_insta_var = tk.BooleanVar(value=True)
        tk.Checkbutton(insta_hdr, text="Show publicly on my card",
                       variable=self._pub_insta_var, bg="#F2F2F7",
                       font=("Helvetica", 20), fg="#555555").pack(side="left", padx=14)

        insta_row = tk.Frame(form, bg="white", relief="solid", bd=1)
        insta_row.pack(fill="x")
        tk.Label(insta_row, text="@", bg="white",
                 font=("Helvetica", 28, "bold"), fg="#C13584", padx=12).pack(side="left")
        self._insta_var = tk.StringVar()
        tk.Entry(insta_row, textvariable=self._insta_var,
                 font=("Helvetica", 26), relief="flat", bg="white").pack(
                 side="left", fill="x", expand=True, ipady=12)

        dorm_hdr = tk.Frame(form, bg="#F2F2F7")
        dorm_hdr.pack(fill="x", pady=(18, 6))
        tk.Label(dorm_hdr, text="Dorm / Building", bg="#F2F2F7",
                 font=("Helvetica", 24, "bold")).pack(side="left")
        self._pub_dorm_var = tk.BooleanVar(value=True)
        tk.Checkbutton(dorm_hdr, text="Show publicly on my card",
                       variable=self._pub_dorm_var, bg="#F2F2F7",
                       font=("Helvetica", 20), fg="#555555").pack(side="left", padx=14)

        dorm_row = tk.Frame(form, bg="white", relief="solid", bd=1)
        dorm_row.pack(fill="x")
        tk.Label(dorm_row, text="🏠", bg="white",
                 font=("Helvetica", 28), padx=12).pack(side="left")
        self._dorm_var = tk.StringVar()
        tk.Entry(dorm_row, textvariable=self._dorm_var,
                 font=("Helvetica", 26), relief="flat", bg="white").pack(
                 side="left", fill="x", expand=True, ipady=12)

        disc_row = tk.Frame(form, bg="#F2F2F7")
        disc_row.pack(fill="x", pady=(18, 0))
        self._only_likers_var = tk.BooleanVar(value=False)
        tk.Checkbutton(disc_row,
                       text="Only show my profile to people I've already liked",
                       variable=self._only_likers_var, bg="#F2F2F7",
                       font=("Helvetica", 20), fg="#555555",
                       wraplength=600, justify="left").pack(anchor="w")
        tk.Label(form, text="If checked, you won't appear to others unless you liked them first.",
                 bg="#F2F2F7", fg="#AAAAAA", font=("Helvetica", 18),
                 wraplength=600, justify="left").pack(anchor="w", pady=(4, 0))

        tk.Button(self._profile_view, text="Save Profile",
                  bg="#C13584", fg="white", command=self._save_profile,
                  **BTN).pack(pady=22)

        self._insta_status = tk.Label(self._profile_view, text="", bg="#F2F2F7",
                                      font=("Helvetica", 22), fg="#27AE60")
        self._insta_status.pack()

        # ── browse sub-view ───────────────────────────────────────────────────
        self._browse_view = tk.Frame(self.nbr_panel, bg="#F2F2F7")

        tk.Label(self._browse_view, text="Neighbors Near You", bg="#F2F2F7",
                 font=("Helvetica", 34, "bold"), pady=14).pack()
        tk.Label(self._browse_view,
                 text="Your like or pass is completely private until you both match.",
                 bg="#F2F2F7", fg="#666666", font=("Helvetica", 20)).pack(pady=(0, 16))

        self._match_idx    = 0
        self._match_data   = {}
        self._browse_order = [i for i, n in enumerate(MOCK_NEIGHBORS) if n["show_insta"]]

        self._card = tk.Frame(self._browse_view, bg="white", relief="ridge", bd=4,
                              padx=60, pady=40)
        self._card.pack()

        self._card_gram = tk.Label(self._card, text="", bg="white",
                                   font=("Helvetica", 40, "bold"), fg="#C13584")
        self._card_gram.pack(pady=(0, 12))

        self._card_dorm = tk.Label(self._card, text="", bg="white",
                                   font=("Helvetica", 26), fg="#444444")
        self._card_dorm.pack()

        self._card_note = tk.Label(self._card, text="", bg="white",
                                   font=("Helvetica", 20, "italic"), fg="#AAAAAA")
        self._card_note.pack(pady=(10, 0))

        swipe_row = tk.Frame(self._browse_view, bg="#F2F2F7")
        swipe_row.pack(pady=22)

        self._pass_btn = tk.Button(swipe_row, text="✕  Pass",
                                   bg="#E74C3C", fg="white",
                                   command=self._swipe_pass, **BTN)
        self._pass_btn.pack(side="left", padx=24)

        self._like_btn = tk.Button(swipe_row, text="♥  Like",
                                   bg="#27AE60", fg="white",
                                   command=self._swipe_like, **BTN)
        self._like_btn.pack(side="left", padx=24)

        # ── inbox panel ───────────────────────────────────────────────────────
        self.inbox_panel = tk.Frame(root, bg="#F2F2F7")

        tk.Label(self.inbox_panel, text="Inbox", bg="#F2F2F7",
                 font=("Helvetica", 36, "bold"), pady=20).pack()

        self._inbox_list_frame = tk.Frame(self.inbox_panel, bg="#F2F2F7")
        self._inbox_list_frame.pack(fill="both", expand=True, padx=24)

        self._inbox_detail_frame = tk.Frame(self.inbox_panel, bg="#F2F2F7")

        # ── account panel ─────────────────────────────────────────────────────
        self.acct_panel = tk.Frame(root, bg="#F2F2F7")

        tk.Label(self.acct_panel, text="Account", bg="#F2F2F7",
                 font=("Helvetica", 34, "bold"), fg="#1A1A1A", pady=20).pack()

        info_card = tk.Frame(self.acct_panel, bg="#FFFFFF",
                             highlightbackground="#E0E0E0", highlightthickness=1)
        info_card.pack(fill="x", padx=40, pady=(0, 8))
        tk.Label(info_card, text=name or "User", bg="#FFFFFF", fg="#1A1A1A",
                 font=("Helvetica", 22, "bold"), anchor="w").pack(
                 fill="x", padx=24, pady=(20, 4))
        tk.Label(info_card, text=email, bg="#FFFFFF", fg="#888888",
                 font=("Helvetica", 16), anchor="w").pack(
                 fill="x", padx=24, pady=(0, 20))

        tk.Frame(self.acct_panel, bg="#E0E0E0", height=1).pack(fill="x", padx=40, pady=(16, 0))

        HoverButton(self.acct_panel, nbg="#F2F2F7", hbg="#FFE8E8",
                    nfg="#E74C3C", hfg="#C0392B",
                    text="Log Out", font=("Helvetica", 20, "bold"),
                    relief="flat", bd=0, pady=18, cursor="hand2",
                    command=lambda: self._on_logout() if self._on_logout else None
                    ).pack(fill="x", padx=40, pady=(16, 0))

        self._load_profile()
        self._advance_card()
        self._show_nbr_browse()

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
        self.canvas.bind("<MouseWheel>",      self._on_scroll)
        self.canvas.bind("<Button-4>",        self._on_scroll)
        self.canvas.bind("<Button-5>",        self._on_scroll)

    # ── tab switching ─────────────────────────────────────────────────────────

    def _set_tab(self, name):
        self.active_tab = name
        inactive = dict(font=("Helvetica", 26), fg="#666666")
        active   = dict(font=("Helvetica", 26, "bold"), fg="white")
        self._tab_map_btn.config(**(active   if name == "map"       else inactive))
        self._tab_nbr_btn.config(**(active   if name == "neighbors" else inactive))
        self._tab_inbox_btn.config(**(active if name == "inbox"     else inactive))
        self._tab_acct_btn.config(**(active  if name == "account"   else inactive))
        self.map_panel.pack_forget()
        self.nbr_panel.pack_forget()
        self.inbox_panel.pack_forget()
        self.acct_panel.pack_forget()
        if name == "map":
            self.map_panel.pack(fill="both", expand=True)
        elif name == "neighbors":
            self.nbr_panel.pack(fill="both", expand=True)
        elif name == "inbox":
            self._build_inbox()
            self.inbox_panel.pack(fill="both", expand=True)
        else:
            self.acct_panel.pack(fill="both", expand=True)

    def _show_map_tab(self):       self._set_tab("map")
    def _show_neighbors_tab(self): self._set_tab("neighbors")
    def _show_inbox_tab(self):     self._set_tab("inbox")
    def _show_account_tab(self):   self._set_tab("account")

    # ── neighbors sub-views ───────────────────────────────────────────────────

    def _show_nbr_profile(self):
        self._browse_view.pack_forget()
        self._profile_view.pack(fill="both", expand=True)
        self._nbr_profile_btn.config(bg="#27AE60", fg="white")
        self._nbr_browse_btn.config(bg="#CCCCCC", fg="#333333")

    def _show_nbr_browse(self):
        self._profile_view.pack_forget()
        self._browse_view.pack(fill="both", expand=True)
        self._nbr_browse_btn.config(bg="#27AE60", fg="white")
        self._nbr_profile_btn.config(bg="#CCCCCC", fg="#333333")

    # ── profile save / load ───────────────────────────────────────────────────

    def _save_profile(self):
        profile = {}
        if os.path.exists(self.data_path):
            with open(self.data_path) as f:
                profile = json.load(f)
        profile["instagram"]   = self._insta_var.get().strip().lstrip("@")
        profile["dorm"]        = self._dorm_var.get().strip()
        profile["pub_insta"]   = self._pub_insta_var.get()
        profile["pub_dorm"]    = self._pub_dorm_var.get()
        profile["only_likers"] = self._only_likers_var.get()
        with open(self.data_path, "w") as f:
            json.dump(profile, f, indent=2)
        self._insta_status.config(text="Profile saved!")

    def _load_profile(self):
        if not os.path.exists(self.data_path):
            return
        with open(self.data_path) as f:
            data = json.load(f)
        self._insta_var.set(data.get("instagram", ""))
        self._dorm_var.set(data.get("dorm", ""))
        self._pub_insta_var.set(data.get("pub_insta", True))
        self._pub_dorm_var.set(data.get("pub_dorm", True))
        self._only_likers_var.set(data.get("only_likers", False))
        self._match_data = data.get("match_data", {})

    # ── browse / matching ─────────────────────────────────────────────────────

    def _visible_neighbors(self):
        return [i for i in self._browse_order if str(i) not in self._match_data]

    def _advance_card(self):
        remaining = self._visible_neighbors()
        if not remaining:
            self._card_gram.config(text="All done!", fg="#27AE60")
            self._card_dorm.config(text="No new neighbors right now.")
            self._card_note.config(text="Check back later.")
            self._pass_btn.config(state="disabled")
            self._like_btn.config(text="♥  Like", bg="#27AE60",
                                  command=self._swipe_like, state="disabled")
            return

        self._match_idx = remaining[0]
        nb = MOCK_NEIGHBORS[self._match_idx]
        self._card_gram.config(
            text=f"@{nb['instagram']}" if nb["show_insta"] else "@hidden",
            fg="#C13584")
        self._card_dorm.config(text=nb["dorm"] if nb["show_dorm"] else "Dorm hidden")
        self._card_note.config(text="instagram & dorm visible · swipe to connect")
        self._pass_btn.config(state="normal")
        self._like_btn.config(text="♥  Like", bg="#27AE60",
                              command=self._swipe_like, state="normal")

    def _swipe_pass(self):
        self._match_data[str(self._match_idx)] = "passed"
        self._persist_match_data()
        self._advance_card()

    def _swipe_like(self):
        idx = self._match_idx
        if _LIKED_YOU_BACK.get(idx, False):
            self._match_data[str(idx)] = "matched"
            self._persist_match_data()
            nb = MOCK_NEIGHBORS[idx]
            self._card_gram.config(text=f"@{nb['instagram']}", fg="#F39C12")
            self._card_dorm.config(text=nb["dorm"])
            self._card_note.config(
                text="It's a match!  Check your Inbox ✉",
                fg="#C13584", font=("Helvetica", 22, "bold"))
            self._pass_btn.config(state="disabled")
            self._like_btn.config(text="Next  →", bg="#2980B9",
                                  command=self._next_after_match, state="normal")
            self._tab_inbox_btn.config(text="💬  Inbox ●", fg="#F39C12",
                                       font=("Helvetica", 26, "bold"))
        else:
            self._match_data[str(idx)] = "liked"
            self._persist_match_data()
            self._advance_card()

    def _next_after_match(self):
        self._card_note.config(fg="#AAAAAA", font=("Helvetica", 20, "italic"))
        self._advance_card()

    def _persist_match_data(self):
        profile = {}
        if os.path.exists(self.data_path):
            with open(self.data_path) as f:
                profile = json.load(f)
        profile["match_data"] = self._match_data
        with open(self.data_path, "w") as f:
            json.dump(profile, f, indent=2)

    # ── inbox ─────────────────────────────────────────────────────────────────

    def _build_inbox(self):
        self._inbox_detail_frame.pack_forget()
        for w in self._inbox_list_frame.winfo_children():
            w.destroy()

        matches = [(int(k), v) for k, v in self._match_data.items() if v == "matched"]

        if not matches:
            tk.Label(self._inbox_list_frame,
                     text="No matches yet.\nGo browse some neighbors!",
                     bg="#F2F2F7", fg="#888888",
                     font=("Helvetica", 26), justify="center").pack(pady=60)
            return

        for idx, _ in matches:
            nb  = MOCK_NEIGHBORS[idx]
            row = tk.Frame(self._inbox_list_frame, bg="white",
                           relief="ridge", bd=2, padx=20, pady=16)
            row.pack(fill="x", pady=8)
            tk.Label(row, text=f"@{nb['instagram']}", bg="white",
                     font=("Helvetica", 28, "bold"), fg="#C13584").pack(anchor="w")
            tk.Label(row, text=nb["dorm"], bg="white",
                     font=("Helvetica", 22), fg="#555555").pack(anchor="w")
            tk.Label(row, text="Matched!", bg="white",
                     font=("Helvetica", 20, "italic"), fg="#27AE60").pack(anchor="w")
            tk.Button(row, text="View Profile →",
                      bg="#27AE60", fg="white",
                      command=lambda n=nb: self._open_match_detail(n),
                      **BTN_SM).pack(anchor="e", pady=(8, 0))

    def _open_match_detail(self, nb):
        self._inbox_list_frame.pack_forget()
        for w in self._inbox_detail_frame.winfo_children():
            w.destroy()
        self._inbox_detail_frame.pack(fill="both", expand=True, padx=36, pady=14)

        tk.Button(self._inbox_detail_frame, text="← Back",
                  command=self._close_match_detail,
                  bg="#CCCCCC", fg="#333333", **BTN_SM).pack(anchor="w", pady=(0, 20))
        tk.Label(self._inbox_detail_frame, text=f"@{nb['instagram']}",
                 bg="#F2F2F7", font=("Helvetica", 42, "bold"), fg="#C13584").pack()
        tk.Label(self._inbox_detail_frame, text=nb["dorm"],
                 bg="#F2F2F7", font=("Helvetica", 28), fg="#444444").pack(pady=(10, 0))
        tk.Label(self._inbox_detail_frame, text="Matched with you",
                 bg="#F2F2F7", font=("Helvetica", 22, "italic"), fg="#27AE60").pack(pady=(6, 28))
        tk.Button(self._inbox_detail_frame, text="💬  Chat",
                  bg="#2980B9", fg="white",
                  command=lambda: self._open_chat(nb),
                  **BTN).pack()

    def _close_match_detail(self):
        self._inbox_detail_frame.pack_forget()
        self._inbox_list_frame.pack(fill="both", expand=True)

    def _open_chat(self, nb):
        win = tk.Toplevel(self.root)
        win.title(f"Chat with @{nb['instagram']}")
        win.geometry("700x800")
        win.grab_set()

        tk.Label(win, text=f"@{nb['instagram']}",
                 font=("Helvetica", 28, "bold"), fg="#C13584").pack(pady=(18, 0))
        tk.Label(win, text=nb["dorm"],
                 font=("Helvetica", 20), fg="#888888").pack(pady=(4, 12))

        frm = tk.Frame(win)
        frm.pack(fill="both", expand=True, padx=14, pady=4)
        sb = tk.Scrollbar(frm)
        sb.pack(side="right", fill="y")
        chat_log = tk.Text(frm, wrap="word", font=("Helvetica", 22),
                           state="disabled", yscrollcommand=sb.set, bg="#F9F9F9")
        chat_log.pack(fill="both", expand=True)
        sb.config(command=chat_log.yview)

        entry_row = tk.Frame(win)
        entry_row.pack(fill="x", padx=14, pady=(0, 14))
        msg_var = tk.StringVar()
        entry = tk.Entry(entry_row, textvariable=msg_var,
                         font=("Helvetica", 24), relief="solid", bd=1)
        entry.pack(side="left", fill="x", expand=True, ipady=10, padx=(0, 10))

        def send(_=None):
            msg = msg_var.get().strip()
            if not msg:
                return
            chat_log.config(state="normal")
            chat_log.insert(tk.END, f"You:  {msg}\n\n")
            chat_log.config(state="disabled")
            chat_log.see(tk.END)
            msg_var.set("")

        tk.Button(entry_row, text="Send", bg="#2980B9", fg="white",
                  command=send, **BTN_SM).pack(side="left")
        entry.bind("<Return>", send)
        entry.focus_set()

    # ── map methods ───────────────────────────────────────────────────────────

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
        if self.dw > 1:
            self._redraw_sub_pois()

    def _shift_hour(self, delta):
        self.sel_hour = (self.sel_hour + delta) % 24
        self._update_time_display()
        if self.dw > 1:
            self._redraw_sub_pois()

    def _update_time_display(self):
        self._date_lbl.config(text=self.sel_date.strftime("%b %d, %Y"))
        h = self.sel_hour
        self._time_lbl.config(text=f"{h % 12 or 12} {'AM' if h < 12 else 'PM'}")

    def selected_datetime(self):
        return datetime.datetime.combine(self.sel_date, datetime.time(self.sel_hour))

    def _update_bar(self):
        for w in (self.add_btn, self.info_lbl):
            w.pack_forget()
        if self.active_bld is None:
            self.info_lbl.config(
                text="Scroll to zoom  •  Drag to pan  •  Click a box to select  •  Drag corner to resize"
            )
            self.info_lbl.pack(fill="x")
        else:
            self.add_btn.pack(side="left", padx=8, pady=6)
            self.info_lbl.config(
                text=f"Building {self.active_bld + 1} selected  —  + Marker to add  •  click empty space to deselect"
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
        data = {}
        if os.path.exists(self.data_path):
            with open(self.data_path) as f:
                data = json.load(f)
        data["buildings"] = self.buildings
        with open(self.data_path, "w") as f:
            json.dump(data, f, indent=2)

    def _on_configure(self, e):
        if self._resize_job:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(40, lambda: self._apply_resize(e.width, e.height))

    def _apply_resize(self, cw, ch, resample=Image.LANCZOS):
        self._resize_job = None
        iw, ih  = self.orig_image.size
        fit     = min(cw / iw, ch / ih)
        scale   = fit * self._zoom
        self.dw = max(1, int(iw * scale))
        self.dh = max(1, int(ih * scale))
        self.ox = (cw - self.dw) // 2 + self._pan_x
        self.oy = (ch - self.dh) // 2 + self._pan_y

        self.canvas.delete("all")
        self._bld_items = {}
        self._sub_items = {}

        vx1 = max(0, self.ox);  vy1 = max(0, self.oy)
        vx2 = min(cw, self.ox + self.dw);  vy2 = min(ch, self.oy + self.dh)
        if vx2 > vx1 and vy2 > vy1:
            cx1 = max(0, int((vx1 - self.ox) / self.dw * iw))
            cy1 = max(0, int((vy1 - self.oy) / self.dh * ih))
            cx2 = min(iw, int((vx2 - self.ox) / self.dw * iw) + 1)
            cy2 = min(ih, int((vy2 - self.oy) / self.dh * ih) + 1)
            crop = self.orig_image.crop((cx1, cy1, cx2, cy2))
            self.tk_img = ImageTk.PhotoImage(
                crop.resize((vx2 - vx1, vy2 - vy1), resample)
            )
            self.canvas.create_image(vx1, vy1, anchor="nw", image=self.tk_img)

        for i in range(len(self.buildings)):
            self._draw_building(i)
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
                text=str(i + 1), font=("Helvetica", 22, "bold"), fill=color,
            ),
        ]
        for corner in range(4):
            hx, hy = self._handle_xy(i, corner)
            ids.append(self.canvas.create_oval(
                hx - BLD_HANDLE, hy - BLD_HANDLE, hx + BLD_HANDLE, hy + BLD_HANDLE,
                fill=color, outline="white", width=2,
            ))
        self._bld_items[i] = ids

    def _sub_xy(self, bld_idx, sub_idx):
        b  = self.buildings[bld_idx]
        sp = b["sub_pois"][sub_idx]
        rx = b["rx1"] + sp["rx"] * (b["rx2"] - b["rx1"])
        ry = b["ry1"] + sp["ry"] * (b["ry2"] - b["ry1"])
        return self.ox + rx * self.dw, self.oy + ry * self.dh

    def _draw_sub_poi(self, bld_idx, sub_idx):
        key = (bld_idx, sub_idx)
        for cid in self._sub_items.get(key, ()):
            self.canvas.delete(cid)

        sp       = self.buildings[bld_idx]["sub_pois"][sub_idx]
        has_note = self._has_note(sp)
        title    = sp.get("title", "").strip()
        x, y     = self._sub_xy(bld_idx, sub_idx)
        ids      = []

        if title and self._zoom >= ZOOM_LABEL_THRESHOLD:
            txt_id = self.canvas.create_text(
                x, y - SUB_RADIUS - 7, text=title,
                font=("Helvetica", 16, "bold"), fill="white", anchor="s",
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

        ids.append(self.canvas.create_oval(
            x - SUB_RADIUS, y - SUB_RADIUS, x + SUB_RADIUS, y + SUB_RADIUS,
            fill=SUB_COLOR if has_note else "#FFFFFF", outline=SUB_COLOR, width=3,
        ))
        ids.append(self.canvas.create_text(
            x, y, text=str(sub_idx + 1),
            font=("Helvetica", 18, "bold"),
            fill="white" if has_note else SUB_COLOR,
        ))
        self._sub_items[key] = ids

    def _redraw_sub_pois(self):
        for bi, bld in enumerate(self.buildings):
            for si in range(len(bld["sub_pois"])):
                self._draw_sub_poi(bi, si)

    def _add_sub_poi(self):
        if self.active_bld is None:
            return
        sps = self.buildings[self.active_bld]["sub_pois"]
        sps.append({"rx": 0.5, "ry": 0.5, "title": "", "notes": {}})
        self._save()
        self._draw_sub_poi(self.active_bld, len(sps) - 1)

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

    def _hit_sub_pois(self, ex, ey):
        for bi, bld in enumerate(self.buildings):
            for si in range(len(bld["sub_pois"])):
                x, y = self._sub_xy(bi, si)
                if (ex - x) ** 2 + (ey - y) ** 2 <= (SUB_RADIUS * 1.5) ** 2:
                    return ("sub", bi, si)
        return None

    def _press(self, e):
        hit = self._hit_sub_pois(e.x, e.y)
        if hit:
            self._action = hit
            sp = self.buildings[hit[1]]["sub_pois"][hit[2]]
            self._origin_state = {"rx": sp["rx"], "ry": sp["ry"]}
        else:
            self._action = self._hit_main(e.x, e.y)
            if self._action:
                b = self.buildings[self._action[1]]
                self._origin_state = {k: b[k] for k in ("rx1", "ry1", "rx2", "ry2")}
        if self._action is None:
            self._action   = ("pan",)
            self._pan_last = (e.x, e.y)
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
            bi  = self._action[1]
            si  = self._action[2]
            b   = self.buildings[bi]
            sp  = b["sub_pois"][si]
            bpw = (b["rx2"] - b["rx1"]) * self.dw
            bph = (b["ry2"] - b["ry1"]) * self.dh
            sp["rx"] = max(0.0, min(s["rx"] + dx / bpw, 1.0))
            sp["ry"] = max(0.0, min(s["ry"] + dy / bph, 1.0))
            self._draw_sub_poi(bi, si)

        elif self._action[0] == "pan":
            px = e.x - self._pan_last[0]
            py = e.y - self._pan_last[1]
            if px or py:
                self.canvas.move("all", px, py)
                self.ox     += px
                self.oy     += py
                self._pan_x += px
                self._pan_y += py
            self._pan_last = (e.x, e.y)

    def _release(self, e):
        if self._action is not None:
            if self._action[0] == "pan":
                if not self._drag_moved:
                    self.active_bld = None
                    self._update_bar()
            elif self._drag_moved:
                self._save()
            elif self._action[0] == "move":
                self.active_bld = self._action[1]
                self._update_bar()
            elif self._action[0] == "sub":
                self._open_note(self._action[1], self._action[2])
        self._action     = None
        self._drag_moved = False

    def _open_note(self, bld_idx, sub_idx):
        sp      = self.buildings[bld_idx]["sub_pois"][sub_idx]
        key     = self._note_key()
        content = sp.get("notes", {}).get(key, [])

        def on_save(new_title, new_content):
            sp["title"] = new_title
            sp.setdefault("notes", {})[key] = new_content
            self._save()
            self._draw_sub_poi(bld_idx, sub_idx)

        MediaEditor(
            self.root,
            window_title=f"Building {bld_idx + 1}  ·  Marker {sub_idx + 1}",
            subtitle=self.selected_datetime().strftime("%A, %B %d %Y  ·  %I:%M %p").replace(" 0", " "),
            marker_title=sp.get("title", ""),
            content=content,
            media_dir=self.media_dir,
            on_save=on_save,
        )

    def _on_scroll(self, e):
        if hasattr(e, "delta") and e.delta:
            direction = 1 if e.delta > 0 else -1
        elif e.num == 4:
            direction = 1
        elif e.num == 5:
            direction = -1
        else:
            return

        new_zoom = max(ZOOM_MIN, min(ZOOM_MAX, self._zoom * (ZOOM_STEP ** direction)))
        if new_zoom == self._zoom:
            return

        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()

        mx = (e.x - self.ox) / self.dw if self.dw else 0.5
        my = (e.y - self.oy) / self.dh if self.dh else 0.5

        self._zoom = new_zoom
        iw, ih    = self.orig_image.size
        fit       = min(cw / iw, ch / ih)
        new_dw    = max(1, int(iw * fit * self._zoom))
        new_dh    = max(1, int(ih * fit * self._zoom))

        self._pan_x = round(e.x - mx * new_dw - (cw - new_dw) // 2)
        self._pan_y = round(e.y - my * new_dh - (ch - new_dh) // 2)

        self._apply_resize(cw, ch, resample=Image.NEAREST)
        if self._zoom_job:
            self.root.after_cancel(self._zoom_job)
        self._zoom_job = self.root.after(
            80, lambda: self._apply_resize(
                self.canvas.winfo_width(), self.canvas.winfo_height()
            )
        )


class HoverButton(tk.Button):
    def __init__(self, master, *, nbg, hbg, nfg="white", hfg="white", **kw):
        super().__init__(master, bg=nbg, fg=nfg,
                         activebackground=hbg, activeforeground=hfg, **kw)
        self.bind("<Enter>", lambda _: self.config(bg=hbg, fg=hfg))
        self.bind("<Leave>", lambda _: self.config(bg=nbg, fg=nfg))


class LoginWindow:
    HEADER   = "#145A32"
    PURPLE   = "#27AE60"
    PURPLE_D = "#1E8449"
    BG       = "#FFFFFF"
    FIELD_BG = "#F0FAF4"
    ERR      = "#E74C3C"

    def __init__(self, root: tk.Tk, on_success):
        self.root       = root
        self.on_success = on_success
        self._code      = None
        self._code_ts   = None
        self._reg_email = None

        root.title("meow")
        root.minsize(420, 580)
        root.configure(bg=self.BG)

        self._f_login    = self._build_login()
        self._f_register = self._build_register()
        self._f_verify   = self._build_verify()
        self._show("login")

    def _show(self, which):
        for f in (self._f_login, self._f_register, self._f_verify):
            f.place_forget()
        {"login": self._f_login, "register": self._f_register,
         "verify": self._f_verify}[which].place(relx=0, rely=0, relwidth=1, relheight=1)

    def _field(self, parent, label, show="", on_return=None):
        tk.Label(parent, text=label, bg=self.BG, fg="#999999",
                 font=("Helvetica", 10, "bold"), anchor="w").pack(fill="x", pady=(16, 2))
        border = tk.Frame(parent, bg="#DEDEDE", padx=1, pady=1)
        border.pack(fill="x")
        var = tk.StringVar()
        e = tk.Entry(border, textvariable=var, show=show,
                     font=("Helvetica", 15), relief="flat",
                     bg=self.FIELD_BG, insertbackground=self.PURPLE)
        e.pack(fill="x", ipady=11, padx=2, pady=1)
        e.bind("<FocusIn>",  lambda _: border.config(bg=self.PURPLE))
        e.bind("<FocusOut>", lambda _: border.config(bg="#DEDEDE"))
        if on_return:
            e.bind("<Return>", lambda _: on_return())
        return var

    def _primary_btn(self, parent, text, command, pady_top=20):
        HoverButton(parent, nbg=self.PURPLE, hbg=self.PURPLE_D,
                    text=text, font=("Helvetica", 14, "bold"),
                    relief="flat", pady=13, cursor="hand2",
                    command=command).pack(fill="x", pady=(pady_top, 0))

    def _outline_btn(self, parent, text, command, pady_top=12):
        HoverButton(parent, nbg=self.BG, hbg="#D5F5E3",
                    nfg=self.PURPLE, hfg=self.PURPLE_D,
                    text=text, font=("Helvetica", 13, "bold"),
                    relief="solid", bd=1, pady=11, cursor="hand2",
                    command=command).pack(fill="x", pady=(pady_top, 0))

    def _err_lbl(self, parent):
        lbl = tk.Label(parent, text="", bg=self.BG, fg=self.ERR,
                       font=("Helvetica", 11), wraplength=320, justify="center")
        lbl.pack(pady=(10, 0))
        return lbl

    def _build_login(self):
        f = tk.Frame(self.root, bg=self.BG)

        hdr = tk.Frame(f, bg=self.HEADER, height=200)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="meow", bg=self.HEADER, fg="white",
                 font=("Helvetica", 58, "bold")).pack(expand=True, pady=(36, 0))
        tk.Label(hdr, text="campus map · TCNJ", bg=self.HEADER, fg="#A9DFBF",
                 font=("Helvetica", 13)).pack(pady=(2, 32))

        body = tk.Frame(f, bg=self.BG, padx=44)
        body.pack(fill="both", expand=True)

        self._login_email = self._field(body, "EMAIL", on_return=self._do_login)
        self._login_pw    = self._field(body, "PASSWORD", show="•", on_return=self._do_login)
        self._login_err   = self._err_lbl(body)

        self._primary_btn(body, "Log In", self._do_login)

        div = tk.Frame(body, bg=self.BG, height=30)
        div.pack(fill="x", pady=(20, 0))
        div.pack_propagate(False)
        tk.Frame(div, bg="#EEEEEE", height=1).pack(side="left", fill="x", expand=True, pady=14)
        tk.Label(div, text="  or  ", bg=self.BG, fg="#CCCCCC",
                 font=("Helvetica", 11)).pack(side="left")
        tk.Frame(div, bg="#EEEEEE", height=1).pack(side="left", fill="x", expand=True, pady=14)

        self._outline_btn(body, "Create Account", lambda: self._show("register"), pady_top=0)

        return f

    def _build_register(self):
        f = tk.Frame(self.root, bg=self.BG, padx=44)

        nav = tk.Frame(f, bg=self.BG)
        nav.pack(fill="x", pady=(20, 0))
        HoverButton(nav, nbg=self.BG, hbg="#D5F5E3", nfg=self.PURPLE, hfg=self.PURPLE_D,
                    text="← Back", font=("Helvetica", 12), relief="flat", bd=0,
                    cursor="hand2", command=lambda: self._show("login")).pack(side="left")

        tk.Label(f, text="Create Account", bg=self.BG, fg="#1A1A1A",
                 font=("Helvetica", 24, "bold")).pack(anchor="w", pady=(12, 0))
        tk.Label(f, text="Use your TCNJ email to get started", bg=self.BG, fg="#AAAAAA",
                 font=("Helvetica", 12)).pack(anchor="w", pady=(2, 0))

        self._reg_name_var  = self._field(f, "FULL NAME")
        self._reg_email_var = self._field(f, "EMAIL")
        self._reg_pw_var    = self._field(f, "PASSWORD  (min 8 chars)", show="•")
        self._reg_pw2_var   = self._field(f, "CONFIRM PASSWORD", show="•",
                                          on_return=self._do_register)
        self._reg_err       = self._err_lbl(f)

        self._primary_btn(f, "Send Verification Code", self._do_register)
        return f

    def _build_verify(self):
        f = tk.Frame(self.root, bg=self.BG, padx=44)

        nav = tk.Frame(f, bg=self.BG)
        nav.pack(fill="x", pady=(20, 0))
        HoverButton(nav, nbg=self.BG, hbg="#D5F5E3", nfg=self.PURPLE, hfg=self.PURPLE_D,
                    text="← Back", font=("Helvetica", 12), relief="flat", bd=0,
                    cursor="hand2", command=lambda: self._show("register")).pack(side="left")

        tk.Label(f, text="Check your email", bg=self.BG, fg="#1A1A1A",
                 font=("Helvetica", 24, "bold")).pack(anchor="w", pady=(24, 0))
        self._verify_sub = tk.Label(f, text="", bg=self.BG, fg="#888888",
                                    font=("Helvetica", 12), wraplength=320, justify="left")
        self._verify_sub.pack(anchor="w", pady=(4, 0))

        tk.Label(f, text="6-DIGIT CODE", bg=self.BG, fg="#999999",
                 font=("Helvetica", 10, "bold"), anchor="w").pack(fill="x", pady=(28, 2))
        code_border = tk.Frame(f, bg="#DEDEDE", padx=1, pady=1)
        code_border.pack(fill="x")
        self._verify_code_var = tk.StringVar()
        code_e = tk.Entry(code_border, textvariable=self._verify_code_var,
                          font=("Helvetica", 28, "bold"), width=8,
                          justify="center", relief="flat",
                          bg=self.FIELD_BG, insertbackground=self.PURPLE)
        code_e.pack(ipady=12, padx=2, pady=1)
        code_e.bind("<FocusIn>",  lambda _: code_border.config(bg=self.PURPLE))
        code_e.bind("<FocusOut>", lambda _: code_border.config(bg="#DEDEDE"))
        code_e.bind("<Return>",   lambda _: self._do_verify())

        self._verify_err = self._err_lbl(f)
        self._primary_btn(f, "Verify & Create Account", self._do_verify)

        row = tk.Frame(f, bg=self.BG)
        row.pack(pady=(16, 0))
        HoverButton(row, nbg=self.BG, hbg="#D5F5E3", nfg=self.PURPLE, hfg=self.PURPLE_D,
                    text="Resend code", font=("Helvetica", 12), relief="flat", bd=0,
                    cursor="hand2", command=self._resend_code).pack(side="left")
        return f

    def _do_login(self):
        email = self._login_email.get().strip().lower()
        pw    = self._login_pw.get()
        self._login_err.config(text="")

        if not email or not pw:
            self._login_err.config(text="Please fill in all fields.")
            return
        db   = _load_accounts()
        user = db["users"].get(email)
        if not user:
            self._login_err.config(text="No account found for that email.")
            return
        if not user.get("verified"):
            self._login_err.config(text="Email not verified. Create your account again.")
            return
        if _hash_pw(pw, user["salt"]) != user["password_hash"]:
            self._login_err.config(text="Incorrect password.")
            return
        _save_session(email)
        self._launch(email, user["name"])

    def _do_register(self):
        name  = self._reg_name_var.get().strip()
        email = self._reg_email_var.get().strip().lower()
        pw    = self._reg_pw_var.get()
        pw2   = self._reg_pw2_var.get()
        self._reg_err.config(text="")

        if not all([name, email, pw, pw2]):
            self._reg_err.config(text="Please fill in all fields.")
            return
        if len(pw) < 8:
            self._reg_err.config(text="Password must be at least 8 characters.")
            return
        if pw != pw2:
            self._reg_err.config(text="Passwords don't match.")
            return
        if "@" not in email or "." not in email.split("@")[-1]:
            self._reg_err.config(text="Please enter a valid email address.")
            return
        db = _load_accounts()
        if email in db["users"] and db["users"][email].get("verified"):
            self._reg_err.config(text="An account with that email already exists.")
            return

        salt = uuid.uuid4().hex
        db["users"][email] = {
            "name":          name,
            "salt":          salt,
            "password_hash": _hash_pw(pw, salt),
            "verified":      False,
            "created_at":    datetime.datetime.now().isoformat(),
        }
        _save_accounts(db)

        self._reg_email = email
        self._code      = str(random.randint(100_000, 999_999))
        self._code_ts   = datetime.datetime.now()

        sent = _send_code(email, self._code)
        if sent:
            self._verify_sub.config(text=f"We sent a 6-digit code to {email}")
        else:
            self._verify_sub.config(
                text=f"SMTP not configured — your code is: {self._code}"
            )
        self._verify_code_var.set("")
        self._verify_err.config(text="")
        self._show("verify")

    def _do_verify(self):
        entered = self._verify_code_var.get().strip()
        self._verify_err.config(text="")

        if not self._code:
            self._verify_err.config(text="No code pending. Go back and try again.")
            return
        age = (datetime.datetime.now() - self._code_ts).total_seconds()
        if age > 600:
            self._verify_err.config(text="Code expired. Please resend.")
            return
        if entered != self._code:
            self._verify_err.config(text="Incorrect code.")
            return

        db = _load_accounts()
        db["users"][self._reg_email]["verified"] = True
        _save_accounts(db)
        _save_session(self._reg_email)
        user = db["users"][self._reg_email]
        self._launch(self._reg_email, user["name"])

    def _resend_code(self):
        if not self._reg_email:
            return
        self._code    = str(random.randint(100_000, 999_999))
        self._code_ts = datetime.datetime.now()
        sent = _send_code(self._reg_email, self._code)
        if sent:
            self._verify_sub.config(text=f"New code sent to {self._reg_email}")
        else:
            self._verify_sub.config(text=f"SMTP not configured — new code: {self._code}")
        self._verify_err.config(text="")

    def _launch(self, email, name):
        for w in self.root.winfo_children():
            w.destroy()
        self.root.configure(bg="black")
        self.root.resizable(True, True)
        try:
            self.root.state("zoomed")
        except Exception:
            self.root.geometry("1400x1000")
        self.on_success(email, name)


IMAGE_PATH = "/mnt/c/Users/antho/Downloads/TCNJ_2017MAP.png"


def main():
    import sys
    dev_mode = "--dev" in sys.argv

    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.6)
    except Exception:
        pass

    if not os.path.exists(IMAGE_PATH):
        messagebox.showerror("File not found", f"Could not find:\n{IMAGE_PATH}")
        root.destroy()
        return

    def do_logout():
        _clear_session()
        for w in root.winfo_children():
            w.destroy()
        root.configure(bg="#FFFFFF")
        LoginWindow(root, launch_app)

    def launch_app(email, name):
        POIApp(root, IMAGE_PATH, email=email, name=name, on_logout=do_logout)
        root.title(f"meow  —  {name}")

    def _maximize():
        try:
            root.state("zoomed")
        except Exception:
            root.geometry("1400x1000")

    if dev_mode:
        root.configure(bg="black")
        _maximize()
        launch_app("dev@local", "Dev")
        root.mainloop()
        return

    saved_email = _load_session()
    if saved_email:
        db   = _load_accounts()
        user = db["users"].get(saved_email)
        if user and user.get("verified"):
            root.configure(bg="black")
            _maximize()
            launch_app(saved_email, user["name"])
            root.mainloop()
            return

    root.geometry("420x600")
    LoginWindow(root, launch_app)
    root.mainloop()


if __name__ == "__main__":
    main()
