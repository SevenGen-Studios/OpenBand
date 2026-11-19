"""Losslessly pack public source responses; original response hashes remain valid."""
import gzip,re
from tools.bc_sources import CACHE

def pack():
 before=after=count=0
 for p in CACHE.iterdir():
  if not p.is_file():continue
  if not(re.fullmatch(r'[0-9a-f]{64}\.html',p.name) or p.name in ('bc-boundaries-source.json','bc-embedded.json','bcafn-embedded.json')):continue
  raw=p.read_bytes();compressed=gzip.compress(raw,compresslevel=9,mtime=0)
  if gzip.decompress(compressed)!=raw:raise ValueError('Compression round-trip failed')
  target=p.with_suffix(p.suffix+'.gz');target.write_bytes(compressed);p.unlink();before+=len(raw);after+=len(compressed);count+=1
 print('Losslessly packed',count,'responses:',before,'->',after,'bytes')
if __name__=='__main__':pack()
