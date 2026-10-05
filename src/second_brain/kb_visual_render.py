"""Bounded local visual rendering. Sources are data, never executable HTML."""
import base64
import io
import math
import re
import subprocess
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

from defusedxml import ElementTree as SafeET

MAX_BYTES = 25 * 1024 * 1024
MAX_PIXELS = 8_000_000
MAX_ITEMS = 100
MAX_DIMENSION = 1600
MAX_PAGES = 20
SVG_TAGS = set("svg g defs title desc rect circle ellipse line polyline polygon path text tspan textPath marker clipPath mask pattern linearGradient radialGradient stop symbol use image style switch a".split())


def deny_fetch(*args, **kwargs):
    raise ValueError("SVG resource fetching is disabled")


def css_external(text):
    import tinycss2

    def unsafe(tokens):
        for token in tokens:
            if token.type == "at-keyword" and token.value.lower() == "import":
                return True
            if token.type == "url" and not token.value.strip().startswith("#"):
                return True
            if token.type == "function":
                if token.lower_name == "url":
                    value = tinycss2.serialize(token.arguments).strip().strip("\"'")
                    if not value.startswith("#"):
                        return True
                if unsafe(token.arguments):
                    return True
            if hasattr(token, "content") and token.content and unsafe(token.content):
                return True
        return False

    return unsafe(tinycss2.parse_component_value_list(text))


def sanitize_svg(data):
    root = SafeET.fromstring(data, forbid_dtd=True)
    if root.tag.rsplit("}", 1)[-1] != "svg":
        raise ValueError("Expected SVG root")
    changed = False
    count = 0
    stack = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        count += 1
        if count > 100_000 or depth > 100:
            raise ValueError("SVG structure limit exceeded")
        for child in list(node):
            child_tag = child.tag.rsplit("}", 1)[-1]
            image_href = child.attrib.get("href", child.attrib.get("{http://www.w3.org/1999/xlink}href", ""))
            if child_tag not in SVG_TAGS or (child_tag == "image" and not image_href.startswith("#")):
                node.remove(child)
                changed = True
            else:
                stack.append((child, depth + 1))
        for key, value in list(node.attrib.items()):
            local = key.rsplit("}", 1)[-1].lower()
            if local.startswith("on") or local in {"base", "src"} or (
                local == "href" and not value.startswith("#")
            ) or css_external(value):
                del node.attrib[key]
                changed = True
        if node.tag.rsplit("}", 1)[-1] == "style" and css_external(node.text or ""):
            node.text = ""
            changed = True
    view = root.attrib.get("viewBox", "").replace(",", " ").split()
    def dimension(key, fallback):
        value = root.attrib.get(key)
        if value is None and fallback is not None:
            return fallback
        match = re.fullmatch(r"([0-9]+(?:\.[0-9]*)?|\.[0-9]+)(px|pt|pc|mm|cm|in)?", value or "")
        if not match:
            raise ValueError("SVG needs a viewBox or supported absolute viewport dimensions")
        scale = {None: 1, "px": 1, "pt": 96 / 72, "pc": 16, "mm": 96 / 25.4, "cm": 96 / 2.54, "in": 96}[match[2]]
        return float(match[1]) * scale
    width = dimension("width", float(view[2]) if len(view) == 4 else None)
    height = dimension("height", float(view[3]) if len(view) == 4 else None)
    if not all(math.isfinite(x) and x > 0 for x in (width, height)):
        raise ValueError("Invalid SVG dimensions")
    ratio = min(MAX_DIMENSION / width, MAX_DIMENSION / height)
    size = (max(1, round(width * ratio)), max(1, round(height * ratio)))
    return ET.tostring(root), size, changed


