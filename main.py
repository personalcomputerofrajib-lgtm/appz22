"""
Swift Suite v2.0 — Entry Point

Professional document toolkit for Android.
All processing is private and runs locally on-device.
"""

import os
import sys
from kivy.utils import platform
from kivy.logger import Logger


def request_android_permissions():
    """Request only valid runtime permissions."""
    if platform != "android":
        return

    from android.permissions import request_permissions, Permission

    perms = [
        Permission.READ_EXTERNAL_STORAGE,
        Permission.WRITE_EXTERNAL_STORAGE,
    ]

    # Android 13+ granular media permissions
    try:
        from android import api_version
        if api_version >= 33:
            perms.extend([
                'android.permission.READ_MEDIA_IMAGES',
                'android.permission.READ_MEDIA_VIDEO',
            ])
    except ImportError:
        pass

    request_permissions(perms)


def main():
    """Launch Swift Suite."""
    try:
        request_android_permissions()

        from ui.app import SwiftSuiteApp
        SwiftSuiteApp().run()

    except Exception as e:
        Logger.error(f"SwiftSuite: Fatal error: {e}")
        import traceback
        Logger.error(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
