import os
import base64
import contextlib
import importlib.util
import io
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from http.client import InvalidURL
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, quote_plus, urlsplit, urlunsplit
from urllib.request import urlretrieve
from textwrap import wrap

APP_VERSION_MAJOR = 0
APP_VERSION_MINOR = 1
APP_VERSION_PATCH_BASE = 0
APP_VERSION_FALLBACK = f"{APP_VERSION_MAJOR}.{APP_VERSION_MINOR}.{APP_VERSION_PATCH_BASE}"
LOG_FILE_NAME = "error.log"


def get_app_version():
    try:
        base_path = Path(__file__).resolve().parent
        if not (base_path / ".git").exists():
            return APP_VERSION_FALLBACK

        commit_count = subprocess.check_output(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=base_path,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        patch = APP_VERSION_PATCH_BASE + int(commit_count)
        return f"{APP_VERSION_MAJOR}.{APP_VERSION_MINOR}.{patch}"
    except Exception:
        return APP_VERSION_FALLBACK


def get_log_file_path():
    return Path(__file__).resolve().parent / LOG_FILE_NAME


def log_to_file(message, level="INFO"):
    try:
        log_path = get_log_file_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"[{timestamp}] [{level}] {message}\n")
    except Exception:
        pass

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = None
    ImageDraw = None
    ImageFont = None


def _is_module_available(module_name):
    return importlib.util.find_spec(module_name) is not None


def _install_package(package_name):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])


def ensure_dependencies_installed():
    required_modules = {
        "crewai": "crewai",
        "reportlab": "reportlab",
        "google.genai": "google-genai",
    }

    for module_name, package_name in required_modules.items():
        if not _is_module_available(module_name):
            _install_package(package_name)

    if not (_is_module_available("PySide6") or _is_module_available("PyQt5")):
        _install_package("PySide6")


ensure_dependencies_installed()

from crewai import Agent, Task, Crew, Process, LLM
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None

try:
    from PySide6.QtCore import QObject, QThread, Signal
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QFormLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except ImportError:
    from PyQt5.QtCore import QObject, QThread, pyqtSignal as Signal
    from PyQt5.QtGui import QIcon
    from PyQt5.QtWidgets import (
        QApplication,
        QCheckBox,
        QFormLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )


