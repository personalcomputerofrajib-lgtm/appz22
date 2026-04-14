"""
convert.py — Image format conversion, resizing, and image-to-PDF.

All functions accept on_progress for UI updates.
"""

import os
from pathlib import Path
from kivy.logger import Logger


# Common preset sizes
PRESETS = {
    "Instagram Post": (1080, 1080),
    "Instagram Story": (1080, 1920),
    "HD 720p": (1280, 720),
    "Full HD 1080p": (1920, 1080),
    "4K": (3840, 2160),
    "Passport Photo": (600, 600),
    "A4 Print (300dpi)": (2480, 3508),
    "Thumbnail": (300, 300),
}

FORMAT_MAP = {
    "JPG": ("JPEG", ".jpg"),
    "JPEG": ("JPEG", ".jpg"),
    "PNG": ("PNG", ".png"),
    "WEBP": ("WEBP", ".webp"),
    "BMP": ("BMP", ".bmp"),
}


def convert_format(src, dst_dir, target_format, on_progress=None):
    """
    Convert an image to a different format.
    
    Args:
        src: source image path
        dst_dir: output directory
        target_format: "JPG", "PNG", "WEBP", or "BMP"
        on_progress: callable(percent, message)
        
    Returns:
        Output file path or None on failure.
    """
    from PIL import Image

    if on_progress:
        on_progress(10, f"Converting to {target_format}...")

    target_format = target_format.upper()
    if target_format not in FORMAT_MAP:
        raise ValueError(f"Unsupported format: {target_format}")

    pil_fmt, ext = FORMAT_MAP[target_format]
    stem = Path(src).stem
    dst = os.path.join(dst_dir, f"{stem}{ext}")

    try:
        with Image.open(src) as im:
            if on_progress:
                on_progress(30, f"Processing {im.size[0]}x{im.size[1]}...")

            # Handle transparency
            if pil_fmt in ("JPEG", "BMP") and im.mode in ("RGBA", "P", "PA"):
                bg = Image.new("RGB", im.size, (255, 255, 255))
                if im.mode == "P":
                    im = im.convert("RGBA")
                bg.paste(im, mask=im.split()[-1] if im.mode == "RGBA" else None)
                im = bg
            elif im.mode not in ("RGB", "RGBA", "L"):
                im = im.convert("RGB")

            save_kwargs = {"optimize": True}
            if pil_fmt == "JPEG":
                save_kwargs["quality"] = 92
            elif pil_fmt == "WEBP":
                save_kwargs["quality"] = 90

            im.save(dst, pil_fmt, **save_kwargs)

        if on_progress:
            on_progress(100, "Conversion complete!")
        return dst

    except Exception as e:
        Logger.error(f"Convert: Format conversion failed: {e}")
        raise


def resize_image(src, dst_dir, width, height, maintain_aspect=True, on_progress=None):
    """
    Resize an image to specified dimensions.
    
    Args:
        src: source image path  
        dst_dir: output directory
        width, height: target dimensions
        maintain_aspect: if True, fits within bounds maintaining ratio
        on_progress: callable(percent, message)
        
    Returns:
        Output file path or None on failure.
    """
    from PIL import Image

    if on_progress:
        on_progress(10, f"Resizing to {width}x{height}...")

    ext = Path(src).suffix.lower()
    if ext in (".jpg", ".jpeg"):
        pil_fmt = "JPEG"
    elif ext == ".png":
        pil_fmt = "PNG"
    elif ext == ".webp":
        pil_fmt = "WEBP"
    else:
        pil_fmt = "JPEG"
        ext = ".jpg"

    stem = Path(src).stem
    dst = os.path.join(dst_dir, f"{stem}_{width}x{height}{ext}")

    try:
        with Image.open(src) as im:
            orig_w, orig_h = im.size
            
            if on_progress:
                on_progress(30, f"Original: {orig_w}x{orig_h}")

            if maintain_aspect:
                im.thumbnail((width, height), Image.LANCZOS)
            else:
                im = im.resize((width, height), Image.LANCZOS)

            if on_progress:
                on_progress(70, f"Saving as {im.size[0]}x{im.size[1]}...")

            if pil_fmt == "JPEG" and im.mode in ("RGBA", "P"):
                im = im.convert("RGB")

            save_kwargs = {"optimize": True}
            if pil_fmt == "JPEG":
                save_kwargs["quality"] = 92

            im.save(dst, pil_fmt, **save_kwargs)

        if on_progress:
            on_progress(100, "Resize complete!")
        return dst

    except Exception as e:
        Logger.error(f"Convert: Resize failed: {e}")
        raise


def image_to_pdf(src, dst_dir, on_progress=None):
    """
    Convert a single image to an A4-fitted PDF.
    
    Args:
        src: source image path
        dst_dir: output directory
        on_progress: callable(percent, message)
        
    Returns:
        Output PDF path.
    """
    import img2pdf
    from PIL import Image

    if on_progress:
        on_progress(10, "Preparing image for PDF...")

    A4 = (595.27, 841.89)
    stem = Path(src).stem
    dst = os.path.join(dst_dir, f"{stem}.pdf")

    try:
        # Ensure image is in a format img2pdf can handle
        temp_jpg = os.path.join(dst_dir, f"_temp_{stem}.jpg")
        with Image.open(src) as im:
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            im.save(temp_jpg, "JPEG", quality=92, optimize=True)

        if on_progress:
            on_progress(50, "Creating PDF layout...")

        layout = img2pdf.get_layout_fun(A4, fit=img2pdf.FitMode.into)
        with open(dst, "wb") as f:
            f.write(img2pdf.convert([temp_jpg], layout_fun=layout))

        # Clean up temp
        try:
            os.remove(temp_jpg)
        except:
            pass

        if on_progress:
            on_progress(100, "PDF created!")
        return dst

    except Exception as e:
        Logger.error(f"Convert: Image to PDF failed: {e}")
        raise


def batch_convert(file_list, dst_dir, target_format, on_progress=None):
    """
    Convert multiple images to a target format.
    
    Args:
        file_list: list of source image paths
        dst_dir: output directory
        target_format: "JPG", "PNG", "WEBP", etc.
        on_progress: callable(percent, message)
        
    Returns:
        List of output file paths.
    """
    results = []
    total = len(file_list)

    for i, src in enumerate(file_list):
        percent = int(((i) / total) * 100)
        if on_progress:
            on_progress(percent, f"Converting {i + 1}/{total}: {os.path.basename(src)}")

        try:
            result = convert_format(src, dst_dir, target_format)
            results.append(result)
        except Exception as e:
            Logger.warning(f"Convert: Batch item {src} failed: {e}")
            results.append(None)

    if on_progress:
        on_progress(100, f"Batch complete: {len([r for r in results if r])}/{total} succeeded")
    return results
