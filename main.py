import os
import sys
import tempfile
from pathlib import Path

from kivy.lang import Builder
from kivy.utils import platform
from kivymd.app import MDApp
from kivymd.uix.filemanager import MDFileManager
from kivymd.toast import toast
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDFlatButton

# --- Compression Logic (Adapted from compress_to_250kb.py) ---

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}
PDF_EXTS = {".pdf"}

def size_kb(path):
    return os.path.getsize(path) / 1024

def compress_image(src, dst, ext, target_kb):
    from PIL import Image
    fmt_map = {"jpg":"JPEG","jpeg":"JPEG","png":"PNG",
               "webp":"WEBP","bmp":"BMP","tiff":"TIFF","tif":"TIFF"}
    pil_fmt = fmt_map.get(ext.lower().lstrip("."), "JPEG")

    target_b = target_kb * 1024
    with Image.open(src) as im:
        orig_w, orig_h = im.size

    quality, scale = 85, 1.0
    for attempt in range(20):
        with Image.open(src) as im:
            if im.mode not in ("RGB","RGBA","L"):
                im = im.convert("RGB")
            if scale < 1.0:
                im = im.resize((max(1,int(orig_w*scale)),
                                max(1,int(orig_h*scale))), Image.LANCZOS)
            kw = {}
            if pil_fmt in ("JPEG","WEBP"):
                kw = {"quality": quality, "optimize": True}
            elif pil_fmt == "PNG":
                kw = {"optimize": True, "compress_level": 9}
            im.save(dst, pil_fmt, **kw)

        if os.path.getsize(dst) <= target_b:
            return True
        if quality > 20 and pil_fmt in ("JPEG","WEBP"):
            quality = max(20, quality - 10)
        else:
            scale = max(0.10, scale - 0.15)
    return os.path.getsize(dst) <= target_b

def compress_pdf(src, dst, target_kb):
    import pypdf
    import img2pdf
    from PIL import Image

    # A4 dimensions in points (72 DPI)
    A4 = (595.27, 841.89)

    target_b = target_kb * 1024
    
    # Pass 1: Simple Re-save
    writer = pypdf.PdfWriter()
    reader = pypdf.PdfReader(src)
    for page in reader.pages:
        writer.add_page(page)
    try:
        writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    except:
        pass
    with open(dst, "wb") as f:
        writer.write(f)
    
    if os.path.getsize(dst) <= target_b:
        return True

    # Pass 2: Rasterize pages (Double-print approach)
    a4_w_pt, a4_h_pt = A4
    layout = img2pdf.get_layout_fun((a4_w_pt, a4_h_pt), fit=img2pdf.FitMode.into)

    for dpi in (120, 96, 72, 60, 48):
        with tempfile.TemporaryDirectory() as tmp_dir:
            jpg_paths = []
            reader = pypdf.PdfReader(src)
            for i, page in enumerate(reader.pages):
                jp = os.path.join(tmp_dir, f"page_{i:04d}.jpg")
                # Simple extraction/rendering fallback for Android compatibility
                imgs = list(page.images)
                if imgs:
                    pil_img = Image.open(imgs[0].data)
                else:
                    pil_img = Image.new("RGB", (595, 842), "white")
                
                pil_img.convert("RGB").save(jp, "JPEG", quality=70, optimize=True)
                jpg_paths.append(jp)
            
            if not jpg_paths: continue
            
            with open(dst, "wb") as f:
                f.write(img2pdf.convert(jpg_paths, layout_fun=layout))
        
        if os.path.getsize(dst) <= target_b:
            return True
    return os.path.getsize(dst) <= target_b

# --- UI Layout ---

