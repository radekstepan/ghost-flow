import os
import urllib.request
from PyQt6.QtCore import QObject, pyqtSignal

MODEL_DIR = os.path.expanduser("~/.ghostflow_models/parakeet-tdt-0.6b-v3")
BASE_URL = "https://huggingface.co/csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8/resolve/main/"

FILES = [
    "tokens.txt",
    "encoder.int8.onnx",
    "decoder.int8.onnx",
    "joiner.int8.onnx"
]

MIN_FILE_SIZES = {
    "tokens.txt": 1000,
    "encoder.int8.onnx": 100_000_000,
    "decoder.int8.onnx": 1_000_000,
    "joiner.int8.onnx": 1_000_000,
}

class ModelDownloader(QObject):
    progress_update = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def run(self):
        if not os.path.exists(MODEL_DIR):
            try:
                os.makedirs(MODEL_DIR)
            except Exception as e:
                self.finished.emit(False, f"Failed to create directory: {e}")
                return

        total_files = len(FILES)
        for index, filename in enumerate(FILES):
            path = os.path.join(MODEL_DIR, filename)
            min_size = MIN_FILE_SIZES.get(filename, 1000)
            
            if os.path.exists(path) and os.path.getsize(path) >= min_size:
                continue

            url = BASE_URL + filename
            self.progress_update.emit(f"Downloading {index + 1}/{total_files}: {filename}")
            
            try:
                urllib.request.urlretrieve(url, path)
                if os.path.getsize(path) < min_size:
                    os.remove(path)
                    self.finished.emit(False, f"Downloaded file {filename} is too small (corrupted?)")
                    return
            except Exception as e:
                self.finished.emit(False, f"Download failed for {filename}: {e}")
                return

        self.finished.emit(True, "")

class ModelManager:
    @staticmethod
    def get_model_paths():
        return {
            "tokens": os.path.join(MODEL_DIR, "tokens.txt"),
            "encoder": os.path.join(MODEL_DIR, "encoder.int8.onnx"),
            "decoder": os.path.join(MODEL_DIR, "decoder.int8.onnx"),
            "joiner": os.path.join(MODEL_DIR, "joiner.int8.onnx")
        }

    @staticmethod
    def is_model_ready():
        for filename in FILES:
            path = os.path.join(MODEL_DIR, filename)
            min_size = MIN_FILE_SIZES.get(filename, 1000)
            if not os.path.exists(path) or os.path.getsize(path) < min_size:
                return False
        return True