def export_report_to_pdf(report_text, output_dir="reports", api_key=None, status_callback=None, generate_images=True):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    images_path = output_path / "images"
    images_path.mkdir(parents=True, exist_ok=True)

    report_title = "Gruene Themen Report"
    report_subtitle = "Ortsverband Markdorf und Umland"
    created_at = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_slug = re.sub(r"[^a-z0-9]+", "_", report_title.lower()).strip("_") or "gruene_report"
    report_basename = f"{report_slug}_{timestamp}"
    pdf_path = output_path / f"{report_basename}.pdf"
    md_path = output_path / f"{report_basename}.md"

    pdf = canvas.Canvas(str(pdf_path), pagesize=A4)
    page_width, page_height = A4
    left_margin = 42
    right_margin = 42
    top_margin = page_height - 120
    bottom_margin = 52
    content_width = page_width - left_margin - right_margin

    page_number = 1
    y = top_margin
    temp_image_paths = []
    image_cache = {}
    saved_report_images = {}
    image_counter = 0

    def save_persistent_image(source_path, section_index=None):
        nonlocal image_counter
        if not source_path:
            return None

        source_path = Path(source_path)
        if not source_path.exists():
            return None

        key = str(source_path.resolve())
        if key in saved_report_images:
            return saved_report_images[key]

        image_counter += 1
        suffix = source_path.suffix.lower() or ".png"
        section_tag = f"section{section_index + 1}_" if section_index is not None else ""
        target_filename = f"{report_basename}_{section_tag}image_{image_counter:02d}{suffix}"
        target_path = images_path / target_filename

        if source_path.resolve() == target_path.resolve():
            saved_report_images[key] = target_path
            return target_path

        try:
            shutil.copy2(str(source_path), str(target_path))
        except Exception:
            try:
                target_path.write_bytes(source_path.read_bytes())
            except Exception:
                return None

        saved_report_images[key] = target_path
        return target_path

    def find_local_layout_images():
        image_dir = Path(__file__).resolve().parent / "assets"
        if not image_dir.exists():
            return []
        images = []
        for pattern in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
            images.extend(sorted(image_dir.glob(pattern)))
        return images

    def extract_image_signal(line):
        text = line.strip()
        if not text:
            return None

        lower_text = text.lower()
        compact = lower_text.replace("_", "").replace(" ", "")

        if compact.startswith("bildurl:"):
            return {"type": "url", "value": text.split(":", 1)[1].strip()}
        if compact.startswith("bildhinweis:"):
            return {"type": "hint", "value": text.split(":", 1)[1].strip()}
        if compact.startswith("bildprompt:"):
            return {"type": "prompt", "value": text.split(":", 1)[1].strip()}

        if "![](http" in lower_text or "![" in lower_text:
            start = text.find("(")
            end = text.find(")", start + 1)
            if start != -1 and end != -1:
                return {"type": "url", "value": text[start + 1 : end].strip()}

        if lower_text.startswith("http://") or lower_text.startswith("https://"):
            return {"type": "url", "value": text}

        return None

    def looks_like_heading(line):
        text = line.strip()
        if not text:
            return False
        if text.startswith(("#", "##", "###")):
            return True
        if text.lower().startswith("ueberschrift:"):
            return True
        if len(text) <= 70 and text.endswith(":"):
            return True
        return False

    def normalize_heading(line):
        text = line.strip().lstrip("#").strip()
        if ":" in text and text.lower().startswith("ueberschrift"):
            text = text.split(":", 1)[1].strip()
        return text.rstrip(":").strip()

    def simplify_markdown_inline(text):
        value = str(text)
        value = value.replace("\uFE0F", "")

        checkbox_patterns = [
            (r"(?i)\[x\]", "__CB_CHECKED__ "),
            (r"\[ \]", "__CB_OPEN__ "),
            (r"☑", "__CB_CHECKED__ "),
            (r"✅", "__CB_CHECKED__ "),
            (r"✔", "__CB_CHECKED__ "),
            (r"☐", "__CB_OPEN__ "),
            (r"❌", "__CB_OPEN__ "),
        ]
        for pattern, replacement in checkbox_patterns:
            value = re.sub(pattern, replacement, value)

        emoji_replacements = {
            "😀": "[Smile]",
            "😄": "[Smile]",
            "😊": "[Freude]",
            "😉": "[Hinweis]",
            "👍": "[Daumen hoch]",
            "👏": "[Applaus]",
            "🙏": "[Danke]",
            "🔥": "[Trend]",
            "🌱": "[Umwelt]",
            "🌍": "[Welt]",
            "🌳": "🌳",
            "🚲": "[Fahrrad]",
            "🚍": "[Bus]",
            "⚡": "[Energie]",
            "💡": "[Idee]",
            "📢": "[Aufruf]",
            "📍": "[Ort]",
            "🗳": "[Demokratie]",
            "✅": "[OK]",
            "❗": "[Wichtig]",
            "❓": "[Frage]",
        }
        for emoji, replacement in emoji_replacements.items():
            value = value.replace(emoji, replacement)

        # Entfernt verbleibende Unicode-Symbole außerhalb des Latein-1-Bereichs,
        # damit ReportLab mit Standardfonts keine Leerstellen zeigt.
        allowed_unicode = {"🌳"}
        value = "".join(ch if (ord(ch) <= 255 or ch in allowed_unicode) else " " for ch in value)
        value = re.sub(r"\s{2,}", " ", value).strip()

        value = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r"\1", value)
        value = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", value)
        value = re.sub(r"`([^`]+)`", r"\1", value)
        value = re.sub(r"\*\*([^*]+)\*\*", r"\1", value)
        value = re.sub(r"__([^_]+)__", r"\1", value)
        value = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", value)
        value = re.sub(r"(?<!_)_([^_]+)_(?!_)", r"\1", value)
        return value.strip()

    def markdown_to_render_lines(body_text):
        lines_out = []
        in_code_block = False

        for raw_line in str(body_text).split("\n"):
            line = raw_line.rstrip()
            stripped = line.strip()

            if stripped.startswith("```"):
                in_code_block = not in_code_block
                continue

            if stripped in {"---", "***", "___"}:
                if lines_out and lines_out[-1] != "":
                    lines_out.append("")
                continue

            if not stripped:
                if lines_out and lines_out[-1] != "":
                    lines_out.append("")
                continue

            if in_code_block:
                lines_out.append(f"Code: {stripped}")
                continue

            if stripped.startswith(("### ", "## ", "# ")):
                heading_text = simplify_markdown_inline(stripped.lstrip("#").strip())
                lines_out.append(heading_text)
                lines_out.append("")
                continue

            bullet_match = re.match(r"^[-*+]\s+(.+)$", stripped)
            if bullet_match:
                lines_out.append(f"• {simplify_markdown_inline(bullet_match.group(1))}")
                continue

            numbered_match = re.match(r"^(\d+)\.\s+(.+)$", stripped)
            if numbered_match:
                lines_out.append(f"{numbered_match.group(1)}. {simplify_markdown_inline(numbered_match.group(2))}")
                continue

            quote_match = re.match(r"^>\s+(.+)$", stripped)
            if quote_match:
                lines_out.append(f"Zitat: {simplify_markdown_inline(quote_match.group(1))}")
                continue

            lines_out.append(simplify_markdown_inline(stripped))

        while lines_out and lines_out[-1] == "":
            lines_out.pop()

        return lines_out

    def parse_layout_sections(raw_report):
        nonlocal report_title, report_subtitle
        lines = [line.rstrip() for line in str(raw_report).splitlines()]
        sections = []
        current = {"heading": "Zusammenfassung", "body": [], "image_signal": None}
        in_code_block = False

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("```"):
                in_code_block = not in_code_block
                continue

            if not stripped:
                if current["body"] and current["body"][-1] != "":
                    current["body"].append("")
                continue

            if stripped in {"---", "***", "___"}:
                continue

            lower = stripped.lower()
            if lower.startswith("titel:"):
                report_title = stripped.split(":", 1)[1].strip() or report_title
                continue
            if lower.startswith("untertitel:"):
                report_subtitle = stripped.split(":", 1)[1].strip() or report_subtitle
                continue

            signal = extract_image_signal(stripped)
            if signal:
                current["image_signal"] = signal
                continue

            if not in_code_block and looks_like_heading(stripped):
                if current["body"] or current["image_signal"]:
                    sections.append(current)
                current = {
                    "heading": normalize_heading(stripped),
                    "body": [],
                    "image_signal": None,
                }
                continue

            current["body"].append(stripped)

        if current["body"] or current["image_signal"]:
            sections.append(current)

        if not sections:
            sections = [{"heading": "Report", "body": [str(raw_report)], "image_signal": None}]

        return sections

    def build_table_of_contents(sections, toc_pages=None):
        headings = []
        for section in sections:
            heading = str(section.get("heading", "")).strip()
            if not heading:
                continue
            if heading.lower() == "inhaltsverzeichnis":
                continue
            headings.append(heading)

        if not headings:
            return None

        body = []
        for idx, heading in enumerate(headings, start=1):
            page = toc_pages.get(heading, "?") if toc_pages else ""
            body.append(f"{idx}. {heading} ... Seite {page}")

        return {"heading": "Inhaltsverzeichnis", "body": body, "image_signal": None}

    def download_image(image_url):
        def sanitize_image_url(raw_url):
            if not raw_url:
                return None

            cleaned = str(raw_url).strip().strip("<>").strip('"\'')

            # Layouter outputs often append a caption like: "...jpg (Beschreibung)"
            cleaned = re.sub(r"\s+\([^)]*\)\s*$", "", cleaned)

            if cleaned.startswith("//"):
                cleaned = f"https:{cleaned}"
            elif cleaned.startswith("www."):
                cleaned = f"https://{cleaned}"

            if not cleaned.lower().startswith(("http://", "https://")):
                return None

            parsed = urlsplit(cleaned)
            if not parsed.netloc:
                return None

            safe_path = quote(parsed.path, safe="/%:@-._~!$&'()*+,;=")
            safe_query = quote(parsed.query, safe="=&%:+,;@-._~!$'()*")
            safe_fragment = quote(parsed.fragment, safe="=&%:+,;@-._~!$'()*")

            return urlunsplit((parsed.scheme, parsed.netloc, safe_path, safe_query, safe_fragment))

        sanitized_url = sanitize_image_url(image_url)
        if not sanitized_url:
            return None

        suffix = Path(sanitized_url.split("?")[0]).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            suffix = ".jpg"
        target_path = Path(tempfile.gettempdir()) / f"gruene_layout_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{suffix}"
        try:
            urlretrieve(sanitized_url, target_path)
            temp_image_paths.append(target_path)
            return target_path
        except (URLError, HTTPError, OSError, InvalidURL, ValueError):
            return None

    def generate_local_theme_image(prompt_text):
        if Image is None:
            return None

        cache_key = re.sub(r"[^a-z0-9]+", "_", (prompt_text or "gruene_markdorf").lower())[:50]
        cached = image_cache.get(cache_key)
        if cached and cached.exists():
            return cached

        target_path = Path(tempfile.gettempdir()) / (
            f"gruene_theme_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
        )

        width, height = 1600, 900
        base = Image.new("RGB", (width, height), (232, 245, 233))
        draw = ImageDraw.Draw(base)

        for y_pos in range(height):
            t = y_pos / max(1, height - 1)
            r = int(232 + (200 - 232) * t)
            g = int(245 + (230 - 245) * t)
            b = int(233 + (201 - 233) * t)
            draw.line((0, y_pos, width, y_pos), fill=(r, g, b))

        # Decorative bands and shapes
        draw.rectangle((0, 0, width, 120), fill=(27, 94, 32))
        draw.rectangle((0, 120, width, 140), fill=(165, 214, 167))
        draw.ellipse((1180, 90, 1450, 360), fill=(255, 248, 225))
        draw.ellipse((1140, 130, 1490, 430), outline=(255, 213, 79), width=8)

        # Simple leaf icon
        leaf_box = (120, 320, 420, 620)
        draw.ellipse(leaf_box, fill=(46, 125, 50))
        draw.arc(leaf_box, 290, 70, fill=(27, 94, 32), width=8)
        draw.line((270, 470, 270, 650), fill=(27, 94, 32), width=8)

        # Stylized skyline / local scene
        for i, x in enumerate(range(520, 1160, 90)):
            h = 120 + ((i * 37) % 180)
            draw.rounded_rectangle((x, 610 - h, x + 60, 610), radius=8, fill=(255, 255, 255), outline=(120, 144, 156), width=3)
            for yy in range(610 - h + 18, 600, 28):
                draw.line((x + 10, yy, x + 50, yy), fill=(200, 230, 201), width=2)

        # Text overlay
        title = "Gruene Markdorf und Umland"
        subtitle = (prompt_text or "Lokales Motiv")[:90]

        def pick_font(size):
            candidates = [
                r"C:\\Windows\\Fonts\\arial.ttf",
                r"C:\\Windows\\Fonts\\calibri.ttf",
                r"C:\\Windows\\Fonts\\segoeui.ttf",
            ]
            for font_path in candidates:
                if Path(font_path).exists():
                    try:
                        return ImageFont.truetype(font_path, size)
                    except Exception:
                        continue
            return ImageFont.load_default()

        title_font = pick_font(54)
        subtitle_font = pick_font(28)
        footer_font = pick_font(24)

        draw.rounded_rectangle((90, 700, 1510, 840), radius=28, fill=(255, 255, 255, 235), outline=(27, 94, 32), width=4)
        draw.text((130, 724), title, fill=(27, 94, 32), font=title_font)
        draw.text((130, 790), subtitle, fill=(69, 90, 100), font=subtitle_font)
        draw.text((130, 838), "Bild automatisch erzeugt", fill=(76, 175, 80), font=footer_font)

        base.save(target_path, format="PNG", optimize=True)
        temp_image_paths.append(target_path)
        image_cache[cache_key] = target_path
        return target_path

    def draw_image_or_placeholder(img_path, box_x, box_y, box_w, box_h, caption):
        import math as _m
        drawn = False
        if img_path:
            img_suffix = Path(str(img_path)).suffix.lower()
            masks = ["auto"] if img_suffix == ".png" else [None, "auto"]
            for attempt_mask in masks:
                try:
                    from reportlab.lib.utils import ImageReader
                    ir = ImageReader(str(img_path))
                    pdf.drawImage(
                        ir, box_x, box_y,
                        width=box_w, height=box_h,
                        preserveAspectRatio=True, anchor="c", mask=attempt_mask,
                    )
                    drawn = True
                    break
                except Exception:
                    continue

        if not drawn:
            pdf.setFillColor(colors.HexColor("#FAFAFA"))
            pdf.roundRect(box_x, box_y, box_w, box_h, 7, stroke=1, fill=1)
            pdf.setStrokeColor(colors.HexColor("#C8E6C9"))
            pdf.setLineWidth(1)
            pdf.roundRect(box_x, box_y, box_w, box_h, 7, stroke=1, fill=0)

            pdf.setFillColor(colors.HexColor("#1B5E20"))
            pdf.setFont("Helvetica-Bold", 10)
            pdf.drawString(box_x + 12, box_y + box_h - 22, "Bildbeschreibung")

            description = simplify_markdown_inline(caption or _placeholder_status[0] or "Gruene Markdorf und Umland")
            description = description.replace("__CB_CHECKED__", "").replace("__CB_OPEN__", "")
            pdf.setFillColor(colors.HexColor("#37474F"))
            pdf.setFont("Helvetica", 9)
            desc_lines = wrap(description, width=max(25, int(box_w / 7.2)))[:5]
            current_y = box_y + box_h - 40
            for desc_line in desc_lines:
                pdf.drawString(box_x + 12, current_y, desc_line)
                current_y -= 12

    _placeholder_status = ["Nano Banana nicht verfuegbar"]

    def get_nanobanana_api_key():
        return (
            os.getenv("GEMINI_PRO_API_KEY")
            or os.getenv("GEMINI_PRO_KEY")
            or api_key
        )

    def generate_image_with_nanobanana(prompt_text, generate_images=True):
        if not generate_images:
            return generate_local_theme_image(prompt_text)

        nanobanana_api_key = get_nanobanana_api_key()
        if not nanobanana_api_key or genai is None:
            _placeholder_status[0] = "Nano Banana: kein API-Key oder Bibliothek fehlt"
            return generate_local_theme_image(prompt_text)

        model_candidates = [
            "imagen-4.0-generate-001",
            "imagen-4.0-fast-generate-001",
            "imagen-4.0-ultra-generate-001",
        ]
        safe_prompt = (
            f"Realistic modern press photo for Gruene Markdorf und Umland: {prompt_text}. "
            "Daylight, authentic, local politics or nature, no logos, no text in image."
        )

        client = genai.Client(api_key=nanobanana_api_key)
        if status_callback:
            status_callback(f"Generiere Bild: {prompt_text[:60]}...")

        last_error = None
        for model_name in model_candidates:
            if not model_name:
                continue
            try:
                config = None
                if genai_types is not None and hasattr(genai_types, "GenerateImagesConfig"):
                    config = genai_types.GenerateImagesConfig(
                        number_of_images=1,
                        output_mime_type="image/jpeg",
                        aspect_ratio="16:9"
                    )

                if config is not None:
                    result = client.models.generate_images(
                        model=model_name,
                        prompt=safe_prompt,
                        config=config
                    )
                else:
                    result = client.models.generate_images(
                        model=model_name,
                        prompt=safe_prompt
                    )

                # Extract image from GenerateImagesResponse
                for generated_image in getattr(result, "images", getattr(result, "generated_images", [])):
                    if hasattr(generated_image, "image"): # Old vertex format
                        image_bytes = getattr(generated_image.image, "image_bytes", None)
                    else: # New structure where it's a list of `Image` directly
                        image_bytes = getattr(generated_image, "image_bytes", None)
                    
                    if not image_bytes:
                        continue

                    if isinstance(image_bytes, str):
                        image_bytes = base64.b64decode(image_bytes)

                    target_path = Path(tempfile.gettempdir()) / (
                        f"gruene_layout_nanobanana_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
                    )

                    # Normalize to RGB PNG to avoid ReportLab issues with unusual JPEG/WebP formats.
                    normalized = False
                    if Image is not None:
                        try:
                            with Image.open(io.BytesIO(image_bytes)) as pil_img:
                                if pil_img.mode not in ("RGB", "RGBA"):
                                    pil_img = pil_img.convert("RGB")
                                pil_img.save(target_path, format="PNG", optimize=True)
                                normalized = True
                        except Exception:
                            normalized = False

                    if not normalized:
                        target_path.write_bytes(image_bytes)

                    temp_image_paths.append(target_path)
                    _placeholder_status[0] = "Bild erfolgreich generiert"
                    return target_path

                last_error = "Keine Bilddaten in der Antwort enthalten"
            except Exception as exc:
                short_err = str(exc)[:240]
                last_error = short_err
                log_to_file(f"Bildgenerierung mit Model {model_name} fehlgeschlagen: {short_err}", "ERROR")
                continue

        _placeholder_status[0] = f"Nano Banana: kein Modell verfügbar ({last_error})"
        if status_callback:
            status_callback("Bild aktuell nicht verfügbar, ersetze durch lokalen Platzhalter.")
        return generate_local_theme_image(prompt_text)

    def infer_image_prompt(section):
        heading = section.get("heading", "Kommunalpolitik in Markdorf")
        body_text = " ".join(line for line in section.get("body", []) if line).lower()

        keyword_map = {
            "mobil": "moderne, sichere Radwege und OePNV in einer kleinen deutschen Stadt",
            "verkehr": "verkehrsberuhigte Innenstadt mit Fahrrad, Bus und Fussgaengern",
            "klima": "klimaanpassung in einer Stadt mit Baeumen, Schatten und Wasserflaechen",
            "energie": "kommunale Energiewende mit Solaranlagen auf oeffentlichen Gebaeuden",
            "natur": "Naturschutzflaechen, artenreiche Wiesen und lokale Biodiversitaet",
            "jugend": "junge Menschen bei einem lokalen Beteiligungsworkshop",
            "buerger": "Buergerdialog bei einer lokalen Veranstaltung im Rathausumfeld",
            "wohnen": "bezahlbares, nachhaltiges Wohnen in moderner Holzbauweise",
        }

        for key, prompt in keyword_map.items():
            if key in body_text or key in heading.lower():
                return f"{prompt}, Markdorf, Baden-Wuerttemberg"

        return f"lokalpolitische Szene in Markdorf zum Thema {heading}, modern und authentisch"

    local_images = find_local_layout_images()
    local_image_index = 0

    def resolve_image_for_section(section, index, generate_images=True):
        nonlocal local_image_index
        signal = section.get("image_signal")
        hint_text = infer_image_prompt(section)
        heading_lower = str(section.get("heading", "")).lower()

        # Messenger-Beitraege sollen explizit ohne Bild ausgegeben werden.
        if heading_lower in {"messenger"}:
            return None, None

        if signal and signal.get("value"):
            signal_type = signal.get("type")
            signal_value = signal.get("value")

            if signal_type == "url":
                image_path = download_image(signal_value)
                if image_path:
                    return image_path, signal_value
                return generate_image_with_nanobanana(signal_value, generate_images), signal_value

            if signal_type == "hint":
                if local_images:
                    image_path = local_images[local_image_index % len(local_images)]
                    local_image_index += 1
                    return image_path, signal_value
                return generate_image_with_nanobanana(signal_value, generate_images), signal_value

            if signal_type == "prompt":
                return generate_image_with_nanobanana(signal_value, generate_images), signal_value

        wants_image = (
            index == 0
            or len(" ".join(str(l) for l in section.get("body", []))) > 130
            or heading_lower in {"instagram", "facebook", "webseite", "website"}
        )
        if not wants_image:
            return None, None

        if local_images:
            image_path = local_images[local_image_index % len(local_images)]
            local_image_index += 1
            return image_path, hint_text

        return generate_image_with_nanobanana(hint_text, generate_images), hint_text

    def draw_page_chrome(current_page):
        pdf.setFillColor(colors.HexColor("#F3FAF4"))
        pdf.rect(0, 0, page_width, page_height, stroke=0, fill=1)

        pdf.setFillColor(colors.HexColor("#DCEEDB"))
        pdf.circle(page_width - 52, page_height - 35, 48, stroke=0, fill=1)
        pdf.circle(56, 64, 36, stroke=0, fill=1)

        pdf.setFillColor(colors.HexColor("#1B5E20"))
        pdf.rect(0, page_height - 104, page_width, 104, stroke=0, fill=1)
        pdf.setFillColor(colors.HexColor("#A5D6A7"))
        pdf.rect(0, page_height - 111, page_width, 7, stroke=0, fill=1)

        pdf.setFillColor(colors.white)
        pdf.setFont("Helvetica-Bold", 20)
        pdf.drawString(left_margin, page_height - 42, report_title[:70])
        pdf.setFont("Helvetica", 10.5)
        pdf.drawString(left_margin, page_height - 63, report_subtitle[:95])

        pdf.setFillColor(colors.HexColor("#607D8B"))
        pdf.setFont("Helvetica", 8.7)
        pdf.drawString(left_margin, 24, f"Erstellt am: {created_at}")
        pdf.drawRightString(page_width - right_margin, 24, f"Seite {current_page}")

    def open_new_page():
        nonlocal page_number, y
        if page_number > 1:
            pdf.showPage()
        draw_page_chrome(page_number)
        y = top_margin

    def next_page():
        nonlocal page_number
        page_number += 1
        pdf.showPage()
        draw_page_chrome(page_number)
        return top_margin

    def ensure_space(required_height):
        nonlocal y
        if y - required_height <= bottom_margin:
            y = next_page()

    sections = parse_layout_sections(report_text)
    toc_pages = {}
    current_page_for_toc = 2  # TOC on page 1, first chapter on page 2

    # First pass to collect page numbers
    for idx, section in enumerate(sections):
        heading = section.get("heading") or f"Abschnitt {idx + 1}"
        if heading.lower() == "inhaltsverzeichnis":
            continue
        toc_pages[heading] = current_page_for_toc
        if "kapitel" in heading.lower():
            current_page_for_toc += 1

    if sections and sections[0].get("heading", "").strip().lower() != "inhaltsverzeichnis":
        toc_section = build_table_of_contents(sections, toc_pages)
        if toc_section:
            sections.insert(0, toc_section)

    open_new_page()

    pdf.setFillColor(colors.HexColor("#E8F5E9"))
    pdf.roundRect(left_margin, y - 46, content_width, 38, 8, stroke=0, fill=1)
    pdf.setFillColor(colors.HexColor("#1B5E20"))
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(left_margin + 12, y - 23, "Modernes Themenlayout | Gruene Markdorf und Umland")
    y -= 60

    for idx, section in enumerate(sections):
        heading = section.get("heading") or f"Abschnitt {idx + 1}"
        body_lines = [line for line in section.get("body", []) if line is not None]
        body_text = "\n".join(body_lines).strip()
        if not body_text:
            body_text = "Keine weiteren Detailangaben fuer diesen Abschnitt verfuegbar."

        wrapped_lines = []
        for paragraph in markdown_to_render_lines(body_text):
            if not paragraph.strip():
                wrapped_lines.append("")
                continue
            wrapped_lines.extend(wrap(paragraph.strip(), width=94))

        image_path, image_caption = resolve_image_for_section(section, idx, generate_images)
        if image_path:
            image_path = save_persistent_image(image_path, idx) or image_path
        has_signal = section.get("image_signal") is not None
        heading_lower_img = str(section.get("heading", "")).lower()
        is_messenger_section = heading_lower_img in {"messenger"}
        wants_image_slot = (
            (has_signal and not is_messenger_section)
            or heading_lower_img in {"instagram", "facebook", "webseite", "website"}
            or idx == 0
            or len(" ".join(str(l) for l in section.get("body", []))) > 130
        )
        if is_messenger_section:
            wants_image_slot = False
        image_height = 166 if wants_image_slot else 0

        text_height = (len(wrapped_lines) * 12.3) + 40
        card_height = text_height + (image_height + 22 if image_height else 0) + 20

        ensure_space(card_height + 14)

        card_x = left_margin
        card_y = y - card_height

        pdf.setFillColor(colors.HexColor("#D0DAD3"))
        pdf.roundRect(card_x + 2, card_y - 2, content_width, card_height, 10, stroke=0, fill=1)

        pdf.setFillColor(colors.white)
        pdf.roundRect(card_x, card_y, content_width, card_height, 10, stroke=0, fill=1)

        pdf.setFillColor(colors.HexColor("#2E7D32"))
        pdf.roundRect(card_x + 10, card_y + card_height - 30, 5, 18, 2, stroke=0, fill=1)

        text_y = card_y + card_height - 18
        pdf.setFillColor(colors.HexColor("#1B5E20"))
        if "kapitel" in heading.lower():
            pdf.setFont("Helvetica-Bold", 16)
            pdf.bookmarkPage(heading)
        else:
            pdf.setFont("Helvetica-Bold", 13)
        pdf.drawString(card_x + 22, text_y, heading[:78])
        text_y -= 18

        def draw_checkbox(cx, cy, checked):
            box_size = 8
            pdf.setStrokeColor(colors.HexColor("#2E7D32"))
            pdf.setLineWidth(0.8)
            pdf.rect(cx, cy - 1, box_size, box_size, stroke=1, fill=0)
            if checked:
                pdf.setStrokeColor(colors.HexColor("#1B5E20"))
                pdf.setLineWidth(1.2)
                pdf.line(cx + 1, cy + 3, cx + 3, cy + 1)
                pdf.line(cx + 3, cy + 1, cx + 7, cy + 6)
            pdf.setStrokeColor(colors.HexColor("#263238"))
            pdf.setLineWidth(0.5)

        pdf.setFillColor(colors.HexColor("#263238"))
        pdf.setFont("Helvetica", 10.2)
        for line in wrapped_lines:
            if not line:
                text_y -= 6
                continue
            if line.startswith("__CB_CHECKED__ ") or line.startswith("__CB_OPEN__ "):
                checked = line.startswith("__CB_CHECKED__")
                label = line.split(" ", 1)[1] if " " in line else ""
                draw_checkbox(card_x + 22, text_y, checked)
                pdf.setFillColor(colors.HexColor("#263238"))
                pdf.drawString(card_x + 36, text_y, label)
            else:
                pdf.drawString(card_x + 22, text_y, line)
            text_y -= 12.3

        if wants_image_slot:
            image_box_y = card_y + 14
            image_box_x = card_x + 20
            image_box_width = content_width - 40
            draw_image_or_placeholder(image_path, image_box_x, image_box_y, image_box_width, image_height, image_caption)

        y = card_y - 14

        # New page for chapters
        if "kapitel" in heading.lower():
            y = next_page()

    pdf.save()

    markdown_lines = [str(report_text).strip(), "", "## Eingesetzte Bilder", ""]
    for image_path in saved_report_images.values():
        rel_path = Path("images") / image_path.name
        markdown_lines.append(f"- ![{image_path.stem}]({rel_path.as_posix()})")
    markdown_lines.append("")
    try:
        md_path.write_text("\n".join(markdown_lines), encoding="utf-8")
    except Exception:
        pass

    for temp_path in temp_image_paths:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass

    return pdf_path, md_path

