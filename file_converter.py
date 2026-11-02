import os
import sys
import math
import time
import shutil
import ctypes
import queue
import threading
import subprocess
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont
from tkinterdnd2 import TkinterDnD, DND_FILES
from PIL import Image
from pypdf import PdfReader, PdfWriter

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".heic", ".tiff"}
OFFICE_EXT = {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"}
PDF_EXT = {".pdf"}
BG_COLOR = "#f8f9fa"
BOX_COLOR = "#ffffff"
PRIMARY_COLOR = "#3b82f6"
PRIMARY_HOVER = "#2563eb"
BORDER_COLOR = "#cbd5e1"


def now_str() -> str:
    t = time.time()
    return f"{time.strftime('%H:%M:%S', time.localtime(t))}.{int(t * 1000) % 1000:03d}"


def find_soffice() -> str | None:
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return found
    candidates = []
    if sys.platform == "darwin":
        candidates = ["/Applications/LibreOffice.app/Contents/MacOS/soffice"]
    elif sys.platform == "win32":
        candidates = [
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None

FONT_CANDIDATES = {
    "darwin": ["Thonburi", "Helvetica Neue", "Helvetica"],
    "win32": ["Leelawadee UI", "Segoe UI", "Tahoma"],
}


def pick_font(root) -> str:
    available = set(tkfont.families(root))
    for name in FONT_CANDIDATES.get(sys.platform, ["Arial"]):
        if name in available:
            return name
    return "TkDefaultFont"

def menu_items_for(paths: list[str]) -> list[str]:
    exts = {os.path.splitext(p)[1].lower() for p in paths}
    if len(paths) > 1 and exts <= PDF_EXT:
        return ["PDF (merge)"]
    if exts <= IMAGE_EXT:
        return ["JPG", "PNG", "WEBP", "PDF"]
    if exts <= OFFICE_EXT:
        return ["PDF"]
    return []


def unique_path(path: str) -> str:
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(f"{base} ({n}){ext}"):
        n += 1
    return f"{base} ({n}){ext}"


def convert(paths: list[str], target: str) -> str:
    if target == "PDF (merge)":
        writer = PdfWriter()
        for p in paths:
            for page in PdfReader(p).pages:
                writer.add_page(page)
        out = unique_path(os.path.join(os.path.dirname(paths[0]), "merged.pdf"))
        with open(out, "wb") as f:
            writer.write(f)
        return out

    src = paths[0]
    base = os.path.splitext(src)[0]
    ext = os.path.splitext(src)[1].lower()

    if target in ("JPG", "PNG", "WEBP"):
        out = unique_path(f"{base}.{target.lower()}")
        with Image.open(src) as im:
            if target == "JPG":
                im = im.convert("RGB")
            im.save(out, "JPEG" if target == "JPG" else target, quality=95)
        return out

    if target == "PDF" and ext in IMAGE_EXT:
        out = unique_path(f"{base}.pdf")
        with Image.open(src) as im:
            im.convert("RGB").save(out, "PDF", resolution=100.0)
        return out

    if target == "PDF" and ext in OFFICE_EXT:
        soffice = find_soffice()
        if not soffice:
            raise RuntimeError("ไม่พบ LibreOffice กรุณาติดตั้งก่อน")
        
        default_out = f"{base}.pdf"
        target_out = unique_path(default_out)

        subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf",
             "--outdir", os.path.dirname(src), src],
            check=True, capture_output=True,
        )

        if target_out != default_out and os.path.exists(default_out):
            shutil.move(default_out, target_out)

        return target_out

    raise ValueError(f"ไม่รองรับการแปลง {ext} -> {target}")