class InertHTML(HTMLParser):
    """Find visible inline SVGs and data raster images without running a browser."""
    SUPPRESSED = {"script", "style", "template", "noscript", "head", "iframe", "object"}

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.suppressed = []
        self.svg = []
        self.depth = 0
        self.tags = []
        self.svg_count = 0
        self.svg_locator = None
        self.assets = []
        self.omitted = 0

    def handle_starttag(self, tag, attrs):
        if self.suppressed:
            if tag in self.SUPPRESSED:
                self.suppressed.append(tag)
            return
        if tag in self.SUPPRESSED:
            self.suppressed.append(tag)
            return
        if tag == "svg" or self.depth:
            if not self.depth:
                self.svg_count += 1
                self.svg_locator = f"HTML/svg[{self.svg_count}]@line[{self.getpos()[0]}]"
            self.depth += 1
            raw = self.get_starttag_text()
            self.tags.append(re.match(r"<\s*([^\s/>]+)", raw)[1])
            self.svg.append(raw)
        elif tag == "img":
            src = dict(attrs).get("src", "")
            match = re.fullmatch(r"data:image/(png|jpeg);base64,([A-Za-z0-9+/=\s]+)", src)
            if match:
                self.assets.append((f"HTML/img[{self.getpos()[0]}:{self.getpos()[1]}]", base64.b64decode(match[2], validate=False), "." + match[1]))
            else:
                self.omitted += 1

    def handle_startendtag(self, tag, attrs):
        if self.depth and not self.suppressed:
            self.svg.append(self.get_starttag_text())
        else:
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.suppressed:
            if tag == self.suppressed[-1]:
                self.suppressed.pop()
            return
        if self.depth:
            original_tag = self.tags.pop()
            self.svg.append(f"</{original_tag if original_tag.lower() == tag else tag}>")
            self.depth -= 1
            if not self.depth:
                self.assets.append((self.svg_locator, "".join(self.svg).encode(), ".svg"))
                self.svg = []

    def handle_data(self, data):
        if self.depth:
            self.svg.append(data)

    def handle_entityref(self, name):
        if self.depth:
            self.svg.append(f"&{name};")

    def handle_charref(self, name):
        if self.depth:
            self.svg.append(f"&#{name};")


