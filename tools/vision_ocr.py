"""Optional on-device macOS Vision word boxes via PyObjC; no cloud service.

Uses the same Apple engine as macos_ocr.swift. PyObjC is optional and imported
only when this adapter is explicitly selected. Language correction stays off.
"""
from pathlib import Path
import re


def pixel_box(rect,width,height):
    x,y=rect.origin.x,rect.origin.y
    w,h=rect.size.width,rect.size.height
    left,top=x*width,(1-y-h)*height
    return [[left,top],[left+w*width,top],[left+w*width,top+h*height],[left,top+h*height]]


def recognize(path):
    import Vision
    from Foundation import NSURL
    from PIL import Image
    with Image.open(path) as image:width,height=image.size
    request=Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setRecognitionLanguages_(['en-US'])
    request.setUsesLanguageCorrection_(False)
    request.setUsesCPUOnly_(True)
    handler=Vision.VNImageRequestHandler.alloc().initWithURL_options_(NSURL.fileURLWithPath_(str(Path(path).resolve())),{})
    success,error=handler.performRequests_error_([request],None)
    if not success or request.results() is None:
        raise RuntimeError('On-device Vision OCR unavailable: '+str(error or 'no recognition result; check host resource permissions'))
    cells=[]
    for observation in request.results():
        candidates=observation.topCandidates_(1)
        if not candidates:continue
        candidate=candidates[0];text=candidate.string()
        for token in re.finditer(r'\S+',text):
            start=len(text[:token.start()].encode('utf-16-le'))//2
            length=len(token.group().encode('utf-16-le'))//2
            word,error=candidate.boundingBoxForRange_error_((start,length),None)
            if word is None:continue  # Never assign a whole-line box to a money cell.
            cells.append(dict(text=token.group(),confidence=float(candidate.confidence()),
                              box=pixel_box(word.boundingBox(),width,height)))
    return cells
