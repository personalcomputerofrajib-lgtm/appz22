import os
import sys
import tempfile
import shutil
from pathlib import Path

from kivy.lang import Builder
from kivy.utils import platform
from kivymd.app import MDApp
from kivymd.uix.filemanager import MDFileManager
from kivymd.toast import toast
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDFlatButton

if platform == "android":
    from jnius import autoclass, cast
    from android import activity
    from android.permissions import request_permissions, Permission
    
    Intent = autoclass('android.content.Intent')
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    Uri = autoclass('android.net.Uri')
    ContentResolver = autoclass('android.content.ContentResolver')
    OpenableColumns = autoclass('android.provider.OpenableColumns')
    # Native PDF Rendering imports
    PdfRenderer = autoclass('android.graphics.pdf.PdfRenderer')
    ParcelFileDescriptor = autoclass('android.os.ParcelFileDescriptor')
    Bitmap = autoclass('android.graphics.Bitmap')
    File = autoclass('java.io.File')
    FileOutputStream = autoclass('java.io.FileOutputStream')

# --- Compression Logic ---

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

def android_render_pdf_to_images(src, tmp_dir):
    """
    Uses Android Native PdfRenderer to convert PDF pages to high-quality JPEGs.
    This captures text and layout perfectly, unlike simple image extraction.
    """
    image_paths = []
    try:
        source_file = File(src)
        fd = ParcelFileDescriptor.open(source_file, ParcelFileDescriptor.MODE_READ_ONLY)
        renderer = PdfRenderer(fd)
        
        page_count = renderer.getPageCount()
        for i in range(page_count):
            page = renderer.openPage(i)
            
            # Rendering at 2x or 3x scale for "Print Quality"
            # Standard PDF point is 1/72 inch. We want at least 200-300 DPI.
            # 72 * 3 = 216 DPI (Good balance)
            scale = 3
            w, h = int(page.getWidth() * scale), int(page.getHeight() * scale)
            
            # Create Bitmap
            bitmap = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
            
            # Render page to bitmap (RENDER_MODE_FOR_DISPLAY = 1)
            page.render(bitmap, None, None, 1)
            
            # Save bitmap to file
            img_path = os.path.join(tmp_dir, f"p_{i:04d}.jpg")
            os_stream = FileOutputStream(img_path)
            # Use high quality initially, compression happens in final step
            bitmap.compress(Bitmap.CompressFormat.JPEG, 90, os_stream)
            os_stream.close()
            
            # Cleanup native resources immediately to prevent OOM
            bitmap.recycle()
            page.close()
            image_paths.append(img_path)
            
        renderer.close()
        fd.close()
    except Exception as e:
        print(f"Android PDF Rendering failed: {e}")
        return []
    return image_paths

