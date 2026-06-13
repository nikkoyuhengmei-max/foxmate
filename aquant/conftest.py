import os
import sys

# Make `aqs` importable without an editable install (src layout).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