KV = '''
MDBoxLayout:
    orientation: 'vertical'
    spacing: dp(10)
    padding: dp(20)

    MDTopAppBar:
        title: "Swift Compressor"
        elevation: 4
        pos_hint: {"top": 1}

    MDBoxLayout:
        orientation: 'vertical'
        size_hint_y: None
        height: self.minimum_height
        spacing: dp(20)
        padding: [0, dp(40), 0, 0]

        MDIconButton:
            icon: "file-upload"
            icon_size: "64sp"
            pos_hint: {"center_x": .5}
            on_release: app.open_file_manager()

        MDLabel:
            id: file_label
            text: "No file selected"
            halign: "center"
            theme_text_color: "Secondary"

        MDBoxLayout:
            orientation: 'horizontal'
            size_hint_y: None
            height: dp(50)
            spacing: dp(10)
            padding: [dp(20), 0]

            MDLabel:
                text: "Target Size (KB):"
                size_hint_x: None
                width: dp(120)

            MDSlider:
                id: size_slider
                min: 50
                max: 2000
                value: 250
                step: 50
                on_value: app.update_slider_label(self.value)

            MDLabel:
                id: slider_val
                text: "250 KB"
                size_hint_x: None
                width: dp(60)

    Widget:

    MDFillRoundFlatButton:
        text: "COMPRESS & SAVE"
        font_style: "H6"
        size_hint_x: .8
        pos_hint: {"center_x": .5}
        on_release: app.start_compression()
        padding: dp(20)
'''

class SwiftCompressor(MDApp):
    def build(self):
        self.theme_cls.primary_palette = "DeepPurple"
        self.theme_cls.theme_style = "Dark"
        self.selected_path = None
        self.file_manager = MDFileManager(
            exit_manager=self.exit_manager,
            select_path=self.select_path,
        )
        return Builder.load_string(KV)

    def open_file_manager(self):
        # On Android, start from primary storage
        path = "/"
        if platform == "android":
            from android.storage import primary_external_storage_path
            path = primary_external_storage_path()
        else:
            path = os.path.expanduser("~")
        
        self.file_manager.show(path)

    def select_path(self, path):
        self.selected_path = path
        self.root.ids.file_label.text = os.path.basename(path)
        self.exit_manager()

    def exit_manager(self, *args):
        self.file_manager.close()

    def update_slider_label(self, value):
        self.root.ids.slider_val.text = f"{int(value)} KB"

    def start_compression(self):
        if not self.selected_path:
            toast("Please select a file first")
            return

        target_kb = int(self.root.ids.size_slider.value)
        src = self.selected_path
        ext = Path(src).suffix.lower()
        
        # Determine output path (Downloads folder)
        if platform == "android":
            from android.storage import primary_external_storage_path
            downloads = os.path.join(primary_external_storage_path(), "Download")
        else:
            downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        
        if not os.path.exists(downloads):
            os.makedirs(downloads)

        dst_name = f"{Path(src).stem}_compressed_{target_kb}kb{ext}"
        dst = os.path.join(downloads, dst_name)

        try:
            success = False
            if ext in IMAGE_EXTS:
                success = compress_image(src, dst, ext, target_kb)
            elif ext in PDF_EXTS:
                success = compress_pdf(src, dst, target_kb)
            else:
                toast(f"Unsupported format: {ext}")
                return

            if success:
                self.show_success_dialog(dst)
            else:
                toast("Compression finished, but was unable to reach target size exactly.")
                self.show_success_dialog(dst) # Still show result

        except Exception as e:
            self.show_error_dialog(str(e))

    def show_success_dialog(self, path):
        kb = size_kb(path)
        self.dialog = MDDialog(
            title="Success!",
            text=f"File compressed to {kb:.1f} KB\nSaved to: {path}",
            buttons=[
                MDFlatButton(text="OK", on_release=lambda x: self.dialog.dismiss())
            ],
        )
        self.dialog.open()

    def show_error_dialog(self, error):
        self.dialog = MDDialog(
            title="Error",
            text=f"An error occurred: {error}",
            buttons=[
                MDFlatButton(text="OK", on_release=lambda x: self.dialog.dismiss())
            ],
        )
        self.dialog.open()

if __name__ == "__main__":
    # Handle Android permissions
    if platform == "android":
        from android.permissions import request_permissions, Permission
        request_permissions([Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE])
    
    SwiftCompressor().run()
