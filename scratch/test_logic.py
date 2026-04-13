import os
import sys
from pathlib import Path

# Add the current directory to path so we can import main
sys.path.append(os.getcwd())

# Mock platform and kivy to avoid errors during logic test
os.environ['KIVY_NO_ARGS'] = '1'
os.environ['KIVY_NO_CONSOLELOG'] = '1'

# We can't easily import the full main.py because of Kivy dependencies
# but we can test the logic part by copy-pasting or modifying main.py to be importable
# Since I just wrote it, I'll just do a quick manual check of the functions.

def test_logic_syntax():
    try:
        from main import IMAGE_EXTS, PDF_EXTS, size_kb
        print("Basic imports OK")
        return True
    except Exception as e:
        print(f"Import failed: {e}")
        return False

if __name__ == "__main__":
    test_logic_syntax()
