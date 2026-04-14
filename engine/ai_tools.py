"""
ai_tools.py — AI-powered image processing using Google ML Kit.

Uses ML Kit Selfie Segmentation for background removal.
Only functional on Android. Desktop shows an informative message.
"""

import os
from pathlib import Path
from kivy.utils import platform
from kivy.logger import Logger


def remove_background(src, dst, on_progress=None, on_complete=None, on_error=None):
    """
    Remove background from a portrait/selfie image using ML Kit.
    
    This uses Google ML Kit Selfie Segmentation which runs fully on-device.
    No data leaves the phone.
    
    Args:
        src: source image path
        dst: destination PNG path (with transparency)
        on_progress: callable(percent, message)
        on_complete: callable(result_path)
        on_error: callable(error_message)
    """
    if platform != "android":
        if on_error:
            on_error("AI background removal requires Android")
        return

    if on_progress:
        on_progress(5, "Initializing AI engine...")

    try:
        from jnius import autoclass, PythonJavaClass, java_method

        # Load required Java classes
        BitmapFactory = autoclass('android.graphics.BitmapFactory')
        Bitmap = autoclass('android.graphics.Bitmap')
        Canvas = autoclass('android.graphics.Canvas')
        Paint = autoclass('android.graphics.Paint')
        Color = autoclass('android.graphics.Color')
        FileOutputStream = autoclass('java.io.FileOutputStream')

        # ML Kit classes
        SelfieSegmenterOptions = autoclass(
            'com.google.mlkit.vision.segmentation.selfie.SelfieSegmenterOptions'
        )
        Segmentation = autoclass(
            'com.google.mlkit.vision.segmentation.Segmentation'
        )
        InputImage = autoclass(
            'com.google.mlkit.vision.common.InputImage'
        )

        if on_progress:
            on_progress(15, "Loading image...")

        # Load the bitmap
        options = BitmapFactory.Options()
        options.inMutable = True
        bitmap = BitmapFactory.decodeFile(src, options)

        if bitmap is None:
            if on_error:
                on_error("Could not load image")
            return

        w, h = bitmap.getWidth(), bitmap.getHeight()

        # Limit size to avoid OOM
        max_dim = 1024
        if w > max_dim or h > max_dim:
            scale = max_dim / max(w, h)
            new_w = int(w * scale)
            new_h = int(h * scale)
            bitmap = Bitmap.createScaledBitmap(bitmap, new_w, new_h, True)
            w, h = new_w, new_h

        if on_progress:
            on_progress(25, "Preparing AI model...")

        # Create segmenter
        seg_opts = (SelfieSegmenterOptions.Builder()
                    .setDetectorMode(SelfieSegmenterOptions.SINGLE_IMAGE_MODE)
                    .build())
        segmenter = Segmentation.getClient(seg_opts)

        # Create InputImage
        input_image = InputImage.fromBitmap(bitmap, 0)

        if on_progress:
            on_progress(35, "Running AI segmentation...")

        # Process with ML Kit
        # We need to use Tasks API synchronously since we're already on a bg thread.
        Tasks = autoclass('com.google.android.gms.tasks.Tasks')
        
        task = segmenter.process(input_image)
        # Block until complete (we're on a background thread, this is safe)
        # 'await' is a Python reserved keyword, must use getattr
        result = getattr(Tasks, 'await')(task)
        
        if on_progress:
            on_progress(60, "Processing segmentation mask...")
        
        # Get the mask buffer
        mask_buffer = result.getBuffer()
        mask_w = result.getWidth()
        mask_h = result.getHeight()
        
        if on_progress:
            on_progress(70, "Applying transparency mask...")
        
        # Create output bitmap with transparency
        output = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        
        # Read mask values and apply to pixels
        pixels = [0] * (w * h)
        bitmap.getPixels(pixels, 0, w, 0, 0, w, h)
        
        mask_buffer.rewind()
        for y in range(h):
            for x in range(w):
                # Map pixel position to mask position
                mask_x = int(x * mask_w / w)
                mask_y = int(y * mask_h / h)
                mask_idx = mask_y * mask_w + mask_x
                
                mask_buffer.position(mask_idx * 4)  # float = 4 bytes
                confidence = mask_buffer.getFloat()
                
                pixel_idx = y * w + x
                if confidence > 0.5:  # Person detected
                    output.setPixel(x, y, pixels[pixel_idx])
                else:
                    output.setPixel(x, y, Color.TRANSPARENT)
        
        if on_progress:
            on_progress(90, "Saving result...")
        
        # Save as PNG (supports transparency)
        out_stream = FileOutputStream(dst)
        output.compress(Bitmap.CompressFormat.PNG, 100, out_stream)
        out_stream.close()
        
        # Cleanup
        output.recycle()
        bitmap.recycle()
        segmenter.close()

        if on_progress:
            on_progress(100, "Background removed!")
        
        if on_complete:
            on_complete(dst)

    except Exception as e:
        error_msg = str(e)
        Logger.error(f"AITools: Background removal failed: {error_msg}")
        
        # Provide user-friendly error messages
        if "Tasks" in error_msg or "await" in error_msg:
            error_msg = "AI model is still downloading. Please try again in a moment."
        elif "OutOfMemory" in error_msg:
            error_msg = "Image too large for AI processing. Try a smaller image."
        elif "not found" in error_msg.lower() or "class" in error_msg.lower():
            error_msg = "AI engine not available. ML Kit may not be installed correctly."
        
        if on_error:
            on_error(error_msg)