def build_markdorf_pr_crew(api_key):
    flash_model = os.getenv("GEMINI_FLASH_MODEL", "gemini/gemini-2.5-flash")
    pro_model = os.getenv("GEMINI_PRO_MODEL", "gemini/gemini-2.5-flash")

    gemini_flash = LLM(model=flash_model, api_key=api_key, temperature=0.7)
    gemini_pro = LLM(model=pro_model, api_key=api_key, temperature=0.3)

    researcher = Agent(
        role="Lokal-Researcher Markdorf und Umland",
        goal="Finde ein klar abgegrenztes Set aus 3 aktuellen, brisanten politischen Themen in Markdorf und Umland.",
        backstory="""Du bist der Infopool des Ortsverbands. Du scannst Lokalnachrichten,
    Gemeinderatsprotokolle und regionale Mitteilungen. Dein Fokus liegt auf absoluter
    Aktualität und lokaler Relevanz für grüne Kernthemen.""",
        llm=gemini_flash,
        verbose=True,
    )

    expert = Agent(
        role="Grüner Grundsatz-Experte",
        goal="Liefere fundierte Hintergründe und die offizielle grüne Position zu den Themen.",
        backstory="""Du bist der inhaltliche Anker. Du verknüpfst lokale Ereignisse mit dem
    Landesprogramm BW und Bundesvorgaben. Du lieferst die harten Fakten und Argumente,
    warum ein Thema aus grüner Sicht relevant ist.""",
        llm=gemini_pro,
        verbose=True,
    )

    social_media = Agent(
        role="Content Manager Markdorf und Umland",
        goal="Erstelle kanalgenaue Entwürfe für Instagram, Facebook, Webseite und Messenger.",
        backstory="""Du bist die Stimme des Ortsverbands nach außen. Du schreibst packend,
    nahbar und nutzt regionale Schlagworte. Du passt Ton, Länge und Struktur
    an den jeweiligen Kanal an und erstellst aus trockenen Fakten
    emotionale und aktivierende Inhalte für Social Media, Website und Direktnachrichten.""",
        llm=gemini_flash,
        verbose=True,
    )

    compliance_officer = Agent(
        role="Politischer Chef-Redakteur & Strategie-Berater",
        goal="Prüfe Posts auf Parteilinie, schreibe sie ggf. um und begründe Änderungen.",
        backstory="""Du bist die letzte Instanz. Du stellst sicher, dass kein Post gegen die
    Linie von Bund, Land oder Kreis verstößt. Du polierst die Texte diplomatisch auf
    und erklärst deine Korrekturen, um das Team strategisch zu schulen.""",
        llm=gemini_pro,
        verbose=True,
    )

    layouter = Agent(
        role="Layouter fuer Gruene Markdorf",
        goal="Erzeuge aus dem finalen Report ein modernes, visuell klares PDF-Layout mit sinnvollen Bildhinweisen.",
        backstory="""Du bist Art Director fuer politische Kommunikation. Du strukturierst Inhalte lesefreundlich,
    definierst klare Abschnittstitel und gibst gezielte Bildhinweise fuer lokale, nachhaltige und gruene Themen.
    Dein Stil wirkt modern, ruhig und glaubwuerdig fuer den Ortsverband Markdorf und Umland.""",
        llm=gemini_pro,
        verbose=True,
    )

    task_research = Task(
        description="Recherchiere 3 aktuelle kommunalpolitische Themen in Markdorf und Umland (Woche: Mai 2026). Stelle sicher, dass jedes Thema klar voneinander abgrenzbar und lokal relevant ist.",
        expected_output="Eine Liste mit 3 News-Themen inkl. Quellenangabe oder kurzer Zusammenfassung, getrennt nach Thema.",
        agent=researcher,
    )

    task_background = Task(
        description="Vertiefe jedes der 3 recherchierten Themen und ergänze sie um grüne Hintergründe, Argumente und klare Relevanz für Markdorf und Umland.",
        expected_output="Ein inhaltliches Briefing zu den 3 Themen mit Fakten-Check, grünem Bezug und jeweils einem kurzen Fokusargument.",
        agent=expert,
        context=[task_research],
    )

    task_creation = Task(
        description="""Erstelle auf Basis des Briefings zu den 3 Themen für jedes Thema je einen Instagram-, Facebook-, Website- und Messenger-Beitrag.
    Gliedere die Ausgabe in Kapitel: THEMA 1, THEMA 2, THEMA 3.
    Passe Ton, Länge und Call-to-Action an den jeweiligen Kanal an.""",
        expected_output="""Format:
    ---
    THEMA 1:
    INSTAGRAM: [Text inkl. Hashtags und Bildidee]
    FACEBOOK: [Text inkl. Call-to-Action]
    WEBSEITE: [Kurzartikel mit Überschrift, Teaser und Haupttext]
    MESSENGER: [Kurznachricht für Broadcast oder Gruppe]

    THEMA 2:
    INSTAGRAM: ...
    FACEBOOK: ...
    WEBSEITE: ...
    MESSENGER: ...

    THEMA 3:
    INSTAGRAM: ...
    FACEBOOK: ...
    WEBSEITE: ...
    MESSENGER: ...
    ---""",
        agent=social_media,
        context=[task_background],
    )

    task_compliance = Task(
        description="""Überprüfe alle vier Entwürfe auf Konformität (Bund, Land BW, Kreis).
    Schreibe die Texte bei Bedarf direkt um, um sie strategisch und kanalgerecht zu optimieren.
    Erstelle am Ende eine kurze Liste deiner Änderungen mit Begründung.""",
        expected_output="""Format:
    ---
    FINALER INSTAGRAM-POST:
    [Der fertige Text]

    FINALER FACEBOOK-BEITRAG:
    [Der fertige Text]

    FINALER WEBSEITEN-ARTIKEL:
    [Der fertige Text]

    FINALER MESSENGER-TEXT:
    [Der fertige Text]

    ÄNDERUNGSLOG & BEGRÜNDUNG:
    - [Änderung X]: [Warum?]
    ---""",
        agent=compliance_officer,
        context=[task_creation],
    )

    task_layout = Task(
        description="""Layoutiere den finalen Report fuer den PDF-Export in einem modernen Stil passend zu Gruene Markdorf.
    Erzeuge den finalen Report mit Inhaltsverzeichnis und drei Kapiteln, eines pro Thema.
    Jedes Kapitel soll das Thema beschreiben, den grünen Hintergrund erklären und die vier Kanal-Posts enthalten.
    Erstelle pro Kapitel je einen Instagram-, Facebook-, Website- und Messenger-Text.
    Fuege dort, wo es sinnvoll ist, passende Bildhinweise ein (lokaler Bezug, Mobilitaet, Klima,
    Energie, Natur, Buergerdialog). Wenn moeglich, gib konkrete Bild-URLs an, sonst einen praezisen
    Bild-Hinweis oder einen Bild-Prompt zur direkten Nano-Banana-Generierung.
    Fuege Bildbloecke nur fuer INSTAGRAM, FACEBOOK und WEBSEITE ein.
    Fuer MESSENGER niemals einen Bild-Block ausgeben.""",
        expected_output="""Format:
    ---
    TITEL: [Titel des finalen Reports]
    UNTERTITEL: [Untertitel mit lokalem Bezug]

    INHALTSVERZEICHNIS:
    1. Thema 1
    2. Thema 2
    3. Thema 3

    KAPITEL 1: THEMA 1
    [Kurze Einleitung zum Thema]
    INSTAGRAM: [Text inkl. Hashtags und Bildidee]
    FACEBOOK: [Text inkl. Call-to-Action]
    WEBSEITE: [Kurzartikel mit Ueberschrift, Teaser und Haupttext]
    MESSENGER: [Kurznachricht fuer Broadcast oder Gruppe]

    KAPITEL 2: THEMA 2
    ...

    KAPITEL 3: THEMA 3
    ...
    ---""",
        agent=layouter,
        context=[task_compliance],
    )

    return Crew(
        agents=[researcher, expert, social_media, compliance_officer, layouter],
        tasks=[task_research, task_background, task_creation, task_compliance, task_layout],
        process=Process.sequential,
        verbose=True,
    )


