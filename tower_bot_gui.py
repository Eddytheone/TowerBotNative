#!/usr/bin/env python3
"""
tower_bot_gui.py

Tower Bot GUI v2.13 – user interface for Tower Bot Core with:
 • Feature toggles & thresholds
 • Wave display
 • Perk‐order editor
 • Coords tab (regions + float gem + def‐tab tap coords capture)
 • Setup tab (bulk region capture & template export)

Coords and Setup tabs stay in sync.
"""
from __future__ import annotations
import json
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from PIL import Image, ImageTk

from config import REGION_FILE
from engine import BotConfig, TowerBot, load_regions
from adb_utils import mac_screencap, ensure_app_running


class TowerBotGUI(tk.Tk):
    def __init__(self, cfg: BotConfig):
        super().__init__()
        self.title("Tower Bot v2.13")
        self.cfg = cfg
        self.bot = TowerBot(self.cfg)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # region-capture state
        self._capture_attr: str | None = None
        self._capture_coords: list[tuple[int,int]] = []
        self._capture_img_full: Image.Image
        self._capture_scale: float
        # for Setup tab labels
        self._setup_labels: dict[str, ttk.Label] = {}

        self._build_gui()
        self._update_wave_label()

    def _build_gui(self):
        pad = {'padx': 5, 'pady': 2}
        main = ttk.Frame(self)
        main.pack(padx=10, pady=10)

        # Feature toggles
        self.vars: dict[str, tk.BooleanVar] = {}
        def mkchk(text: str, attr: str, row: int):
            var = tk.BooleanVar(value=getattr(self.cfg, attr))
            chk = ttk.Checkbutton(
                main, text=text, variable=var,
                command=lambda: setattr(self.cfg, attr, var.get())
            )
            chk.grid(row=row, column=0, sticky='w', **pad)
            self.vars[attr] = var

        mkchk("Retry",        'retry_enabled',   0)
        mkchk("Health Up",    'health_enabled',  1)
        mkchk("AbsDef Up",    'abs_def_enabled', 2)
        mkchk("Claim Gems",   'gems_enabled',    3)
        mkchk("Float Gem",    'float_enabled',   4)
        mkchk("Auto Perk",    'perk_enabled',    5)
        mkchk("Debug",        'debug_enabled',   6)

        # Stop-after-wave spinboxes
        ttk.Label(main, text="Stop Health after:").grid(row=7, column=0, **pad)
        self.sh = ttk.Spinbox(
            main, from_=0, to=999999, width=6,
            command=lambda: setattr(self.cfg, 'health_stop', int(self.sh.get()))
        )
        self.sh.delete(0, 'end'); self.sh.insert(0, str(self.cfg.health_stop))
        self.sh.grid(row=7, column=1, **pad)

        ttk.Label(main, text="Stop AbsDef after:").grid(row=8, column=0, **pad)
        self.sa = ttk.Spinbox(
            main, from_=0, to=999999, width=6,
            command=lambda: setattr(self.cfg, 'abs_def_stop', int(self.sa.get()))
        )
        self.sa.delete(0, 'end'); self.sa.insert(0, str(self.cfg.abs_def_stop))
        self.sa.grid(row=8, column=1, **pad)

        ttk.Label(main, text="Stop Perks after:").grid(row=9, column=0, **pad)
        self.sp = ttk.Spinbox(
            main, from_=0, to=999999, width=6,
            command=lambda: setattr(self.cfg, 'perk_stop', int(self.sp.get()))
        )
        self.sp.delete(0, 'end'); self.sp.insert(0, str(self.cfg.perk_stop))
        self.sp.grid(row=9, column=1, **pad)

        # Start/Stop & Wave display
        self.btn = ttk.Button(main, text="Start", command=self._toggle)
        self.btn.grid(row=10, column=0, columnspan=2, **pad)

        self.wave_lbl = ttk.Label(main, text="Wave: –", font=(None, 12, 'bold'))
        self.wave_lbl.grid(row=11, column=0, columnspan=2, **pad)

        # Notebook
        nb = ttk.Notebook(self)
        nb.pack(fill='both', expand=True, padx=10, pady=(0,10))

        # Tab 1: Perk Order
        t1 = ttk.Frame(nb); nb.add(t1, text="Perk Order")
        self.lb = tk.Listbox(t1, height=16)
        self.lb.pack(side='left', fill='both', expand=True, padx=(10,0), pady=10)
        for p in self.cfg.perk_priority:
            self.lb.insert('end', p)
        fb = ttk.Frame(t1); fb.pack(side='right', padx=5, pady=10)
        ttk.Button(fb, text="Up",   command=self._move_up).pack(fill='x', pady=2)
        ttk.Button(fb, text="Down", command=self._move_down).pack(fill='x', pady=2)

        # Tab 2: Coords
        t2 = ttk.Frame(nb); nb.add(t2, text="Coords")
        cf = ttk.Frame(t2); cf.pack(padx=10, pady=10)
        regions = [
            ('new_perk_region','NewPerk',4),
            ('perk1_region','Perk1',4),
            ('perk2_region','Perk2',4),
            ('perk3_region','Perk3',4),
            ('perk4_region','Perk4',4),
            ('retry1_region','Retry1',4),
            ('retry2_region','Retry2',4),
            ('defence_region','DefTab',4),
            ('health_region','Health',4),
            ('abs_def_region','AbsDef',4),
            ('claim_region','Claim',4),
            ('wave_region','Wave',4),
            ('float_gem_coord','FloatGem',2),
            ('def_tab_tap_coord','DefTap',2),
        ]
        self.coord_vars: dict[str, list[tk.StringVar]] = {}
        for i,(attr,label,dim) in enumerate(regions):
            ttk.Label(cf, text=label).grid(row=i, column=0, sticky='w', **pad)
            vs = []
            vals = getattr(self.cfg, attr)
            for j in range(dim):
                v = tk.StringVar(value=str(vals[j]))
                e = ttk.Entry(cf, textvariable=v, width=6)
                e.grid(row=i, column=j+1, **pad)
                vs.append(v)
            self.coord_vars[attr] = vs
            b = ttk.Button(cf, text="Capture",
                           command=lambda a=attr: self._start_region_capture(a))
            b.grid(row=i, column=dim+1, **pad)
        ttk.Button(cf, text="Update", command=self._update_coords).grid(
            row=len(regions), column=0, columnspan=dim+2, pady=10
        )

        # Tab 3: Setup
        t3 = ttk.Frame(nb); nb.add(t3, text="Setup")
        sf = ttk.Frame(t3); sf.pack(padx=10, pady=10, fill='both', expand=True)
        ttk.Label(sf, text="Region Capture").grid(row=0, column=0, columnspan=2, pady=(0,10))
        btns = [
            ("Capture Claim Region",       "claim_region"),
            ("Capture New Perk Region",    "new_perk_region"),
            ("Capture Defence Tab Region", "defence_region"),
        ]
        for i,(lbl,attr) in enumerate(btns, start=1):
            b = ttk.Button(sf, text=lbl, command=lambda a=attr: self._start_region_capture(a))
            b.grid(row=i, column=0, sticky='w', **pad)
            lblv = ttk.Label(sf, text=str(getattr(self.cfg, attr)))
            lblv.grid(row=i, column=1, sticky='w', **pad)
            self._setup_labels[attr] = lblv
        ttk.Button(sf, text="Save Regions", command=self._update_coords).grid(
            row=len(btns)+1, column=0, columnspan=2, pady=(20,0)
        )

    def _move_up(self):
        sel = self.lb.curselection()
        if sel and sel[0] > 0:
            i = sel[0]; v = self.lb.get(i)
            self.lb.delete(i); self.lb.insert(i-1, v); self.lb.select_set(i-1)

    def _move_down(self):
        sel = self.lb.curselection()
        if sel and sel[0] < self.lb.size()-1:
            i = sel[0]; v = self.lb.get(i)
            self.lb.delete(i); self.lb.insert(i+1, v); self.lb.select_set(i+1)

    def _update_coords(self):
        data = {}
        for attr, vs in self.coord_vars.items():
            vals = tuple(int(v.get()) for v in vs)
            setattr(self.cfg, attr, vals)
            data[attr] = list(vals)
            if attr in self._setup_labels:
                self._setup_labels[attr].config(text=str(vals))
        with open(REGION_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        messagebox.showinfo("Saved", "regions.json updated")

    def _update_wave_label(self):
        self.wave_lbl.config(text=f"Wave: {self.cfg.wave_number}")
        self.after(500, self._update_wave_label)

    def _toggle(self):
        if not self.cfg.running:
            self.bot.start()
            self.cfg.running = True
            self.btn.config(text="Stop")
        else:
            self.bot.stop()
            self.cfg.running = False
            self.btn.config(text="Start")

    def _on_close(self):
        if self.cfg.running and not messagebox.askyesno("Quit", "Bot running. Quit anyway?"):
            return
        self.bot.stop()
        self.destroy()

    def _start_region_capture(self, attr: str):
        self._capture_attr = attr
        self._capture_coords.clear()
        try:
            ensure_app_running()
            img_full = mac_screencap()
        except Exception as e:
            messagebox.showerror("ADB Error", f"{e}")
            return

        if self.cfg.debug_enabled:
            print(f"[DEBUG] Screenshot size: {img_full.size}")

        ow, oh = img_full.size
        mw = self.winfo_screenwidth() - 200
        mh = self.winfo_screenheight() - 200
        scale = min(mw/ow, mh/oh, 1.0)
        dw, dh = int(ow*scale), int(oh*scale)
        img_disp = img_full.resize((dw, dh), Image.LANCZOS)

        self._capture_img_full = img_full
        self._capture_scale = scale

        self._cap_win = tk.Toplevel(self)
        self._cap_win.title(f"Capture: {attr}")
        canvas = tk.Canvas(self._cap_win, width=dw, height=dh)
        canvas.pack()
        photo = ImageTk.PhotoImage(img_disp)
        canvas.create_image(0,0, anchor="nw", image=photo)
        canvas.image = photo
        canvas.bind("<Button-1>", self._on_capture_click)
        ttk.Label(self._cap_win, text="Click two opposite corners").pack(pady=5)

    def _on_capture_click(self, event):
        x_full = int(event.x / self._capture_scale)
        y_full = int(event.y / self._capture_scale)
        self._capture_coords.append((x_full, y_full))
        canvas = event.widget
        if len(self._capture_coords) == 1:
            canvas.create_oval(event.x-3, event.y-3, event.x+3, event.y+3, fill="red")
            return

        (x0,y0),(x1,y1) = self._capture_coords
        x0, x1 = sorted((x0,x1)); y0, y1 = sorted((y0,y1))
        canvas.create_rectangle(
            int(x0/self._capture_scale), int(y0/self._capture_scale),
            int(x1/self._capture_scale), int(y1/self._capture_scale),
            outline="red"
        )

        curr = getattr(self.cfg, self._capture_attr)
        dim = len(curr)

        if dim == 4:
            region = (x0, y0, x1-x0, y1-y0)
            tpl_dir = Path(__file__).parent / "templates"
            tpl_dir.mkdir(exist_ok=True)
            out = tpl_dir / f"{self._capture_attr}.png"
            self._capture_img_full.crop((x0,y0,x1,y1)).save(out)
            self._dbg(f"Saved template: {out}")
        else:
            region = (x0, y0)

        setattr(self.cfg, self._capture_attr, region)
        if self._capture_attr in self._setup_labels:
            self._setup_labels[self._capture_attr].config(text=str(region))
        for idx, v in enumerate(self.coord_vars[self._capture_attr]):
            v.set(str(region[idx]))

        self._cap_win.destroy()
        self._capture_attr = None
        self._capture_coords.clear()

    def _dbg(self, *msgs):
        if self.cfg.debug_enabled:
            print("[DEBUG]", *msgs)


if __name__ == "__main__":
    cfg = BotConfig()
    load_regions(cfg)
    app = TowerBotGUI(cfg)
    app.mainloop()