class Renderer:
    def __init__(self, root, pdftoppm=None):
        self.root = Path(root)
        self.pdftoppm = pdftoppm
        self.items = []
        self.issues = []

    def gap(self, source_id, locator, code, detail):
        self.issues.append({"id": f"GAP-{len(self.issues) + 1:04}", "source_id": source_id,
                            "locator": locator, "code": code, "detail": detail})

    def image(self, source_id, locator, data, extension):
        from .kb_visual_review import sha
        if len(self.items) >= MAX_ITEMS:
            raise ValueError("Packet visual-item limit exceeded")
        item = {"id": f"V-{len(self.items) + 1:04}", "source_id": source_id, "locator": locator,
                "asset_sha256": sha(data), "status": "unavailable", "preview_path": None,
                "preview_sha256": None, "width": None, "height": None}
        self.items.append(item)
        try:
            if len(data) > MAX_BYTES:
                raise ValueError("Visual asset exceeds byte limit")
            if extension == ".svg":
                from cairosvg.surface import PNGSurface
                xml, size, changed = sanitize_svg(data)
                if changed:
                    self.gap(source_id, locator, "svg_restricted", "Unsupported/active elements or resource references were removed from the preview; compare the original separately.")
                data = PNGSurface.convert(bytestring=xml, unsafe=False, url_fetcher=deny_fetch,
                                          output_width=size[0], output_height=size[1])
            from PIL import Image
            with Image.open(io.BytesIO(data)) as image:
                if image.width * image.height > MAX_PIXELS:
                    raise ValueError("Image pixel limit exceeded")
                if getattr(image, "n_frames", 1) > 1:
                    self.gap(source_id, locator, "image_frames_omitted", "Only the first raster frame is shown.")
                image.load()
                preview = image.convert("RGBA")
                preview.info.clear()
                preview.thumbnail((MAX_DIMENSION, MAX_DIMENSION))
                out = io.BytesIO()
                preview.save(out, format="PNG")
                if out.tell() > 8 * 1024 * 1024:
                    raise ValueError("Preview byte limit exceeded")
                relative = f"previews/{item['id']}.png"
                (self.root / relative).write_bytes(out.getvalue())
                item.update(status="rendered", preview_path=relative, preview_sha256=sha(out.getvalue()),
                            width=preview.width, height=preview.height)
        except Exception as exc:
            self.gap(source_id, locator, "render_unavailable", f"{type(exc).__name__}: {str(exc)[:400]}")

    def source(self, source):
        sid, ext = source["id"], source["extension"]
        path = self.root / source["original_path"]
        data = path.read_bytes()
        if ext in {".svg", ".png", ".jpg", ".jpeg"}:
            self.image(sid, "original", data, ext)
        elif ext == ".html":
            parser = InertHTML()
            parser.feed(data.decode("utf-8", errors="strict"))
            if parser.depth:
                self.gap(sid, "HTML", "incomplete_svg", "An unclosed inline SVG could not be rendered.")
            for locator, asset, extension in parser.assets:
                self.image(sid, locator, asset, extension)
            self.gap(sid, "HTML", "html_layout_unavailable", "Only inline SVGs and embedded PNG/JPEG assets are shown; page layout, text, CSS and linked images are not rendered.")
            if parser.omitted:
                self.gap(sid, "HTML", "linked_images_unavailable", f"{parser.omitted} non-embedded images were not fetched.")
        elif ext in {".docx", ".xlsx", ".pptx"}:
            prefix = {".docx": "word/media/", ".xlsx": "xl/media/", ".pptx": "ppt/media/"}[ext]
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                members = archive.infolist()
                if len(members) > 10_000 or sum(m.file_size for m in members) > 64 * 1024 * 1024:
                    raise ValueError("Office ZIP expansion limit exceeded")
                if len({m.filename for m in members}) != len(members):
                    raise ValueError("Duplicate Office parts")
                for member in sorted(members, key=lambda m: m.filename):
                    if not member.filename.startswith(prefix) or member.is_dir():
                        continue
                    if member.file_size > MAX_BYTES:
                        self.gap(sid, member.filename, "asset_too_large", "Office media exceeds byte limit.")
                        continue
                    self.image(sid, "OOXML/" + member.filename, archive.read(member), Path(member.filename).suffix.lower())
            self.gap(sid, "OOXML", "office_layout_unavailable", "Embedded media only: placement, crops, overlays, text, shapes, charts, linked media and whole pages are unavailable. Supply a separately reviewed PDF export for page comparison.")
        elif ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data), strict=True)
            if reader.is_encrypted:
                raise ValueError("Encrypted PDFs are unavailable")
            count = len(reader.pages)
            if count == 0:
                self.gap(sid, "PDF", "empty_pdf", "PDF has no pages; no material visuals were compared.")
            if count > MAX_PAGES:
                self.gap(sid, "PDF", "pdf_pages_omitted", f"Only the first {MAX_PAGES} of {count} pages are included.")
            for number in range(1, min(count, MAX_PAGES) + 1):
                locator = f"PDF/page[{number}]"
                if not self.pdftoppm:
                    self.image(sid, locator, b"", ".png")
                    continue
                prefix = self.root / ".pdf-page"
                preview = prefix.with_suffix(".png")
                try:
                    subprocess.run([self.pdftoppm, "-f", str(number), "-l", str(number), "-singlefile", "-scale-to", str(MAX_DIMENSION), "-png", str(path), str(prefix)],
                                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
                    self.image(sid, locator, preview.read_bytes(), ".png")
                except (OSError, subprocess.SubprocessError) as exc:
                    self.image(sid, locator, b"", ".png")
                    self.gap(sid, locator, "pdf_renderer_failed", type(exc).__name__)
                finally:
                    preview.unlink(missing_ok=True)
        else:
            self.gap(sid, "original", "format_unavailable", f"No visual adapter for {ext}.")
