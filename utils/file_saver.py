"""
file_saver.py — Save processed files to the user's Downloads folder.

Handles Android's scoped storage + MediaStore notification so files 
appear immediately in the file manager and gallery.
"""

import os
import shutil
from kivy.utils import platform
from kivy.logger import Logger


def get_download_dir():
    """Get the Downloads directory path."""
    if platform == "android":
        try:
            from android.storage import primary_external_storage_path
            return os.path.join(primary_external_storage_path(), "Download")
        except ImportError:
            return "/sdcard/Download"
    else:
        return os.path.join(os.path.expanduser("~"), "Downloads")


def save_file(src_path, filename=None, subfolder="SwiftSuite"):
    """
    Copy a processed file to Downloads/SwiftSuite/.
    
    Args:
        src_path: path to the processed temp file
        filename: output filename (defaults to source basename)
        subfolder: subfolder inside Downloads
        
    Returns:
        Final path where file was saved, or None on failure.
    """
    if not src_path or not os.path.exists(src_path):
        Logger.error(f"FileSaver: Source does not exist: {src_path}")
        return None

    if filename is None:
        filename = os.path.basename(src_path)

    dst_dir = os.path.join(get_download_dir(), subfolder)
    try:
        os.makedirs(dst_dir, exist_ok=True)
    except Exception as e:
        Logger.error(f"FileSaver: Cannot create dir {dst_dir}: {e}")
        # Fallback to Downloads root
        dst_dir = get_download_dir()
        os.makedirs(dst_dir, exist_ok=True)

    dst_path = os.path.join(dst_dir, filename)

    # Avoid overwriting: append counter
    base, ext = os.path.splitext(filename)
    counter = 1
    while os.path.exists(dst_path):
        dst_path = os.path.join(dst_dir, f"{base}_{counter}{ext}")
        counter += 1

    try:
        shutil.copy2(src_path, dst_path)
    except Exception as e:
        Logger.error(f"FileSaver: Copy failed: {e}")
        return None

    # Notify MediaStore so file shows up immediately
    if platform == "android":
        try:
            _notify_media_store(dst_path)
        except Exception as e:
            Logger.warning(f"FileSaver: MediaStore notification failed: {e}")

    Logger.info(f"FileSaver: Saved to {dst_path}")
    return dst_path


def _notify_media_store(file_path):
    """Scan the file so it appears in gallery/file manager immediately."""
    from jnius import autoclass
    
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    Intent = autoclass('android.content.Intent')
    Uri = autoclass('android.net.Uri')
    File = autoclass('java.io.File')
    
    context = PythonActivity.mActivity
    intent = Intent(Intent.ACTION_MEDIA_SCANNER_SCAN_FILE)
    intent.setData(Uri.fromFile(File(file_path)))
    context.sendBroadcast(intent)


def format_size(size_bytes):
    """Format bytes to human readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