def refine_report_with_gemini_designer(raw_report, api_key):
    if not api_key or genai is None:
        return str(raw_report)

    model_name = os.getenv("GEMINI_LAYOUT_MODEL", "gemini-2.5-pro")
    source_text = str(raw_report)

    prompt = f"""Du bist ein Premium-Redaktionsdesigner wie im Gemini-Webinterface.
Erstelle aus dem folgenden Roh-Report eine druckreife Endfassung fuer ein modernes PDF.

Wichtige Regeln:
- Gib nur den finalen Inhalt aus, keine Erklaerungen.
- Liefere exakt diese Struktur:
  TITEL: ...
  UNTERTITEL: ...
  INHALTSVERZEICHNIS:
  1. Thema 1
  2. Thema 2
  3. Thema 3

  KAPITEL 1: THEMA 1
  [Kurze Einleitung zum Thema]
  INSTAGRAM: ...
  FACEBOOK: ...
  WEBSEITE: ...
  MESSENGER: ...

  KAPITEL 2: THEMA 2
  ...

  KAPITEL 3: THEMA 3
  ...
- Genau ein Bildblock bei INSTAGRAM, FACEBOOK und WEBSEITE pro Kapitel (BILD_URL oder BILD_HINWEIS oder BILD_PROMPT).
- Fuer MESSENGER kein Bildblock.
- Schreibe ohne Markdown-Codeblock-Markierungen.
- Schreibe in deutscher Sprache.
- Nenne drei klare, unterscheidbare Kapitel fuer die drei Themen.

Roh-Report:
{source_text}
"""

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model=model_name, contents=prompt)

        if getattr(response, "text", None):
            refined = str(response.text).strip()
            if refined:
                return refined

        parts = []
        for candidate in getattr(response, "candidates", []) or []:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", []) or []:
                text_value = getattr(part, "text", None)
                if text_value:
                    parts.append(str(text_value))

        refined = "\n".join(parts).strip()
        if refined:
            return refined
    except Exception:
        return str(raw_report)

    return str(raw_report)


