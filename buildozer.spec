[app]
title = Swift Suite
package.name = swiftsuite
package.domain = org.rajib
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
source.include_patterns = ui/*,engine/*,utils/*
version = 2.0

# Requirements
requirements = python3,kivy==2.3.0,kivymd==1.2.0,pillow==9.5.0,pypdf,img2pdf,pyjnius

orientation = portrait
osx.python_version = 3
osx.kivy_version = 2.3.0
fullscreen = 0

# Android permissions
android.permissions = READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,MANAGE_EXTERNAL_STORAGE,INTERNET,READ_MEDIA_IMAGES,READ_MEDIA_VIDEO

android.api = 33
android.minapi = 23
android.ndk = 25b
android.archs = arm64-v8a

# ML Kit dependencies for AI background removal
android.gradle_dependencies = com.google.mlkit:segmentation-selfie:16.0.0-beta6,com.google.mlkit:vision-common:17.3.0,com.google.android.gms:play-services-tasks:18.0.2

# Android packaging
android.accept_sdk_license = True
android.skip_update = False

# Icon and splash (optional)
# icon.filename = %(source.dir)s/data/icon.png
# presplash.filename = %(source.dir)s/data/presplash.png

[buildozer]
log_level = 2
warn_on_root = 0