def compress_pdf(src, dst, target_kb):
    import pypdf
    import img2pdf
    from PIL import Image

    # A4 dimensions in points (72 DPI)
    A4 = (595.27, 841.89)
    target_b = target_kb * 1024
    
    # Pass 1: Simple Re-save / Metadata Optimization
    writer = pypdf.PdfWriter()
    try:
        reader = pypdf.PdfReader(src)
        for page in reader.pages:
            writer.add_page(page)
        writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
        with open(dst, "wb") as f:
            writer.write(f)
        
        if os.path.getsize(dst) <= target_b:
            return True
    except:
        pass

    # Pass 2: Rasterize pages (The "Double Print" Fix)
    # This fixes cut edges, wrong sizes, and alignment by redrawing everything.
    a4_w_pt, a4_h_pt = A4
    layout = img2pdf.get_layout_fun((a4_w_pt, a4_h_pt), fit=img2pdf.FitMode.into)

    with tempfile.TemporaryDirectory() as tmp_dir:
        jpg_paths = []
        if platform == "android":
            # Use Native Print Engine
            jpg_paths = android_render_pdf_to_images(src, tmp_dir)
        
        # Fallback for non-android or if native failed
        if not jpg_paths:
            reader = pypdf.PdfReader(src)
            for i, page in enumerate(reader.pages):
                jp = os.path.join(tmp_dir, f"page_{i:04d}.jpg")
                imgs = list(page.images)
                if imgs:
                    pil_img = Image.open(imgs[0].data)
                else:
                    pil_img = Image.new("RGB", (int(a4_w_pt), int(a4_h_pt)), "white")
                
                pil_img.convert("RGB").save(jp, "JPEG", quality=75, optimize=True)
                jpg_paths.append(jp)
        
        if not jpg_paths: return False
        
        # Final "Print to PDF" with Fit-to-A4 logic
        with open(dst, "wb") as f:
            f.write(img2pdf.convert(jpg_paths, layout_fun=layout))
        
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
        self.temp_dir = tempfile.mkdtemp()
        
        if platform == "android":
            activity.bind(on_activity_result=self.on_activity_result)
        else:
            self.file_manager = MDFileManager(
                exit_manager=self.exit_manager,
                select_path=self.select_path,
            )
        return Builder.load_string(KV)

    def open_file_manager(self):
        if platform == "android":
            intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            intent.setType("*/*")
            # Filter for images and PDFs
            mimeTypes = ["image/*", "application/pdf"]
            intent.putExtra(Intent.EXTRA_MIME_TYPES, mimeTypes)
            PythonActivity.mActivity.startActivityForResult(intent, 42)
        else:
            path = os.path.expanduser("~")
            self.file_manager.show(path)

    def on_activity_result(self, request_code, result_code, intent):
        if request_code == 42:
            if result_code == -1: # RESULT_OK
                uri = intent.getData()
                self.handle_android_uri(uri)
            else:
                toast("File selection cancelled")

    def handle_android_uri(self, uri):
        try:
            context = PythonActivity.mActivity
            content_resolver = context.getContentResolver()
            
            # Get display name
            name = "selected_file"
            cursor = content_resolver.query(uri, None, None, None, None)
            if cursor and cursor.moveToFirst():
                name_index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                name = cursor.getString(name_index)
                cursor.close()
            
            # Copy to temp file
            input_stream = content_resolver.openInputStream(uri)
            temp_path = os.path.join(self.temp_dir, name)
            
            # Read in chunks to avoid memory issues with large files
            with open(temp_path, "wb") as f:
                buffer = autoclass('java.lang.reflect.Array').newInstance(autoclass('java.lang.Byte').TYPE, 1024*64)
                while True:
                    read = input_stream.read(buffer)
                    if read == -1:
                        break
                    # Convert java byte array to python bytes (inefficient but safe for small/med files)
                    # Actually, Pyjnius handles byte arrays fairly well lately, but let's be careful.
                    # A better way is to use a java-based copy if possible, or just:
                    f.write(bytes(buffer)[:read])
            
            self.select_path(temp_path)
            toast(f"Selected: {name}")
        except Exception as e:
            self.show_error_dialog(f"Failed to load file: {str(e)}")

    def select_path(self, path):
        self.selected_path = path
        self.root.ids.file_label.text = os.path.basename(path)
        if platform != "android":
            self.exit_manager()

    def exit_manager(self, *args):
        if platform != "android":
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
        
        if platform == "android":
            from android.storage import primary_external_storage_path
            # On Android 11+, writing to Download might require specific handling,
            # but usually the app's Download subfolder works or we use MANAGE_EXTERNAL_STORAGE.
            downloads = os.path.join(primary_external_storage_path(), "Download")
        else:
            downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        
        if not os.path.exists(downloads):
            try:
                os.makedirs(downloads)
            except:
                # Fallback to internal storage if Download is restricted
                downloads = self.user_data_dir
        
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
                self.show_success_dialog(dst)

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

    def on_stop(self):
        # Cleanup temp files
        shutil.rmtree(self.temp_dir, ignore_errors=True)

if __name__ == "__main__":
    if platform == "android":
        # Request necessary permissions for older android and general storage access
        request_permissions([
            Permission.READ_EXTERNAL_STORAGE, 
            Permission.WRITE_EXTERNAL_STORAGE,
            Permission.MANAGE_EXTERNAL_STORAGE
        ])
    
    SwiftCompressor().run()
