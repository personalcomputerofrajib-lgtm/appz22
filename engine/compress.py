"""
compress.py — Image & PDF compression engine.

All functions accept an on_progress callback for UI updates.
Designed to run on a background thread via BackgroundTask.
"""

import os
import tempfile
from pathlib import Path
from kivy.utils import platform
from kivy.logger import Logger


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}
PDF_EXTS = {".pdf"}
ALL_SUPPORTED = IMAGE_EXTS | PDF_EXTS


def compress_image(src, dst, target_kb, on_progress=None):
    """
    Compress an image to target file size using iterative quality + scale reduction.
    
    Args:
        src: source image path
        dst: destination path
        target_kb: target size in KB
        on_progress: callable(percent, message)
        
    Returns:
        True if target size achieved, False otherwise.
    """
    from PIL import Image

    ext = Path(dst).suffix.lower().lstrip(".")
    fmt_map = {
        "jpg": "JPEG", "jpeg": "JPEG", "png": "PNG",
        "webp": "WEBP", "bmp": "BMP", "tiff": "TIFF", "tif": "TIFF"
    }
    pil_fmt = fmt_map.get(ext, "JPEG")
    target_b = target_kb * 1024

    with Image.open(src) as im:
        orig_w, orig_h = im.size
    
    if on_progress:
        on_progress(5, "Analyzing image...")

    quality = 90
    scale = 1.0
    total_attempts = 20

    for attempt in range(total_attempts):
        percent = 10 + int((attempt / total_attempts) * 80)
        if on_progress:
            on_progress(percent, f"Optimizing... (q={quality}, s={scale:.0%})")

        with Image.open(src) as im:
            if im.mode not in ("RGB", "RGBA", "L"):
                im = im.convert("RGB")
            if pil_fmt == "JPEG" and im.mode == "RGBA":
                im = im.convert("RGB")
            if scale < 1.0:
                new_w = max(1, int(orig_w * scale))
                new_h = max(1, int(orig_h * scale))
                im = im.resize((new_w, new_h), Image.LANCZOS)

            save_kwargs = {"optimize": True}
            if pil_fmt in ("JPEG", "WEBP"):
                save_kwargs["quality"] = quality
            elif pil_fmt == "PNG":
                save_kwargs["compress_level"] = 9
            
            im.save(dst, pil_fmt, **save_kwargs)

        current_size = os.path.getsize(dst)
        if current_size <= target_b:
            if on_progress:
                on_progress(100, "Compression complete!")
            return True

        # Reduce quality first, then scale
        if quality > 20 and pil_fmt in ("JPEG", "WEBP"):
            quality = max(20, quality - 8)
        elif scale > 0.1:
            scale = max(0.1, scale - 0.1)
        else:
            break

    if on_progress:
        on_progress(100, "Best compression achieved")
    return os.path.getsize(dst) <= target_b


def compress_pdf(src, dst, target_kb, on_progress=None):
    """
    Compress a PDF to target file size.
    
    Strategy:
      1. Lossless: pypdf compression + dedup
      2. Lossy: Rasterize pages → recompose as image-PDF
      
    Args:
        src: source PDF path
        dst: destination path
        target_kb: target size in KB
        on_progress: callable(percent, message)
        
    Returns:
        True if target size achieved.
    """
    import pypdf
    import img2pdf

    A4 = (595.27, 841.89)
    target_b = target_kb * 1024

    if on_progress:
        on_progress(10, "Trying lossless optimization...")

    # Pass 1: Lossless
    try:
        writer = pypdf.PdfWriter()
        reader = pypdf.PdfReader(src)
        for page in reader.pages:
            writer.add_page(page)

        try:
            writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
        except TypeError:
            try:
                writer.compress_identical_objects(True, True)
            except Exception:
                pass

        with open(dst, "wb") as f:
            writer.write(f)

        if os.path.getsize(dst) <= target_b:
            if on_progress:
                on_progress(100, "Lossless compression successful!")
            return True
    except Exception as e:
        Logger.warning(f"Compress: Lossless pass failed: {e}")

    if on_progress:
        on_progress(30, "Rasterizing pages for deeper compression...")

    # Pass 2: Rasterize + recompose
    layout = img2pdf.get_layout_fun(A4, fit=img2pdf.FitMode.into)
    quality_levels = [85, 70, 55, 40]

    for qi, jpeg_quality in enumerate(quality_levels):
        percent = 40 + int((qi / len(quality_levels)) * 50)
        if on_progress:
            on_progress(percent, f"Re-rendering at quality {jpeg_quality}...")

        with tempfile.TemporaryDirectory() as tmp_dir:
            jpg_paths = _render_pdf_pages(src, tmp_dir, jpeg_quality)
            if not jpg_paths:
                if on_progress:
                    on_progress(100, "Could not render PDF pages")
                return False

            with open(dst, "wb") as f:
                f.write(img2pdf.convert(jpg_paths, layout_fun=layout))

            if os.path.getsize(dst) <= target_b:
                if on_progress:
                    on_progress(100, "Compression complete!")
                return True

    if on_progress:
        on_progress(100, "Best compression achieved")
    return os.path.getsize(dst) <= target_b


