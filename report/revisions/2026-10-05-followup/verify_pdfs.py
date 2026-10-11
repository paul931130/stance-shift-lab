from pathlib import Path
import hashlib
import json
import re
import fitz
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
QA = Path(__file__).resolve().parent / 'qa'
QA.mkdir(exist_ok=True)
checks = {}
for stem in ('stance-shift-ssrn', 'application'):
    pdf = ROOT / (stem + '.pdf')
    doc = fitz.open(pdf)
    log = (ROOT / (stem + '.log')).read_text(encoding='utf-8', errors='replace')
    blg = (ROOT / (stem + '.blg')).read_text(encoding='utf-8', errors='replace')
    issues = re.findall(r'^.*(?:Overfull|undefined|Missing character|LaTeX Error|Warning--).*$'
                        , log + '\n' + blg, re.M | re.I)
    texts = [page.get_text() for page in doc]
    for start in range(0, len(doc), 12):
        sheet = Image.new('RGB', (900, 1280), 'white')
        draw = ImageDraw.Draw(sheet)
        for offset, index in enumerate(range(start, min(start + 12, len(doc)))):
            pix = doc[index].get_pixmap(matrix=fitz.Matrix(.6, .6), alpha=False)
            im = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
            im.thumbnail((286, 292))
            x, y = (offset % 3) * 300, (offset // 3) * 320
            sheet.paste(im, (x + (300-im.width)//2, y + 24))
            draw.text((x + 8, y + 5), f'{stem}: {index+1}', fill='black')
        sheet.save(QA / f'{stem}-contact-{start+1}.png')
    key_pages = []
    for index, content in enumerate(texts):
        if any(term in content for term in ('composite-protocol', '6.3', '0.853', 'T −1', 'arXiv preprint')):
            key_pages.append(index + 1)
            doc[index].get_pixmap(matrix=fitz.Matrix(1.35, 1.35), alpha=False).save(
                QA / f'{stem}-page-{index+1}.png')
    (QA / f'{stem}-text.txt').write_text('\n\n'.join(texts), encoding='utf-8')
    checks[stem] = {'pages': len(doc), 'bytes': pdf.stat().st_size,
                    'sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(),
                    'log_issues': issues,
                    'bibtex_warning_count': blg.count('Warning--'),
                    'key_pages': key_pages}
    doc.close()
(QA / 'verification.json').write_text(json.dumps(checks, indent=2), encoding='utf-8')
print(json.dumps(checks, indent=2))
