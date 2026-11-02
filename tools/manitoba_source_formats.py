"""Recognize official DOCX responses mislabeled as PDF without executing content."""
import hashlib
import io
import zipfile
from pathlib import Path
from tools import ingest_alberta as engine
ROOT=Path(__file__).resolve().parents[1]
SHARED_DOWNLOAD=engine.download

def is_docx(payload):
    if not payload.startswith(b'PK\x03\x04'):return False
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            entries=archive.infolist()
            return len(entries)<1000 and sum(e.file_size for e in entries)<45*1024*1024 and {'[Content_Types].xml','word/document.xml'}.issubset(archive.namelist())
    except (zipfile.BadZipFile,ValueError):return False

def download(url,refresh=False):
    key=hashlib.sha256(engine.canonical_url(url).encode()).hexdigest()
    cached=engine.CACHE/(key+'.docx')
    if cached.exists() and not refresh:
        payload=cached.read_bytes()
        if is_docx(payload):return payload
    payload=SHARED_DOWNLOAD(url,refresh)
    if is_docx(payload):
        engine.CACHE.mkdir(parents=True,exist_ok=True);cached.write_bytes(payload)
    return payload

def parse_non_pdf(band,filing,payload):
    if not is_docx(payload):raise ValueError('Official source returned neither a PDF nor a recognized DOCX')
    digest=hashlib.sha256(payload).hexdigest()
    update={'parserRevision':engine.PARSER_REVISION,'sha256':digest,'byteSize':len(payload),'httpStatus':200,'sourceFormat':'docx','lastChecked':engine.now(),'verificationStatus':'source_retrieved','parse_status':'manual_review','manual_review_required':True,'people':[],'documentChecks':{'identityAndYearConfirmed':False},'warnings':['The official link returns a DOCX containing scan images despite its PDF content-type label. Format-specific source review is required.']}
    source=ROOT/'public/disclosure-sources'/f"{band['id']}-{filing['year']}-{digest[:12]}.docx"
    source.parent.mkdir(parents=True,exist_ok=True);source.write_bytes(payload)
    update['originalSourceFile']='/'+source.relative_to(ROOT).as_posix()
    reviewed=engine.reviewed_remuneration(band,filing,digest)
    if reviewed:
        update.update(reviewed)
        update.update(verificationStatus='automated_validated',documentChecks={'identityAndYearConfirmed':True,'method':'Complete hash-bound original DOCX scan review'},ocrStatus='not_required_reviewed_source',extractionMethod='Complete source schedule visually reviewed; both original embedded page images inspected')
    return update
