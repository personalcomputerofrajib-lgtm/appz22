"""
pdf_tools.py — PDF manipulation: merge, split, extract pages, PDF to images.

Uses pypdf for all operations. Android PdfRenderer for page rendering.
"""

import os
from pathlib import Path
from kivy.utils import platform
from kivy.logger import Logger


def merge_pdfs(pdf_paths, dst, on_progress=None):
    """
    Merge multiple PDFs into one.
    
    Args:
        pdf_paths: list of PDF file paths (in order)
        dst: output PDF path
        on_progress: callable(percent, message)
        
    Returns:
        Output path on success.
    """
    import pypdf

    if on_progress:
        on_progress(5, f"Merging {len(pdf_paths)} PDFs...")

    writer = pypdf.PdfWriter()
    total = len(pdf_paths)

    for i, path in enumerate(pdf_paths):
        percent = 10 + int((i / total) * 80)
        if on_progress:
            on_progress(percent, f"Adding {os.path.basename(path)} ({i+1}/{total})")

        try:
            reader = pypdf.PdfReader(path)
            for page in reader.pages:
                writer.add_page(page)
        except Exception as e:
            Logger.warning(f"PDFTools: Could not read {path}: {e}")
            raise ValueError(f"Could not read {os.path.basename(path)}: {e}")

    if on_progress:
        on_progress(90, "Writing merged PDF...")

    with open(dst, "wb") as f:
        writer.write(f)

    if on_progress:
        on_progress(100, "Merge complete!")
    return dst


def split_pdf(src, start_page, end_page, dst, on_progress=None):
    """
    Extract a range of pages from a PDF.
    
    Args:
        src: source PDF path
        start_page: first page to extract (1-indexed, inclusive)
        end_page: last page to extract (1-indexed, inclusive)
        dst: output PDF path
        on_progress: callable(percent, message)
        
    Returns:
        Output path on success.
    """
    import pypdf

    if on_progress:
        on_progress(10, "Reading PDF...")

    reader = pypdf.PdfReader(src)
    total_pages = len(reader.pages)

    # Validate range
    if start_page < 1:
        start_page = 1
    if end_page > total_pages:
        end_page = total_pages
    if start_page > end_page:
        raise ValueError(f"Invalid range: {start_page}-{end_page}")

    if on_progress:
        on_progress(30, f"Extracting pages {start_page}-{end_page} of {total_pages}...")

    writer = pypdf.PdfWriter()
    pages_to_extract = end_page - start_page + 1

    for i in range(start_page - 1, end_page):
        percent = 30 + int(((i - start_page + 1) / pages_to_extract) * 60)
        if on_progress:
            on_progress(percent, f"Extracting page {i + 1}...")
        writer.add_page(reader.pages[i])

    if on_progress:
        on_progress(95, "Saving...")

    with open(dst, "wb") as f:
        writer.write(f)

    if on_progress:
        on_progress(100, f"Extracted {pages_to_extract} pages!")
    return dst


def pdf_to_images(src, dst_dir, on_progress=None):
    """
    Export each page of a PDF as a JPEG image.
    
    Args:
        src: source PDF path
        dst_dir: directory to save images
        on_progress: callable(percent, message)
        
    Returns:
        List of output image paths.
    """
    if on_progress:
        on_progress(5, "Rendering PDF pages...")

    if platform == "android":
        paths = _android_pdf_to_images(src, dst_dir, on_progress)
    else:
        paths = _fallback_pdf_to_images(src, dst_dir, on_progress)

    if on_progress:
        on_progress(100, f"Exported {len(paths)} pages!")
    return paths


def get_page_count(src):
    """Get the number of pages in a PDF."""
    import pypdf
    try:
        reader = pypdf.PdfReader(src)
        return len(reader.pages)
    except Exception as e:
        Logger.error(f"PDFTools: Could not count pages: {e}")
        return 0


def _android_pdf_to_images(src, dst_dir, on_progress=None):
    """Render PDF pages using Android's native PdfRenderer."""
    from jnius import autoclass

    paths = []
    try:
        ParcelFileDescriptor = autoclass('android.os.ParcelFileDescriptor')
        File = autoclass('java.io.File')
        PdfRenderer = autoclass('android.graphics.pdf.PdfRenderer')
        Bitmap = autoclass('android.graphics.Bitmap')
        FileOutputStream = autoclass('java.io.FileOutputStream')

        fd = ParcelFileDescriptor.open(File(src), ParcelFileDescriptor.MODE_READ_ONLY)
        renderer = PdfRenderer(fd)
        total = renderer.getPageCount()
        stem = Path(src).stem

        for i in range(total):
            if on_progress:
                percent = 10 + int((i / total) * 85)
                on_progress(percent, f"Rendering page {i+1}/{total}...")

            page = renderer.openPage(i)
            scale = 2.5
            w, h = int(page.getWidth() * scale), int(page.getHeight() * scale)

            bitmap = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
            page.render(bitmap, None, None, 1)

            img_path = os.path.join(dst_dir, f"{stem}_page_{i+1:03d}.jpg")
            out_stream = FileOutputStream(img_path)
            bitmap.compress(Bitmap.CompressFormat.JPEG, 90, out_stream)
            out_stream.close()
            bitmap.recycle()
            page.close()
            paths.append(img_path)

        renderer.close()
        fd.close()
    except Exception as e:
        Logger.error(f"PDFTools: Android render failed: {e}")
        raise

    return paths


def _fallback_pdf_to_images(src, dst_dir, on_progress=None):
    """Desktop fallback using pypdf image extraction."""
    import pypdf
    from PIL import Image

    paths = []
    try:
        reader = pypdf.PdfReader(src)
        total = len(reader.pages)
        stem = Path(src).stem

        for i, page in enumerate(reader.pages):
            if on_progress:
                percent = 10 + int((i / total) * 85)
                on_progress(percent, f"Extracting page {i+1}/{total}...")

            jp = os.path.join(dst_dir, f"{stem}_page_{i+1:03d}.jpg")
            imgs = list(page.images)
            if imgs:
                with Image.open(imgs[0].data) as pil_img:
                    pil_img.convert("RGB").save(jp, "JPEG", quality=90, optimize=True)
            else:
                Image.new("RGB", (595, 842), (255, 255, 255)).save(jp, "JPEG")
            paths.append(jp)
    except Exception as e:
        Logger.error(f"PDFTools: Fallback render failed: {e}")
        raise

    return paths