def _render_pdf_pages(src, tmp_dir, jpeg_quality=75):
    """Render PDF pages to JPEG images using Android PdfRenderer."""
    if platform == "android":
        return _android_render_pdf(src, tmp_dir, jpeg_quality)
    else:
        return _fallback_render_pdf(src, tmp_dir, jpeg_quality)


def _android_render_pdf(src, tmp_dir, jpeg_quality=75):
    """Use Android's native PdfRenderer for high-quality page rendering."""
    from jnius import autoclass
    
    image_paths = []
    try:
        ParcelFileDescriptor = autoclass('android.os.ParcelFileDescriptor')
        File = autoclass('java.io.File')
        PdfRenderer = autoclass('android.graphics.pdf.PdfRenderer')
        Bitmap = autoclass('android.graphics.Bitmap')
        FileOutputStream = autoclass('java.io.FileOutputStream')

        fd = ParcelFileDescriptor.open(File(src), ParcelFileDescriptor.MODE_READ_ONLY)
        renderer = PdfRenderer(fd)

        for i in range(renderer.getPageCount()):
            page = renderer.openPage(i)
            render_scale = 2.0
            w = int(page.getWidth() * render_scale)
            h = int(page.getHeight() * render_scale)

            bitmap = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
            page.render(bitmap, None, None, 1)  # RENDER_MODE_FOR_DISPLAY

            img_path = os.path.join(tmp_dir, f"page_{i:04d}.jpg")
            out_stream = FileOutputStream(img_path)
            bitmap.compress(Bitmap.CompressFormat.JPEG, jpeg_quality, out_stream)
            out_stream.close()
            bitmap.recycle()
            page.close()
            image_paths.append(img_path)

        renderer.close()
        fd.close()
    except Exception as e:
        Logger.error(f"Compress: Android PDF render failed: {e}")

    return image_paths


def _fallback_render_pdf(src, tmp_dir, jpeg_quality=75):
    """Desktop fallback: extract embedded images from PDF pages."""
    import pypdf
    from PIL import Image
    
    paths = []
    try:
        reader = pypdf.PdfReader(src)
        for i, page in enumerate(reader.pages):
            jp = os.path.join(tmp_dir, f"page_{i:04d}.jpg")
            imgs = list(page.images)
            if imgs:
                with Image.open(imgs[0].data) as pil_img:
                    pil_img.convert("RGB").save(jp, "JPEG", quality=jpeg_quality, optimize=True)
            else:
                Image.new("RGB", (595, 842), "white").save(jp, "JPEG", quality=jpeg_quality)
            paths.append(jp)
    except Exception as e:
        Logger.error(f"Compress: Fallback PDF render failed: {e}")

    return paths


def get_file_info(path):
    """Get file type and size info for display."""
    if not path or not os.path.exists(path):
        return None

    ext = Path(path).suffix.lower()
    size = os.path.getsize(path)
    
    if ext in IMAGE_EXTS:
        file_type = "Image"
    elif ext in PDF_EXTS:
        file_type = "PDF"
    else:
        file_type = "File"

    return {
        "path": path,
        "name": os.path.basename(path),
        "ext": ext,
        "type": file_type,
        "size": size,
    }