def run_research(api_key, status_callback=None, generate_images=True):
    if not api_key or not api_key.strip():
        log_to_file("Fehler: API-Key fehlt bei Aufruf von run_research.", "ERROR")
        raise ValueError("Bitte gib einen API-Key ein.")

    clean_api_key = api_key.strip()
    log_to_file("Starte run_research.", "INFO")

    if status_callback:
        status_callback("Initialisiere Agenten...")
    log_to_file("Initialisiere Agenten...", "INFO")
    crew = build_markdorf_pr_crew(clean_api_key)

    if status_callback:
        status_callback("Recherche läuft...")
    log_to_file("Recherche läuft...", "INFO")
    result = crew.kickoff()

    if status_callback:
        status_callback("Veredle Report mit Gemini Designer...")
    log_to_file("Veredle Report mit Gemini Designer...", "INFO")
    final_report = refine_report_with_gemini_designer(result, clean_api_key)

    if status_callback:
        status_callback("Erstelle PDF-Report...")
    log_to_file("Erstelle PDF-Report...", "INFO")
    pdf_path, md_path = export_report_to_pdf(final_report, api_key=clean_api_key, status_callback=status_callback, generate_images=generate_images)

    try:
        if os.name == "nt":
            os.startfile(str(pdf_path))
        else:
            subprocess.Popen([str(pdf_path)], shell=True)
    except Exception:
        if status_callback:
            status_callback("PDF wurde erstellt, konnte aber nicht automatisch geöffnet werden.")

    if status_callback:
        status_callback("Recherche abgeschlossen.")
    return str(final_report), str(pdf_path), str(md_path)


