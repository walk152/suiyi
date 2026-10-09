"""Optional compact English recognizer for low-confidence or space-less lines."""
from pathlib import Path
import re

from runtime_paths import BUNDLE_ROOT

MODEL_NAME='en_PP-OCRv4_rec_mobile.onnx'
MODEL_SHA256='e8770c967605983d1570cdf5352041dfb68fa0c21664f49f47b155abd3e0e318'
MODEL_BYTES=7653044
MODEL_URL='https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv4/rec/'+MODEL_NAME


def refine_english(ocr, image, rows):
    if not rows:
        return rows
    chosen=[]
    for i,row in enumerate(rows):
        text=str(row[1])
        letters=len(re.findall('[A-Za-z]',text))
        if (letters>=4 and not re.search(r'[\u3400-\u9fff]',text)
                and (float(row[2])<.8 or (letters>=12 and len(text.split())<=2))):
            chosen.append(i)
    if not chosen:
        return rows
    if not hasattr(ocr,'get_crop_img_list'):
        return rows  # Small synthetic OCR adapters need no additional model.
    if not hasattr(ocr,'_suiyi_english_recognizer'):
        path=BUNDLE_ROOT/'ocr_models'/MODEL_NAME
        if not path.is_file():
            ocr._suiyi_english_recognizer=None
        else:
            import hashlib
            if path.stat().st_size!=MODEL_BYTES or hashlib.sha256(path.read_bytes()).hexdigest()!=MODEL_SHA256:
                raise ValueError('英文文字模型校验失败，请重新安装完整公开版。')
            from rapidocr_onnxruntime.ch_ppocr_rec import TextRecognizer
            config=dict(model_path=str(path),intra_op_num_threads=2,inter_op_num_threads=1,
                        use_cuda=False,use_dml=False,rec_img_shape=[3,48,320],rec_batch_num=6)
            ocr._suiyi_english_recognizer=TextRecognizer(config)
    recognizer=ocr._suiyi_english_recognizer
    if recognizer is None:
        return rows
    import numpy as np
    crops=ocr.get_crop_img_list(image,[np.asarray(rows[i][0],dtype='float32') for i in chosen])
    refined,_=recognizer(crops)
    output=[list(row) for row in rows]
    for i,(text,score,*_) in zip(chosen,refined):
        before=re.sub(r'\s+','',str(rows[i][1]))
        after=re.sub(r'\s+','',text)
        if score>=max(.55,float(rows[i][2])-.18) and .55<=len(after)/max(1,len(before))<=1.6:
            output[i][1:3]=[text,float(score)]
    return output
