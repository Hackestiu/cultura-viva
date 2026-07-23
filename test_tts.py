from piper import PiperVoice
import wave

#set configuration paths for the models
TTS_MODEL_PATH = "./models/tts/en_US-lessac-medium.onnx"
OUTPUT_WAV = "output.wav"

voice = PiperVoice.load(TTS_MODEL_PATH)

with wave.open(OUTPUT_WAV, 'wb') as wav_file:
    voice.synthesize_wav('Hello, this is a test of the text to speech system running on the Arduino UNO Q.', wav_file)

print(f"Done. Generated {OUTPUT_WAV}")