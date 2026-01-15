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
        print("DEBUG: Audio Stream Starting...")
        # Start non-blocking stream
        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype='int16',
            callback=self._callback
        )
        self.stream.start()

    def _callback(self, indata, frames, time, status):
        if status:
            print(f"DEBUG: Audio Status: {status}")
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
            print("DEBUG: Audio Stream Stopped")

        if not self.recording:
            print("DEBUG: No recording data captured.")
            return ""

        # Concatenate all blocks
        audio_data = np.concatenate(self.recording, axis=0)
        
        # Check volume levels (to see if Mic is actually working)
        max_amp = np.max(np.abs(audio_data))
        print(f"DEBUG: Recording finished. Frames: {len(audio_data)}, Max Amplitude: {max_amp}")
        
        if max_amp < 100: # Very low threshold, likely silence or mic permission issue
            print("WARNING: Audio appears silent. Check Microphone permissions.")
            # We return None/Empty to indicate failure to capture meaningful audio
            # But let's return the file anyway so Whisper can try (it handles silence)
            # or return empty to fail fast.
            # Returning empty string will trigger "No Audio" in main.
            return "" 
        
        # Save to temp file
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, "ghost_voice.wav")
        wav.write(file_path, self.sample_rate, audio_data)
        
        return file_path
