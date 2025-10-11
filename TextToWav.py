# Import libraries
from gtts import gTTS
from pydub import AudioSegment

# Input text
text = "Hello! This is a test of converting text to a WAV audio file."

# Convert text → temporary MP3
tts = gTTS(text)
tts.save("/Users/lukegeel/Desktop/temp.mp3")

# Convert MP3 → WAV using pydub
audio = AudioSegment.from_mp3("/Users/lukegeel/Desktop/temp.mp3")
audio.export("/Users/lukegeel/Desktop/JNoutput.wav", format="wav")

print("✅ Saved output.wav successfully!")

# (Optional) Play the result
#from IPython.display import Audio
#Audio("/Users/lukegeel/Desktop/JNoutput.wav")
