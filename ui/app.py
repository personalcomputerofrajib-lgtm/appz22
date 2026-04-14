"""
app.py — Swift Suite Application Controller.

Connects the UI (layout.kv) to the engine modules.
All heavy operations run on background threads via BackgroundTask.
"""

import os
import tempfile
from pathlib import Path

from kivy.lang import Builder
from kivy.utils import platform
from kivy.logger import Logger
from kivy.clock import Clock

from kivymd.app import MDApp
from kivymd.toast import toast
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDFlatButton

from utils.threading_helper import BackgroundTask, TaskLock
from utils.file_saver import save_file, format_size
from engine.compress import compress_image, compress_pdf, get_file_info, IMAGE_EXTS, PDF_EXTS


class SwiftSuiteApp(MDApp):
    """Main application class."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.temp_dir = tempfile.mkdtemp()
        self.task_lock = TaskLock()
        self._dialog = None
        
        # State for each tab
        self.compress_file = None
        self.compress_output = "PDF"
        
        self.convert_file = None
        self.convert_op = "format"
        self.target_format = "JPG"
        
        self.pdf_files = []
        self.pdf_op = "merge"
        
        self.ai_file = None
        
        # File picker context
        self._pick_context = None

    def build(self):
        self.theme_cls.primary_palette = "DeepPurple"
        self.theme_cls.theme_style = "Dark"
        self.title = "Swift Suite"

        # Bind activity result for Android file picker
        if platform == "android":
            from android import activity
            activity.bind(on_activity_result=self._on_activity_result)

        kv_path = os.path.join(os.path.dirname(__file__), "layout.kv")
        return Builder.load_file(kv_path)

    # ==========================================================
    #  Widget ID Helper
    # ==========================================================

    def _w(self, widget_id):
        """Find a widget by ID in the widget tree (handles nested bottom nav)."""
        def _search(widget, target):
            if hasattr(widget, 'ids') and target in widget.ids:
                return widget.ids[target]
            for child in widget.children:
                result = _search(child, target)
                if result:
                    return result
            return None
        return _search(self.root, widget_id)

    # ==========================================================
    #  File Picker
    # ==========================================================

    def pick_file_for(self, context):
        """Open file picker for a specific tab context."""
        self._pick_context = context

        if platform == "android":
            from utils.file_picker import pick_file
            
            if context == "compress":
                pick_file(["image/*", "application/pdf"])
            elif context == "convert":
                pick_file(["image/*"])
            elif context == "pdf":
                allow_multi = (self.pdf_op == "merge")
                pick_file(["application/pdf"], allow_multiple=allow_multi)
            elif context == "ai":
                pick_file(["image/*"])
        else:
            toast("File picker requires Android")

    def _on_activity_result(self, request_code, result_code, intent):
        """Handle Android SAF file picker result."""
        if result_code != -1 or intent is None:
            return

        from utils.file_picker import copy_uri_to_temp, extract_uris_from_intent

        allow_multi = (request_code == 43)
        uris = extract_uris_from_intent(intent, allow_multi)

        if not uris:
            toast("No file selected")
            return

        # Copy files to temp
        paths = []
        names = []
        for uri in uris:
            path, name = copy_uri_to_temp(uri, self.temp_dir)
            if path:
                paths.append(path)
                names.append(name)

        if not paths:
            toast("Failed to load file")
            return

        # Route to the correct tab handler
        ctx = self._pick_context
        if ctx == "compress":
            self._set_compress_file(paths[0], names[0])
        elif ctx == "convert":
            self._set_convert_file(paths[0], names[0])
        elif ctx == "pdf":
            self._set_pdf_files(paths, names)
        elif ctx == "ai":
            self._set_ai_file(paths[0], names[0])

    # ==========================================================
    #  TAB 1: COMPRESS
    # ==========================================================

    def _set_compress_file(self, path, name):
        self.compress_file = path
        label = self._w('comp_file_label')
        size_label = self._w('comp_file_size')
        if label:
            label.text = name
            label.text_color = (0.95, 0.95, 0.97, 1)
        if size_label:
            size_label.text = f"Size: {format_size(os.path.getsize(path))}"
        toast(f"Loaded: {name}")

    def on_slider_change(self, value):
        label = self._w('comp_slider_val')
        if label:
            label.text = f"{int(value)} KB"

    def set_compress_output(self, mode):
        self.compress_output = mode
        btn_pdf = self._w('btn_out_pdf')
        btn_orig = self._w('btn_out_orig')
        
        active_bg = (0.45, 0.32, 0.95, 1)
        active_text = (1, 1, 1, 1)
        inactive_bg = (0, 0, 0, 0)
        inactive_text = (0.7, 0.7, 0.75, 1)
        
        if mode == "PDF":
            if btn_pdf:
                btn_pdf.md_bg_color = active_bg
                btn_pdf.text_color = active_text
            if btn_orig:
                btn_orig.md_bg_color = inactive_bg
                btn_orig.text_color = inactive_text
        else:
            if btn_orig:
                btn_orig.md_bg_color = active_bg
                btn_orig.text_color = active_text
            if btn_pdf:
                btn_pdf.md_bg_color = inactive_bg
                btn_pdf.text_color = inactive_text

    def start_compress(self):
        if not self.compress_file:
            toast("Select a file first")
            return
        if not self.task_lock.acquire():
            toast("Please wait for current task to finish")
            return

        slider = self._w('comp_slider')
        target_kb = int(slider.value) if slider else 250
        src = self.compress_file
        ext = Path(src).suffix.lower()

        def do_work(on_progress):
            target_ext = ".pdf" if self.compress_output == "PDF" else ext
            stem = Path(src).stem
            out_name = f"{stem}_compressed{target_ext}"
            tmp_out = os.path.join(self.temp_dir, out_name)

            if ext in IMAGE_EXTS:
                if target_ext == ".pdf":
                    # Compress image then convert to PDF
                    tmp_img = os.path.join(self.temp_dir, f"_tmp_comp.jpg")
                    on_progress(10, "Compressing image...")
                    compress_image(src, tmp_img, target_kb, on_progress=None)

                    on_progress(70, "Converting to PDF...")
                    from engine.convert import image_to_pdf
                    tmp_out = image_to_pdf(tmp_img, self.temp_dir)
                    try:
                        os.remove(tmp_img)
                    except:
                        pass
                else:
                    compress_image(src, tmp_out, target_kb, on_progress)
            elif ext in PDF_EXTS:
                compress_pdf(src, tmp_out, target_kb, on_progress)
            else:
                raise ValueError(f"Unsupported file type: {ext}")

            # Save to Downloads
            saved = save_file(tmp_out)
            return saved

        def on_complete(result):
            self.task_lock.release()
            self._update_progress('comp_progress', 0)
            if result:
                size = format_size(os.path.getsize(result))
                self._update_status('comp_status', f"✓ Saved: {size}")
                self._show_dialog("Success", f"Compressed file saved!\n\nLocation: {result}\nSize: {size}")
            else:
                self._update_status('comp_status', "Failed to save")
                toast("Compression failed")

        def on_error(msg):
            self.task_lock.release()
            self._update_progress('comp_progress', 0)
            self._update_status('comp_status', f"✗ Error")
            self._show_dialog("Error", msg)

        def on_progress(pct, msg):
            self._update_progress('comp_progress', pct)
            self._update_status('comp_status', msg)

        self._update_status('comp_status', "Starting...")
        task = BackgroundTask(
            target=do_work,
            on_progress=on_progress,
            on_complete=on_complete,
            on_error=on_error,
        )
        task.start()

    # ==========================================================
    #  TAB 2: CONVERT
    # ==========================================================

    def _set_convert_file(self, path, name):
        self.convert_file = path
        label = self._w('conv_file_label')
        if label:
            label.text = name
            label.text_color = (0.95, 0.95, 0.97, 1)
        toast(f"Loaded: {name}")

    def set_convert_op(self, op):
        self.convert_op = op
        
        # Update button states
        ops = {"format": "btn_op_format", "resize": "btn_op_resize", "topdf": "btn_op_topdf"}
        for key, btn_id in ops.items():
            btn = self._w(btn_id)
            if btn:
                if key == op:
                    btn.md_bg_color = (0.45, 0.32, 0.95, 1)
                    btn.text_color = (1, 1, 1, 1)
                else:
                    btn.md_bg_color = (0, 0, 0, 0)
                    btn.text_color = (0.7, 0.7, 0.75, 1)

        # Show/hide option cards
        fmt_card = self._w('format_options_card')
        resize_card = self._w('resize_options_card')
        
        if fmt_card:
            if op == "format":
                fmt_card.opacity = 1
                fmt_card.disabled = False
                fmt_card.size_hint_y = None
                fmt_card.height = fmt_card.minimum_height
            else:
                fmt_card.opacity = 0
                fmt_card.disabled = True
                fmt_card.height = 0

        if resize_card:
            if op == "resize":
                resize_card.opacity = 1
                resize_card.disabled = False
                resize_card.size_hint_y = None
                resize_card.height = resize_card.minimum_height
            else:
                resize_card.opacity = 0
                resize_card.disabled = True
                resize_card.height = 0

    def set_target_format(self, fmt):
        self.target_format = fmt
        fmts = {"JPG": "btn_fmt_jpg", "PNG": "btn_fmt_png", "WEBP": "btn_fmt_webp"}
        for key, btn_id in fmts.items():
            btn = self._w(btn_id)
            if btn:
                if key == fmt:
                    btn.md_bg_color = (0.45, 0.32, 0.95, 1)
                    btn.text_color = (1, 1, 1, 1)
                else:
                    btn.md_bg_color = (0, 0, 0, 0)
                    btn.text_color = (0.7, 0.7, 0.75, 1)

    def start_convert(self):
        if not self.convert_file:
            toast("Select a file first")
            return
        if not self.task_lock.acquire():
            toast("Please wait for current task to finish")
            return

        src = self.convert_file
        op = self.convert_op

        def do_work(on_progress):
            from engine import convert as conv

            if op == "format":
                result = conv.convert_format(src, self.temp_dir, self.target_format, on_progress)
            elif op == "resize":
                w_widget = self._w('resize_w')
                h_widget = self._w('resize_h')
                w = int(w_widget.text) if w_widget and w_widget.text else 1080
                h = int(h_widget.text) if h_widget and h_widget.text else 1080
                result = conv.resize_image(src, self.temp_dir, w, h, True, on_progress)
            elif op == "topdf":
                result = conv.image_to_pdf(src, self.temp_dir, on_progress)
            else:
                raise ValueError(f"Unknown operation: {op}")

            saved = save_file(result)
            return saved

        def on_complete(result):
            self.task_lock.release()
            self._update_progress('conv_progress', 0)
            if result:
                size = format_size(os.path.getsize(result))
                self._update_status('conv_status', f"✓ Saved: {size}")
                self._show_dialog("Success", f"File converted!\n\nLocation: {result}\nSize: {size}")
            else:
                self._update_status('conv_status', "Failed")
                toast("Conversion failed")

        def on_error(msg):
            self.task_lock.release()
            self._update_progress('conv_progress', 0)
            self._update_status('conv_status', f"✗ Error")
            self._show_dialog("Error", msg)

        def on_progress(pct, msg):
            self._update_progress('conv_progress', pct)
            self._update_status('conv_status', msg)

        self._update_status('conv_status', "Starting...")
        BackgroundTask(target=do_work, on_progress=on_progress, on_complete=on_complete, on_error=on_error).start()

    # ==========================================================
    #  TAB 3: PDF TOOLS
    # ==========================================================

    def _set_pdf_files(self, paths, names):
        self.pdf_files = paths
        label = self._w('pdf_file_label')
        info = self._w('pdf_info_label')
        
        if len(paths) == 1:
            if label:
                label.text = names[0]
                label.text_color = (0.95, 0.95, 0.97, 1)
            if info:
                from engine.pdf_tools import get_page_count
                pages = get_page_count(paths[0])
                info.text = f"{pages} pages • {format_size(os.path.getsize(paths[0]))}"
                
                # Update split end field
                end_field = self._w('split_end')
                if end_field:
                    end_field.text = str(pages)
        else:
            if label:
                label.text = f"{len(paths)} PDFs selected"
                label.text_color = (0.95, 0.95, 0.97, 1)
            if info:
                total = sum(os.path.getsize(p) for p in paths)
                info.text = f"Total: {format_size(total)}"
        
        toast(f"Loaded {len(paths)} file(s)")

    def set_pdf_op(self, op):
        self.pdf_op = op
        ops = {"merge": "btn_pdf_merge", "split": "btn_pdf_split", "toimg": "btn_pdf_toimg"}
        for key, btn_id in ops.items():
            btn = self._w(btn_id)
            if btn:
                if key == op:
                    btn.md_bg_color = (0.45, 0.32, 0.95, 1)
                    btn.text_color = (1, 1, 1, 1)
                else:
                    btn.md_bg_color = (0, 0, 0, 0)
                    btn.text_color = (0.7, 0.7, 0.75, 1)

        # Show/hide split options
        split_card = self._w('split_options_card')
        if split_card:
            if op == "split":
                split_card.opacity = 1
                split_card.disabled = False
                split_card.size_hint_y = None
                split_card.height = split_card.minimum_height
            else:
                split_card.opacity = 0
                split_card.disabled = True
                split_card.height = 0

        # Update file label hint
        label = self._w('pdf_file_label')
        if label and not self.pdf_files:
            if op == "merge":
                label.text = "Select multiple PDFs to merge"
            elif op == "split":
                label.text = "Select PDF to split"
            elif op == "toimg":
                label.text = "Select PDF to export as images"

    def start_pdf_op(self):
        if not self.pdf_files:
            toast("Select PDF file(s) first")
            return
        if not self.task_lock.acquire():
            toast("Please wait for current task to finish")
            return

        op = self.pdf_op
        files = self.pdf_files

        def do_work(on_progress):
            from engine import pdf_tools

            if op == "merge":
                if len(files) < 2:
                    raise ValueError("Select at least 2 PDFs to merge")
                tmp_out = os.path.join(self.temp_dir, "merged.pdf")
                pdf_tools.merge_pdfs(files, tmp_out, on_progress)
                return save_file(tmp_out, "merged.pdf")

            elif op == "split":
                if not files:
                    raise ValueError("Select a PDF first")
                start_w = self._w('split_start')
                end_w = self._w('split_end')
                start = int(start_w.text) if start_w and start_w.text else 1
                end = int(end_w.text) if end_w and end_w.text else 999
                
                stem = Path(files[0]).stem
                tmp_out = os.path.join(self.temp_dir, f"{stem}_p{start}-{end}.pdf")
                pdf_tools.split_pdf(files[0], start, end, tmp_out, on_progress)
                return save_file(tmp_out)

            elif op == "toimg":
                if not files:
                    raise ValueError("Select a PDF first")
                import tempfile as tf
                img_dir = tf.mkdtemp(dir=self.temp_dir)
                paths = pdf_tools.pdf_to_images(files[0], img_dir, on_progress)
                # Save all images
                saved = []
                for p in paths:
                    s = save_file(p)
                    if s:
                        saved.append(s)
                return f"{len(saved)} images exported"

        def on_complete(result):
            self.task_lock.release()
            self._update_progress('pdf_progress', 0)
            if result and os.path.exists(str(result)):
                size = format_size(os.path.getsize(result))
                self._update_status('pdf_status', f"✓ Done: {size}")
                self._show_dialog("Success", f"PDF operation complete!\n\n{result}")
            else:
                self._update_status('pdf_status', f"✓ {result}")
                self._show_dialog("Success", str(result))

        def on_error(msg):
            self.task_lock.release()
            self._update_progress('pdf_progress', 0)
            self._update_status('pdf_status', f"✗ Error")
            self._show_dialog("Error", msg)

        def on_progress(pct, msg):
            self._update_progress('pdf_progress', pct)
            self._update_status('pdf_status', msg)

        self._update_status('pdf_status', "Starting...")
        BackgroundTask(target=do_work, on_progress=on_progress, on_complete=on_complete, on_error=on_error).start()

    # ==========================================================
    #  TAB 4: AI TOOLS
    # ==========================================================

    def _set_ai_file(self, path, name):
        self.ai_file = path
        label = self._w('ai_file_label')
        if label:
            label.text = name
            label.text_color = (0.95, 0.95, 0.97, 1)
        toast(f"Loaded: {name}")

    def start_ai_removal(self):
        if not self.ai_file:
            toast("Select an image first")
            return
        if platform != "android":
            toast("AI features require Android")
            return
        if not self.task_lock.acquire():
            toast("Please wait for current task to finish")
            return

        src = self.ai_file
        stem = Path(src).stem
        tmp_out = os.path.join(self.temp_dir, f"{stem}_nobg.png")

        def do_work(on_progress):
            from engine.ai_tools import remove_background
            
            result_holder = [None]
            error_holder = [None]
            done_event = __import__('threading').Event()
            
            def ai_complete(path):
                result_holder[0] = path
                done_event.set()
            
            def ai_error(msg):
                error_holder[0] = msg
                done_event.set()
            
            remove_background(
                src, tmp_out,
                on_progress=on_progress,
                on_complete=ai_complete,
                on_error=ai_error,
            )
            
            # If remove_background is synchronous (calls callbacks directly),
            # the event is already set. Otherwise wait.
            done_event.wait(timeout=120)
            
            if error_holder[0]:
                raise Exception(error_holder[0])
            
            if result_holder[0]:
                return save_file(result_holder[0], f"{stem}_nobg.png")
            
            # If we get here, check if output exists
            if os.path.exists(tmp_out):
                return save_file(tmp_out, f"{stem}_nobg.png")
            
            raise Exception("Background removal produced no output")

        def on_complete(result):
            self.task_lock.release()
            self._update_progress('ai_progress', 0)
            if result:
                self._update_status('ai_status', "✓ Background removed!")
                self._show_dialog("Success", f"Transparent PNG saved!\n\n{result}")
            else:
                self._update_status('ai_status', "Failed")

        def on_error(msg):
            self.task_lock.release()
            self._update_progress('ai_progress', 0)
            self._update_status('ai_status', f"✗ Error")
            self._show_dialog("Error", msg)

        def on_progress(pct, msg):
            self._update_progress('ai_progress', pct)
            self._update_status('ai_status', msg)

        self._update_status('ai_status', "Initializing AI...")
        BackgroundTask(target=do_work, on_progress=on_progress, on_complete=on_complete, on_error=on_error).start()

    # ==========================================================
    #  UI Helpers
    # ==========================================================

    def _update_progress(self, widget_id, value):
        w = self._w(widget_id)
        if w:
            w.value = value

    def _update_status(self, widget_id, text):
        w = self._w(widget_id)
        if w:
            w.text = text

    def _show_dialog(self, title, text):
        if self._dialog:
            try:
                self._dialog.dismiss()
            except:
                pass
        
        self._dialog = MDDialog(
            title=title,
            text=text,
            buttons=[
                MDFlatButton(
                    text="OK",
                    text_color=(0.55, 0.40, 1.0, 1),
                    on_release=lambda x: self._dialog.dismiss(),
                )
            ],
        )
        self._dialog.open()

    def on_stop(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
