from unittest.mock import patch
from src.utils.image_utils import _find_chromium_binary

def test_find_chromium_binary_macos():
    macos_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    with patch('shutil.which', return_value=None), \
         patch('os.path.exists', side_effect=lambda p: p == macos_path):
        assert _find_chromium_binary() == macos_path
