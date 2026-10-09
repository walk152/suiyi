"""Download the fixed free English OCR weights; never called during inference."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from download_models import download_verified
from ocr_english import MODEL_NAME,MODEL_SHA256,MODEL_BYTES,MODEL_URL

if __name__=='__main__':
    target=Path(__file__).resolve().parents[1]/'ocr_models'/MODEL_NAME
    download_verified(MODEL_URL,target,{'bytes':MODEL_BYTES,'sha256':MODEL_SHA256})
    print('English OCR model verified: '+MODEL_NAME)