class RadialMenu:
    RADIUS = 115
    INNER = 38

    def __init__(self, canvas, cx, cy, items, on_pick, font_name, on_close):
        self.canvas = canvas
        self.cx, self.cy = cx, cy
        self.items = items
        self.on_pick = on_pick
        self.font_name = font_name
        self.on_close = on_close
        self.step = 360 / len(items)
        self.hovered_idx = None
        self._draw()

        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Button-1>", self._click)

    def _get_choice_index(self, x, y):
        dx = x - self.cx
        dy = self.cy - y
        dist = math.hypot(dx, dy)
        if self.INNER <= dist <= self.RADIUS:
            ang = math.degrees(math.atan2(dy, dx)) % 360
            return int(((ang - (90 - self.step / 2)) % 360) // self.step)
        return None

    def _draw(self):
        self.canvas.delete("radial")
        r = self.RADIUS

        if len(self.items) == 1:
            color = PRIMARY_HOVER if self.hovered_idx == 0 else PRIMARY_COLOR
            self.canvas.create_oval(
                self.cx - r, self.cy - r, self.cx + r, self.cy + r,
                fill=color, outline="white", width=2, tags="radial"
            )
        else:
            for i in range(len(self.items)):
                color = PRIMARY_HOVER if self.hovered_idx == i else PRIMARY_COLOR
                start = 90 + i * self.step - self.step / 2
                pts = [self.cx, self.cy]
                for k in range(25):
                    a = math.radians(start + self.step * k / 24)
                    pts += [self.cx + r * math.cos(a), self.cy - r * math.sin(a)]
                self.canvas.create_polygon(*pts, fill=color, outline="white", width=2, tags="radial")

        for i, label in enumerate(self.items):
            center = 90 + i * self.step
            rad = math.radians(center)
            mid = (r + self.INNER) / 2
            tx = self.cx + mid * math.cos(rad)
            ty = self.cy - mid * math.sin(rad)
            self.canvas.create_text(tx, ty, text=label, fill="white",
                                    font=(self.font_name, 10, "bold"), tags="radial")

        self.canvas.create_oval(
            self.cx - self.INNER, self.cy - self.INNER,
            self.cx + self.INNER, self.cy + self.INNER,
            fill="#ffffff", outline="#e2e8f0", width=2, tags="radial"
        )
        self.canvas.create_text(self.cx, self.cy, text="✕", fill="#94a3b8",
                                font=(self.font_name, 12, "bold"), tags="radial")

    def _on_motion(self, event):
        idx = self._get_choice_index(event.x, event.y)
        if idx != self.hovered_idx:
            self.hovered_idx = idx
            self._draw()

    def _click(self, event):
        idx = self._get_choice_index(event.x, event.y)
        choice = self.items[idx] if idx is not None else None
        self.close()
        if choice is not None:
            self.on_pick(choice)

    def close(self):
        self.canvas.unbind("<Motion>")
        self.canvas.unbind("<Button-1>")
        self.canvas.delete("radial")
        self.on_close()

class FileeApp:
    def __init__(self):
        self.root = TkinterDnD.Tk()
        self.root.title("Filee Converter")
        self.root.geometry("540x540")
        self.root.minsize(480, 480)
        self.root.configure(bg=BG_COLOR)
        self.font_name = pick_font(self.root)
        self.latest_out_path = ""

        self.bg_canvas = tk.Canvas(self.root, bg=BG_COLOR, highlightthickness=0)
        self.bg_canvas.pack(fill="both", expand=True, padx=25, pady=25)
        self.bg_canvas.bind("<Configure>", self.draw_drop_zone)

        self.overlay = tk.Canvas(self.root, bg=BG_COLOR, highlightthickness=0)
        self.menu = None

        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind("<<Drop>>", self.on_drop)
        self.root.bind("<Escape>", lambda e: self.close_menu())

        self.results = queue.Queue()
        self.root.after(100, self.poll_results)

    def draw_drop_zone(self, event=None):
        w = self.bg_canvas.winfo_width()
        h = self.bg_canvas.winfo_height()
        if w < 50 or h < 50:
            return

        self.bg_canvas.delete("all")
        pad = 12

        self.bg_canvas.create_rectangle(
            pad, pad, w - pad, h - pad,
            fill=BOX_COLOR, outline=BORDER_COLOR,
            width=2, dash=(6, 6)
        )

        cx, cy = w / 2, h / 2 - 40
        snout_y = cy - 25

        self.bg_canvas.create_text(
            cx, cy - 30, text="🐽",
            font=(self.font_name, 48), fill="#38bdf8"
        )

        # 3. ข้อความแนะนำ (คมชัด ไม่แตก)
        self.bg_canvas.create_text(
            cx, cy + 35, text="ลากและวางไฟล์ที่นี่",
            font=(self.font_name, 13, "bold"), fill="#1e293b"
        )
        self.bg_canvas.create_text(
            cx, cy + 60, text="รองรับ Word, Excel, PowerPoint, รูปภาพ, PDF",
            font=(self.font_name, 9), fill="#64748b"
        )

        # 4. กล่องแสดงผลสถานะ ปุ่ม และ Progress Bar
        if not hasattr(self, 'ui_container') or not self.ui_container.winfo_exists():
            self.ui_container = tk.Frame(self.bg_canvas, bg=BOX_COLOR)
            self.status_var = tk.StringVar(value="")
            self.lbl_status = tk.Label(self.ui_container, textvariable=self.status_var,
                                       bg=BOX_COLOR, fg="#0f172a", font=(self.font_name, 10),
                                       wraplength=380, justify="center")
            self.lbl_status.pack(pady=4)

            self.progress = ttk.Progressbar(self.ui_container, mode="indeterminate", length=220)

            self.action_box = tk.Frame(self.ui_container, bg=BOX_COLOR)
            self.btn_open = tk.Button(self.action_box, text="📁 เปิดโฟลเดอร์", font=(self.font_name, 9),
                                      bg="#e2e8f0", relief="flat", padx=8, pady=4, cursor="hand2",
                                      command=self.open_output_folder)
            self.btn_copy = tk.Button(self.action_box, text="📋 คัดลอก Path", font=(self.font_name, 9),
                                      bg="#e2e8f0", relief="flat", padx=8, pady=4, cursor="hand2",
                                      command=self.copy_output_path)
            self.btn_open.pack(side="left", padx=5)
            self.btn_copy.pack(side="left", padx=5)

        self.bg_canvas.create_window(w / 2, h / 2 + 120, window=self.ui_container)

    def open_output_folder(self):
        if self.latest_out_path and os.path.exists(self.latest_out_path):
            full_path = os.path.abspath(self.latest_out_path)
            if sys.platform == "win32":
                subprocess.run(f'explorer /select,"{full_path}"')
            elif sys.platform == "darwin":
                subprocess.run(["open", "-R", full_path])

    def copy_output_path(self):
        if self.latest_out_path:
            full_path = os.path.abspath(self.latest_out_path)
            self.root.clipboard_clear()
            self.root.clipboard_append(full_path)
            self.status_var.set(f"คัดลอก Path ลงคลิปบอร์ดแล้ว!\n{os.path.basename(full_path)}")

    def on_drop(self, event):
        paths = list(self.root.tk.splitlist(event.data))
        x = self.root.winfo_pointerx() - self.root.winfo_rootx()
        y = self.root.winfo_pointery() - self.root.winfo_rooty()
        self.root.after(20, lambda: self.show_menu(paths, x, y))

    def show_menu(self, paths, x, y):
        items = menu_items_for(paths)
        if not items:
            self.action_box.pack_forget()
            self.status_var.set("❌ ไม่รองรับชนิดไฟล์นี้")
            return

        self.close_menu()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        r = RadialMenu.RADIUS
        cx = max(r, min(x, w - r))
        cy = max(r, min(y, h - r))

        self.overlay.place(x=0, y=0, relwidth=1, relheight=1)
        self.menu = RadialMenu(self.overlay, cx, cy, items,
                               lambda target: self.run(paths, target),
                               self.font_name, on_close=self.hide_overlay)
        self.root.update_idletasks()

    def hide_overlay(self):
        self.overlay.place_forget()
        self.menu = None

    def close_menu(self):
        if self.menu:
            self.menu.close()

    def run(self, paths, target):
        self.action_box.pack_forget()
        self.status_var.set(f"กำลังแปลงเป็น {target} ... กรุณารอสักครู่")
        self.progress.pack(pady=6)
        self.progress.start(10)
        threading.Thread(target=self._worker, args=(paths, target), daemon=True).start()

    def _worker(self, paths, target):
        try:
            out = convert(paths, target)
            self.results.put(("ok", out))
        except Exception as e:
            self.results.put(("error", f"แปลงไม่สำเร็จ: {e}"))

    def poll_results(self):
        try:
            while True:
                status, val = self.results.get_nowait()
                self.progress.stop()
                self.progress.pack_forget()

                if status == "ok":
                    self.latest_out_path = val
                    self.status_var.set(f"✅ แปลงเสร็จเรียบร้อย:\n{os.path.basename(val)}")
                    self.action_box.pack(pady=10)
                else:
                    self.action_box.pack_forget()
                    self.status_var.set(f"⚠️ {val}")
        except queue.Empty:
            pass
        self.root.after(100, self.poll_results)

    def start(self):
        self.root.mainloop()


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()

    FileeApp().start()