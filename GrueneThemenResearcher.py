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
APP_VERSION_MINOR = 8
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
        "google.genai": "google-genai",
    }

    for module_name, package_name in required_modules.items():
        if not _is_module_available(module_name):
            _install_package(package_name)

    if not (_is_module_available("PySide6") or _is_module_available("PyQt5")):
        _install_package("PySide6")


ensure_dependencies_installed()

from crewai import Agent, Task, Crew, Process, LLM

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


def export_report_to_pdf(report_text, output_dir='reports', api_key=None, status_callback=None, generate_images=True):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_slug = re.sub(r'[^a-z0-9]+', '_', 'gruene_themen_report').strip('_') or 'gruene_report'
    report_basename = f'{report_slug}_{timestamp}'
    md_path = output_path / f'{report_basename}.md'

    if status_callback:
        status_callback('Speichere Markdown-Report...')

    markdown_lines = [str(report_text).strip(), '']
    try:
        md_path.write_text('\n'.join(markdown_lines), encoding='utf-8')
    except Exception:
        pass

    return None, md_path

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
        status_callback("Erstelle Markdown-Report...")
    log_to_file("Erstelle Markdown-Report...", "INFO")
    pdf_path, md_path = export_report_to_pdf(final_report, api_key=clean_api_key, status_callback=status_callback, generate_images=generate_images)

    if status_callback:
        status_callback("Recherche abgeschlossen.")
    return str(final_report), "", str(md_path)


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
        self.result_text.append(f"\n\nMarkdown gespeichert unter: {md_path}")
        log_to_file(f"Recherche erfolgreich abgeschlossen, Markdown: {md_path}", "INFO")

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