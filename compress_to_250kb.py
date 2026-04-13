#!/usr/bin/env python3
"""
compress_to_250kb.py  –  No Poppler needed!
--------------------------------------------
Upload an image (JPG/PNG/WEBP/BMP/TIFF) or a PDF and get back
a compressed version that is <= 250 KB with correct A4 page sizing.

Usage:
    python compress_to_250kb.py <input_file> [output_file]

Requirements (install once):
    pip install pypdf pillow img2pdf reportlab pikepdf pypdfium2
"""

import sys, os, tempfile
from pathlib import Path

TARGET_KB  = 250
TARGET_B   = TARGET_KB * 1024
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}
PDF_EXTS   = {".pdf"}


def size_kb(path):
    return os.path.getsize(path) / 1024


def ensure_libs():
    missing = []
    for pkg, imp in [("pypdf","pypdf"),("Pillow","PIL"),
                     ("img2pdf","img2pdf"),("reportlab","reportlab"),
                     ("pikepdf","pikepdf")]:
        try: __import__(imp)
        except ImportError: missing.append(pkg)
    if missing:
        print(f"[!] Missing: {', '.join(missing)}")
        print(f"    Run:  pip install {' '.join(missing)}")
        sys.exit(1)


# -- fitted A4 PDF from an image ----------------------------------------------

def image_to_fitted_pdf(img_path, out_pdf):
    from PIL import Image
    import img2pdf
    from reportlab.lib.pagesizes import A4

    with Image.open(img_path) as im:
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        tmp = img_path + "_norm.jpg"
        im.save(tmp, "JPEG", quality=85, optimize=True)

    a4_w_pt, a4_h_pt = A4
    layout = img2pdf.get_layout_fun(
        (a4_w_pt, a4_h_pt), fit=img2pdf.FitMode.into
    )
    with open(out_pdf, "wb") as f:
        f.write(img2pdf.convert(tmp, layout_fun=layout))
    os.remove(tmp)


# -- compress image -----------------------------------------------------------

def compress_image(src, dst, ext):
    from PIL import Image
    fmt_map = {"jpg":"JPEG","jpeg":"JPEG","png":"PNG",
               "webp":"WEBP","bmp":"BMP","tiff":"TIFF","tif":"TIFF"}
    pil_fmt = fmt_map.get(ext.lower().lstrip("."), "JPEG")

    with Image.open(src) as im:
        orig_w, orig_h = im.size

    quality, scale = 85, 1.0
    for attempt in range(30):
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

        kb = size_kb(dst)
        print(f"  attempt {attempt+1}: {kb:.1f} KB  (quality={quality}, scale={scale:.2f})")
        if os.path.getsize(dst) <= TARGET_B:
            return True
        if quality > 20 and pil_fmt in ("JPEG","WEBP"):
            quality = max(20, quality - 10)
        else:
            scale = max(0.05, scale - 0.10)
    return os.path.getsize(dst) <= TARGET_B


# -- rasterise PDF pages with best available library (no Poppler needed) ------

def rasterise_pages(src, tmp_dir, dpi):
    """
    Returns a list of JPEG paths, one per page.
    Tries pypdfium2 first (best, no Poppler), then falls back to pypdf image extraction.
    """
    import pypdf
    from PIL import Image

    # -- best option: pypdfium2 -----------------------------------------------
    try:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(src)
        scale_factor = dpi / 72.0
        paths = []
        for i, page in enumerate(pdf):
            bmp = page.render(scale=scale_factor, rotation=0)
            pil_img = bmp.to_pil()
            jp = os.path.join(tmp_dir, f"page_{i:04d}.jpg")
            pil_img.convert("RGB").save(jp, "JPEG", quality=75, optimize=True)
            paths.append(jp)
        pdf.close()
        return paths
    except ImportError:
        pass

    # -- fallback: extract embedded images from each page via pypdf -----------
    print("\n  [tip] pip install pypdfium2  gives much better PDF compression\n  ", end="")
    reader = pypdf.PdfReader(src)
    paths = []
    for i, page in enumerate(reader.pages):
        jp = os.path.join(tmp_dir, f"page_{i:04d}.jpg")
        imgs = list(page.images)
        if imgs:
            pil_img = Image.open(imgs[0].data)
        else:
            pil_img = Image.new("RGB", (595, 842), "white")
        pil_img.convert("RGB").save(jp, "JPEG", quality=75, optimize=True)
        paths.append(jp)
    return paths


