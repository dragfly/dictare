#!/usr/bin/env python3
"""Test microphone recording."""
import sounddevice as sd
import soundfile as sf
import numpy as np

print("Registrando 5 secondi a 16kHz... PARLA ORA!")
audio = sd.rec(int(5 * 16000), samplerate=16000, channels=1, dtype="float32")
sd.wait()

sf.write("/tmp/test_mic.wav", audio, 16000)

print(f"Max level: {np.abs(audio).max():.4f}")
print("Ascolta con: aplay /tmp/test_mic.wav")
