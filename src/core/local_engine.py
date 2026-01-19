import numpy as np
try:
    import sherpa_onnx
except ImportError:
    sherpa_onnx = None

SAMPLE_RATE = 16000

class LocalParakeetEngine:
    def __init__(self, model_paths):
        if not sherpa_onnx:
            raise ImportError("sherpa-onnx is not installed. Run: pip install sherpa-onnx")

        self.recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
            tokens=model_paths["tokens"],
            encoder=model_paths["encoder"],
            decoder=model_paths["decoder"],
            joiner=model_paths["joiner"],
            num_threads=4,
            sample_rate=SAMPLE_RATE,
            feature_dim=80,
            decoding_method="greedy_search",
            provider="cpu",
            model_type="nemo_transducer",
        )
        self._audio_buffer = []
        self._last_text = ""

    def start_stream(self):
        """Resets the buffer for a new utterance."""
        self._audio_buffer = []
        self._last_text = ""

    def process_audio(self, pcm_bytes: bytes) -> str:
        """
        Buffers Int16 PCM bytes. Returns empty string since offline model
        transcribes only at the end.
        """
        if not self._audio_buffer:
            self._audio_buffer = []

        # Convert int16 bytes to float32 array normalized to [-1, 1]
        samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        self._audio_buffer.append(samples)
        
        return ""  # Offline model doesn't provide interim results

    def finalize_stream(self) -> str:
        """Transcribes all buffered audio and returns final text."""
        if not self._audio_buffer:
            return self._last_text
        
        # Concatenate all buffered audio
        all_samples = np.concatenate(self._audio_buffer)
        
        # Create stream and transcribe
        stream = self.recognizer.create_stream()
        stream.accept_waveform(SAMPLE_RATE, all_samples)
        self.recognizer.decode_stream(stream)
        
        text = stream.result.text.strip()
        self._last_text = text
        return text

    def stop_stream(self):
        """Finalizes and cleans up the stream."""
        final_text = self.finalize_stream()
        self._audio_buffer = []
        return final_text
