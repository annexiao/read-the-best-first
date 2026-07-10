#!/usr/bin/env python3
"""build_epub: assemble a valid EPUB3 from a manifest of ordered chapters.

Generalized from the Paul Graham collection builder (2026-07-08). Feed it a JSON
manifest describing parts + chapters (each chapter points at an .html/.txt/.md
source file); it extracts clean text and emits an epub whose spine follows the
manifest order exactly. Pair with epub2m4b.py to turn the result into an audiobook.

Manifest shape (parts optional; a flat "chapters" list at top level also works):

{
  "title": "Book Title",
  "author": "Author Name",
  "language": "en",
  "intro": "One paragraph shown on the title page (plain text).",
  "parts": [
    {"name": "Part I - ...", "blurb": "why these come first",
     "chapters": [{"title": "Essay", "source": "/abs/path/essay.html"}]}
  ]
}

Usage:
  .venv/bin/python build_epub.py manifest.json --out ~/Downloads/book.epub

Hard-won rules baked in:
- EVERY string interpolated into XHTML goes through esc(); an unescaped '&' in a
  title-page sentence once produced an epub Apple Books refused to open.
- mimetype must be the first zip entry, STORED (uncompressed).
- .html sources are cleaned with trafilatura (favor_recall=True); .txt/.md are
  used as-is, blank-line-separated paragraphs.
- Sources yielding under 20 chars are dropped (covers, junk pages).
"""
import argparse
import html as htmllib
import json
import re
import zipfile
from pathlib import Path

XHTML = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>{title}</title>
<style>
body {{ font-family: Georgia, serif; line-height: 1.55; margin: 5%; }}
h1 {{ font-size: 1.5em; line-height: 1.2; }}
p.meta {{ color: #777; font-style: italic; }}
</style></head>
<body>{body}</body></html>
"""


def esc(s):
    return htmllib.escape(str(s), quote=True)


def source_to_paragraphs(path, base_dir=None):
    p = Path(path).expanduser()
    if not p.is_absolute() and base_dir is not None:
        p = Path(base_dir) / p  # relative sources resolve against the manifest's dir
    raw = p.read_bytes()
    if p.suffix.lower() in (".html", ".htm", ".xhtml"):
        import trafilatura
        text = trafilatura.extract(raw, include_comments=False,
                                   include_links=False, favor_recall=True) or ""
        paras = [x.strip() for x in text.split("\n") if x.strip()]
    else:  # .txt / .md: blank-line paragraphs
        text = raw.decode("utf-8", errors="replace")
        paras = [re.sub(r"\s+", " ", x).strip()
                 for x in re.split(r"\n\s*\n", text) if x.strip()]
    return paras


def chapter_doc(title, paras):
    if paras and paras[0].lower() == title.lower():
        paras = paras[1:]
    body = "\n".join(f"<p>{esc(x)}</p>" for x in paras)
    return XHTML.format(title=esc(title), body=f"<h1>{esc(title)}</h1>\n{body}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    manifest_path = Path(args.manifest).expanduser()
    m = json.loads(manifest_path.read_text())
    base_dir = manifest_path.parent
    title = m["title"]
    author = m.get("author", "Unknown")
    lang = m.get("language", "en")
    parts = m.get("parts") or [{"name": None, "blurb": None,
                                "chapters": m.get("chapters", [])}]

    docs = []  # (id, title, xhtml, is_part)
    intro = f"<h1>{esc(title)}</h1>"
    if m.get("intro"):
        intro += f'<p class="meta">{esc(m["intro"])}</p>'
    docs.append(("titlepage", title, XHTML.format(title=esc(title), body=intro), False))

    skipped = []
    n = 0
    for pi, part in enumerate(parts, 1):
        if part.get("name"):
            body = f'<h1>{esc(part["name"])}</h1>'
            if part.get("blurb"):
                body += f'<p class="meta">{esc(part["blurb"])}</p>'
            docs.append((f"part{pi}", part["name"],
                         XHTML.format(title=esc(part["name"]), body=body), True))
        for ch in part["chapters"]:
            paras = source_to_paragraphs(ch["source"], base_dir)
            if sum(len(x) for x in paras) < 20:
                skipped.append(ch["title"])
                continue
            n += 1
            docs.append((f"c{n:04d}", ch["title"], chapter_doc(ch["title"], paras), False))

    manifest_items, spine, nav_lis, ncx = [], [], [], []
    open_part = False
    for i, (did, dtitle, _, is_part) in enumerate(docs, 1):
        manifest_items.append(
            f'<item id="{did}" href="{did}.xhtml" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="{did}"/>')
        if is_part:
            if open_part:
                nav_lis.append("</ol></li>")
            nav_lis.append(f'<li><a href="{did}.xhtml">{esc(dtitle)}</a><ol>')
            open_part = True
        else:
            nav_lis.append(f'<li><a href="{did}.xhtml">{esc(dtitle)}</a></li>')
        ncx.append(f'<navPoint id="np{i}" playOrder="{i}"><navLabel><text>{esc(dtitle)}'
                   f'</text></navLabel><content src="{did}.xhtml"/></navPoint>')
    if open_part:
        nav_lis.append("</ol></li>")

    uid = "urn:uuid:build-epub-" + re.sub(r"[^a-z0-9]+", "-", title.lower())[:40]
    nav = XHTML.format(title="Contents", body=(
        '<nav epub:type="toc" id="toc"><h1>Contents</h1><ol>'
        + "\n".join(nav_lis) + "</ol></nav>"))
    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="uid">{esc(uid)}</dc:identifier>
<dc:title>{esc(title)}</dc:title>
<dc:creator>{esc(author)}</dc:creator>
<dc:language>{esc(lang)}</dc:language>
<meta property="dcterms:modified">2026-01-01T00:00:00Z</meta>
</metadata>
<manifest>
<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
{chr(10).join(manifest_items)}
</manifest>
<spine toc="ncx">
{chr(10).join(spine)}
</spine>
</package>"""
    ncx_doc = f"""<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
<head><meta name="dtb:uid" content="{esc(uid)}"/></head>
<docTitle><text>{esc(title)}</text></docTitle>
<navMap>{chr(10).join(ncx)}</navMap></ncx>"""
    container = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""

    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container)
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/nav.xhtml", nav)
        z.writestr("OEBPS/toc.ncx", ncx_doc)
        for did, _, doc, _ in docs:
            z.writestr(f"OEBPS/{did}.xhtml", doc)
    msg = f"wrote {out} ({n} chapters, {len(docs)} docs)"
    if skipped:
        msg += f"; skipped empty: {skipped}"
    print(msg)


if __name__ == "__main__":
    main()
