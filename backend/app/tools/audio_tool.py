import os
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any

try:
    import speech_recognition as sr  # type: ignore
except ImportError:
    sr = None

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)


def _sync_transcribe(audio_path: str) -> str:
    """CPU/IO-bound transcription — runs in thread to avoid blocking the event loop."""
    recognizer = sr.Recognizer()
    with sr.AudioFile(audio_path) as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.2)
        audio_data = recognizer.record(source)
        return recognizer.recognize_google(audio_data)


async def run_audio_transcription(audio_path: str, **kwargs) -> Dict[str, Any]:
    """
    Extracts text from an audio file (wav/mp3) using local or fallback Speech Recognition.
    
    Args:
        audio_path (str): The absolute or relative path to the audio file.
        
    Returns:
        Dict: Contains the transcribed text or an error message.
    """
    if sr is None:
        return {"error": "Multi-Modal libraries (SpeechRecognition) are not installed."}

    if not os.path.exists(audio_path):
        return {"error": f"Audio file not found at path: {audio_path}"}

    try:
        loop = asyncio.get_running_loop()
        transcribed_text = await loop.run_in_executor(_executor, _sync_transcribe, audio_path)
        
        return {
            "status": "success",
            "audio_path": audio_path,
            "transcription": transcribed_text
        }
    except sr.UnknownValueError:
        return {"error": "Audio was indistinguishable or blank. Could not transcribe."}
    except sr.RequestError as e:
        return {"error": f"API unavailable or network issue during transcription: {e}"}
    except Exception as e:
        logger.error(f"Audio transcription failed on {audio_path}: {e}")
        return {"error": f"Failed to process audio: {str(e)}"}
