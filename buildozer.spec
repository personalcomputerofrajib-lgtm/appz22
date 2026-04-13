[app]
title = SwiftCompressor
package.name = swiftcompressor
package.domain = org.rajib
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.1

# Requirements
requirements = python3, kivy==2.3.0, kivymd==1.2.0, pillow==9.5.0, pypdf, img2pdf

orientation = portrait
osx.python_version = 3
osx.kivy_version = 2.3.0
fullscreen = 0

# Android permissions
android.permissions = READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE, MANAGE_EXTERNAL_STORAGE
android.api = 33
android.minapi = 21
# android.sdk = 33
android.ndk = 25b
android.archs = arm64-v8a

# Android packaging
android.preserve_paths = lib/python*/site-packages/*.so
android.accept_sdk_license = True
android.skip_update = False

# Icon and splash (optional, defaults used if not provided)
# icon.filename = %(source.dir)s/data/icon.png
# presplash.filename = %(source.dir)s/data/presplash.png

[buildozer]
log_level = 2
warn_on_root = 0