# -- compress PDF -------------------------------------------------------------

def compress_pdf(src, dst):
    import pypdf, img2pdf
    from reportlab.lib.pagesizes import A4

    # pass 1: lossless cleanup
    writer = pypdf.PdfWriter()
    reader = pypdf.PdfReader(src)
    for page in reader.pages:
        writer.add_page(page)
    try:
        writer.compress_identical_objects(remove_duplicates=True,
                                          remove_unreferenced=True)
    except TypeError:
        writer.compress_identical_objects(remove_identicals=True,
                                          remove_orphans=True)
    with open(dst, "wb") as f:
        writer.write(f)
    print(f"  after lossless re-save : {size_kb(dst):.1f} KB")
    if os.path.getsize(dst) <= TARGET_B:
        return True

    # pass 2: rasterise + recompose (the double-print approach)
    a4_w_pt, a4_h_pt = A4
    layout = img2pdf.get_layout_fun((a4_w_pt, a4_h_pt), fit=img2pdf.FitMode.into)

    for dpi in (150, 120, 96, 72, 60, 48):
        print(f"  rasterising at {dpi} DPI ... ", end="", flush=True)
        with tempfile.TemporaryDirectory() as tmp:
            jpg_paths = rasterise_pages(src, tmp, dpi)
            if not jpg_paths:
                print("skipped"); continue
            with open(dst, "wb") as f:
                f.write(img2pdf.convert(jpg_paths, layout_fun=layout))
        print(f"{size_kb(dst):.1f} KB")
        if os.path.getsize(dst) <= TARGET_B:
            return True

    return os.path.getsize(dst) <= TARGET_B


# -- main ---------------------------------------------------------------------

def main():
    ensure_libs()

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    src = sys.argv[1]
    ext = Path(src).suffix.lower()
    dst = sys.argv[2] if len(sys.argv) >= 3 else \
          str(Path(src).parent / f"{Path(src).stem}_compressed{ext}")

    if not os.path.exists(src):
        print(f"[!] File not found: {src}"); sys.exit(1)

    orig_kb = size_kb(src)
    print(f"\n{'='*55}")
    print(f"  Input : {src}  ({orig_kb:.1f} KB)")
    print(f"  Target: <= {TARGET_KB} KB")
    print(f"{'='*55}")

    if ext in IMAGE_EXTS:
        out_img = dst
        out_pdf = str(Path(dst).with_suffix(".pdf"))

        print(f"\n[1/2] Compressing image -> {out_img}")
        ok = compress_image(src, out_img, ext)

        print(f"\n[2/2] Creating fitted A4 PDF -> {out_pdf}")
        image_to_fitted_pdf(out_img if ok else src, out_pdf)
        if os.path.getsize(out_pdf) > TARGET_B:
            compress_pdf(out_pdf, out_pdf)

        print(f"\n{'='*55}")
        print(f"  Compressed image : {size_kb(out_img):.1f} KB  ->  {out_img}")
        print(f"  Fitted A4 PDF    : {size_kb(out_pdf):.1f} KB  ->  {out_pdf}")

    elif ext in PDF_EXTS:
        out_pdf = dst if dst.lower().endswith(".pdf") else dst + ".pdf"
        print(f"\nCompressing PDF -> {out_pdf}")

        try:
            import pypdfium2
        except ImportError:
            print("  [tip] For best results (no Poppler needed):")
            print("        pip install pypdfium2\n")

        ok = compress_pdf(src, out_pdf)
        status = "OK - within target" if ok else \
                 "WARNING: still above target  ->  run: pip install pypdfium2"
        print(f"\n{'='*55}")
        print(f"  Original  : {orig_kb:.1f} KB")
        print(f"  Compressed: {size_kb(out_pdf):.1f} KB  {status}")
        print(f"  Saved to  : {out_pdf}")

    else:
        print(f"[!] Unsupported type: {ext}")
        print(f"    Supported: {IMAGE_EXTS | PDF_EXTS}")
        sys.exit(1)

    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()