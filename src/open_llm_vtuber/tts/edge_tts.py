import sys
import os
import re

import edge_tts
from loguru import logger
from .tts_interface import TTSInterface

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)


# Check out doc at https://github.com/rany2/edge-tts
# Use `edge-tts --list-voices` to list all available voices


CJK_RE = re.compile(r"[㐀-鿿豈-﫿]")
# Characters that are common in written Cantonese and rare in Mandarin
CANTONESE_RE = re.compile(r"[係唔嘅咗佢哋冇嚟啲喺嗰乜嘢囉喎㗎啱畀睇攞咪嘞噉嚿]")


def detect_lang(text: str) -> str:
    """Return 'yue', 'zh' or 'en' for a sentence."""
    if not CJK_RE.search(text):
        return "en"
    if CANTONESE_RE.search(text):
        return "yue"
    return "zh"


class TTSEngine(TTSInterface):
    def __init__(self, voice="en-US-AvaMultilingualNeural", voice_zh=None, voice_yue=None):
        self.voice = voice
        # Per-language voices: native pronunciation for each language
        self.voices = {"en": voice, "zh": voice_zh or voice, "yue": voice_yue or voice_zh or voice}

        self.temp_audio_file = "temp"
        self.file_extension = "mp3"
        self.new_audio_dir = "cache"

        if not os.path.exists(self.new_audio_dir):
            os.makedirs(self.new_audio_dir)

    def generate_audio(self, text, file_name_no_ext=None):
        """
        Generate speech audio file using TTS.
        text: str
            the text to speak
        file_name_no_ext: str
            name of the file without extension


        Returns:
        str: the path to the generated audio file

        """
        file_name = self.generate_cache_file_name(file_name_no_ext, self.file_extension)

        try:
            voice = self.voices[detect_lang(text)]
            communicate = edge_tts.Communicate(text, voice)
            communicate.save_sync(file_name)
        except Exception as e:
            logger.critical(f"\nError: edge-tts unable to generate audio: {e}")
            logger.critical("It's possible that edge-tts is blocked in your region.")
            return None

        return file_name


# en-US-AvaMultilingualNeural
# en-US-EmmaMultilingualNeural
# en-US-JennyNeural
