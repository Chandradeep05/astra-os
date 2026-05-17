import os
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any

try:
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore
except ImportError:
    pytesseract = None
    Image = None

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)


def _sync_ocr(image_path: str) -> str:
    """CPU-bound OCR — runs in thread to avoid blocking the event loop."""
    image = Image.open(image_path)
    return pytesseract.image_to_string(image)


async def run_vision_ocr(image_path: str, **kwargs) -> Dict[str, Any]:
    """
    Extracts text and structured data from an image using Optical Character Recognition (OCR).
    
    Args:
        image_path (str): The absolute or relative path to the image file (png, jpg, jpeg).
        
    Returns:
        Dict: Contains the extracted text or an error message.
    """
    if pytesseract is None or Image is None:
        return {"error": "Multi-Modal libraries (pytesseract, Pillow) are not installed or configured."}

    if not os.path.exists(image_path):
        return {"error": f"Image file not found at path: {image_path}"}

    try:
        loop = asyncio.get_running_loop()
        extracted_text = await loop.run_in_executor(_executor, _sync_ocr, image_path)
        
        return {
            "status": "success",
            "image_path": image_path,
            "extracted_text": extracted_text.strip()
        }
    except Exception as e:
        logger.error(f"OCR Execution failed on {image_path}: {e}")
        return {"error": f"Failed to process image: {str(e)}"}
