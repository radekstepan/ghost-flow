import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav
import tempfile
import os

class AudioRecorder:
    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate
        self.recording = []
        self.is_recording = False
        self.stream = None

    def start(self):
        if self.is_recording:
            return
        self.recording = []
        self.is_recording = True
        # Start non-blocking stream
        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype='int16',
            callback=self._callback
        )
        self.stream.start()

    def _callback(self, indata, frames, time, status):
        if self.is_recording:
            self.recording.append(indata.copy())

    def stop(self) -> str:
        if not self.is_recording:
            return ""
        
        self.is_recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        if not self.recording:
            return ""

        # Concatenate all blocks
        audio_data = np.concatenate(self.recording, axis=0)
        
        # Save to temp file
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, "ghost_voice.wav")
        wav.write(file_path, self.sample_rate, audio_data)
        
        return file_path
