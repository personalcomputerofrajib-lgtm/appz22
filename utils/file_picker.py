"""
file_picker.py — Cross-platform file picker.

Android: Uses Storage Access Framework (SAF) via ACTION_OPEN_DOCUMENT.
Desktop: Falls back to KivyMD's MDFileManager.
"""

import os
import tempfile
from kivy.utils import platform
from kivy.logger import Logger


# Lazy-loaded Java classes cache
_JAVA = {}


def _get_java(name):
    """Lazy-load a Java class via pyjnius."""
    if name not in _JAVA:
        from jnius import autoclass
        try:
            _JAVA[name] = autoclass(name)
        except Exception as e:
            Logger.error(f"FilePicker: Failed to load {name}: {e}")
            return None
    return _JAVA[name]


def pick_file(mime_types=None, allow_multiple=False):
    """
    Launch Android SAF file picker.
    
    Args:
        mime_types: list of MIME types e.g. ["image/*", "application/pdf"]
        allow_multiple: if True, allows selecting multiple files
    
    Returns request_code to match in on_activity_result.
    """
    if platform != "android":
        return None

    if mime_types is None:
        mime_types = ["*/*"]

    Intent = _get_java('android.content.Intent')
    PythonActivity = _get_java('org.kivy.android.PythonActivity')

    if not Intent or not PythonActivity:
        return None

    intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
    intent.addCategory(Intent.CATEGORY_OPENABLE)

    if len(mime_types) == 1:
        intent.setType(mime_types[0])
    else:
        intent.setType("*/*")
        intent.putExtra(Intent.EXTRA_MIME_TYPES, mime_types)

    if allow_multiple:
        intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, True)

    request_code = 42 if not allow_multiple else 43
    PythonActivity.mActivity.startActivityForResult(intent, request_code)
    return request_code


def copy_uri_to_temp(uri, temp_dir):
    """
    Copy a content:// URI to a local temp file.
    
    Args:
        uri: Android Uri object
        temp_dir: directory to copy into
        
    Returns:
        tuple (local_path, display_name)
    """
    if platform != "android":
        return None, None

    from jnius import autoclass

    PythonActivity = _get_java('org.kivy.android.PythonActivity')
    OpenableColumns = _get_java('android.provider.OpenableColumns')

    resolver = PythonActivity.mActivity.getContentResolver()

    # Get display name
    display_name = "file"
    try:
        cursor = resolver.query(uri, None, None, None, None)
        if cursor and cursor.moveToFirst():
            idx = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if idx >= 0:
                display_name = cursor.getString(idx)
            cursor.close()
    except Exception as e:
        Logger.warning(f"FilePicker: Could not get display name: {e}")

    # Copy content to temp file
    local_path = os.path.join(temp_dir, display_name)
    try:
        istream = resolver.openInputStream(uri)
        ArrayClass = autoclass('java.lang.reflect.Array')
        ByteType = autoclass('java.lang.Byte').TYPE
        buf = ArrayClass.newInstance(ByteType, 64 * 1024)
        
        with open(local_path, "wb") as f:
            while True:
                read = istream.read(buf)
                if read == -1:
                    break
                f.write(bytes(buf)[:read])
        istream.close()
    except Exception as e:
        Logger.error(f"FilePicker: Failed to copy URI: {e}")
        return None, None

    return local_path, display_name


def extract_uris_from_intent(intent, allow_multiple=False):
    """
    Extract URI(s) from an activity result intent.
    
    Returns:
        list of Uri objects
    """
    uris = []
    
    if allow_multiple and intent.getClipData() is not None:
        clip = intent.getClipData()
        for i in range(clip.getItemCount()):
            uris.append(clip.getItemAt(i).getUri())
    elif intent.getData() is not None:
        uris.append(intent.getData())
    
    return uris