def get_app_icon_path():
    if getattr(sys, "frozen", False):
        base_path = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base_path = Path(__file__).resolve().parent
    return base_path / "assets" / "gruene_icon.svg"


class ResearchWorker(QObject):
    status_changed = Signal(str)
    agent_changed = Signal(str)
    result_ready = Signal(str, str, str)
    error_occurred = Signal(str)
    finished = Signal()

    def __init__(self, api_key, generate_images=True):
        super().__init__()
        self.api_key = api_key
        self.generate_images = generate_images
        self._last_agent_status = ""

    def _status_from_log_line(self, line):
        line_lower = line.lower()
        agent_markers = [
            ("lokal-researcher markdorf und umland", "Lokal-Researcher"),
            ("gruener grundsatz-experte", "Gruener Grundsatz-Experte"),
            ("content manager markdorf und umland", "Content Manager"),
            ("politischer chef-redakteur & strategie-berater", "Chef-Redakteur"),
            ("layouter fuer gruene markdorf", "Layouter"),
        ]

        for marker, label in agent_markers:
            if marker in line_lower:
                return f"Aktiver Agent: {label}"
        return None

    def _handle_runtime_log_line(self, line):
        status_text = self._status_from_log_line(line)
        if status_text and status_text != self._last_agent_status:
            self._last_agent_status = status_text
            self.agent_changed.emit(status_text)

    def run(self):
        class _LogTee:
            def __init__(self, original_stream, line_callback):
                self.original_stream = original_stream
                self.line_callback = line_callback
                self._buffer = ""

            def write(self, data):
                self.original_stream.write(data)
                self._buffer += data
                while "\n" in self._buffer:
                    line, self._buffer = self._buffer.split("\n", 1)
                    self.line_callback(line)
                return len(data)

            def flush(self):
                if self._buffer:
                    self.line_callback(self._buffer)
                    self._buffer = ""
                self.original_stream.flush()

        try:
            stdout_tee = _LogTee(sys.stdout, self._handle_runtime_log_line)
            stderr_tee = _LogTee(sys.stderr, self._handle_runtime_log_line)
            with contextlib.redirect_stdout(stdout_tee), contextlib.redirect_stderr(stderr_tee):
                result, pdf_path, md_path = run_research(self.api_key, self.status_changed.emit, self.generate_images)
            self.result_ready.emit(result, pdf_path, md_path)
        except Exception as exc:
            error_text = f"{exc}\n\n{traceback.format_exc()}"
            log_to_file(error_text, "ERROR")
            self.error_occurred.emit(error_text)
        finally:
            self.agent_changed.emit("Aktiver Agent: -")
            self.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Gruene Themen Researcher - Ortsverband Markdorf und Umland v{get_app_version()}")
        icon_path = get_app_icon_path()
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(980, 700)
        self.worker_thread = None
        self.worker = None

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)

        form_layout = QFormLayout()
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("API-Key eingeben")
        form_layout.addRow("Google API-Key:", self.api_key_input)

        self.api_key_help = QLabel(
            'Noch keinen API-Key? <a href="https://aistudio.google.com/app/apikey">Hier Google API-Key erstellen</a>'
        )
        self.api_key_help.setOpenExternalLinks(True)
        form_layout.addRow("Info:", self.api_key_help)

        self.version_label = QLabel(f"Version: v{get_app_version()}")
        form_layout.addRow("Version:", self.version_label)

        self.status_label = QLabel("Bereit")
        form_layout.addRow("Status:", self.status_label)

        self.active_agent_label = QLabel("Aktiver Agent: -")
        form_layout.addRow("Agent:", self.active_agent_label)

        self.generate_images_checkbox = QCheckBox("Bilder generieren")
        self.generate_images_checkbox.setChecked(True)
        self.generate_images_checkbox.setToolTip("Ohne Bilder entstehen Kosten zwischen 5-10 cent mit Bilder zwischen 20-30 cent.")
        form_layout.addRow("Optionen:", self.generate_images_checkbox)

        root_layout.addLayout(form_layout)

        self.start_button = QPushButton("Recherche starten")
        self.start_button.clicked.connect(self.start_research)
        root_layout.addWidget(self.start_button)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setPlaceholderText("Das Ergebnis der Recherche erscheint hier...")
        root_layout.addWidget(self.result_text)

    def start_research(self):
        api_key = self.api_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "API-Key fehlt", "Bitte gib zuerst einen API-Key ein.")
            return

        self.result_text.clear()
        self.set_status("Starte Recherche...")
        self.start_button.setEnabled(False)

        self.worker_thread = QThread(self)
        self.worker = ResearchWorker(api_key, self.generate_images_checkbox.isChecked())
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.status_changed.connect(self.set_status)
        self.worker.agent_changed.connect(self.set_active_agent)
        self.worker.result_ready.connect(self.show_result)
        self.worker.error_occurred.connect(self.show_error)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.finished.connect(self.on_worker_finished)

        self.worker_thread.start()

    def set_status(self, status_text):
        self.status_label.setText(status_text)
        log_to_file(status_text, "INFO")

    def set_active_agent(self, status_text):
        self.active_agent_label.setText(status_text)

    def show_result(self, result_text, pdf_path, md_path):
        self.result_text.setPlainText(result_text)
        self.result_text.append(f"\n\nPDF gespeichert unter: {pdf_path}")
        self.result_text.append(f"Markdown gespeichert unter: {md_path}")
        log_to_file(f"Recherche erfolgreich abgeschlossen, PDF: {pdf_path}, Markdown: {md_path}", "INFO")

    def show_error(self, error_text):
        self.set_status("Fehler bei der Recherche")
        self.result_text.setPlainText(error_text)
        log_to_file(error_text, "ERROR")

    def on_worker_finished(self):
        self.start_button.setEnabled(True)
        self.set_active_agent("Aktiver Agent: -")
        self.worker = None
        self.worker_thread = None


def main():
    app = QApplication([])
    icon_path = get_app_icon_path()
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    window = MainWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()