import os
import importlib.util
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path
from textwrap import wrap


def _is_module_available(module_name):
    return importlib.util.find_spec(module_name) is not None


def _install_package(package_name):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])


def ensure_dependencies_installed():
    required_modules = {
        "crewai": "crewai",
        "reportlab": "reportlab",
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
    from PySide6.QtCore import QObject, QThread, Signal
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import (
        QApplication,
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


def export_report_to_pdf(report_text, output_dir="reports"):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_path = output_path / f"finaler_report_{timestamp}.pdf"

    pdf = canvas.Canvas(str(pdf_path), pagesize=A4)
    page_width, page_height = A4
    left_margin = 46
    right_margin = 46
    top_margin = page_height - 120
    bottom_margin = 70
    content_width = page_width - left_margin - right_margin
    max_chars = 102

    report_title = "Report Gruene Themen"
    report_subtitle = "Finaler Redaktionsreport fuer Ortsverband Markdorf und Umland"
    created_at = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    page_number = 1

    def draw_page_chrome(current_page):
        pdf.setFillColor(colors.HexColor("#1B5E20"))
        pdf.rect(0, page_height - 92, page_width, 92, stroke=0, fill=1)

        pdf.setFillColor(colors.white)
        pdf.setFont("Helvetica-Bold", 21)
        pdf.drawString(left_margin, page_height - 44, report_title)
        pdf.setFont("Helvetica", 10)
        pdf.drawString(left_margin, page_height - 62, report_subtitle)

        pdf.setStrokeColor(colors.HexColor("#A5D6A7"))
        pdf.setLineWidth(1)
        pdf.line(left_margin, page_height - 98, page_width - right_margin, page_height - 98)

        pdf.setFillColor(colors.HexColor("#546E7A"))
        pdf.setFont("Helvetica", 9)
        pdf.drawString(left_margin, 30, f"Erstellt am: {created_at}")
        pdf.drawRightString(page_width - right_margin, 30, f"Seite {current_page}")

    draw_page_chrome(page_number)

    y = top_margin

    pdf.setFillColor(colors.HexColor("#263238"))
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(left_margin, y, "Projektrahmen")
    y -= 16

    pdf.setFont("Helvetica", 10)
    pdf.setFillColor(colors.black)
    meta_lines = [
        "Ortsverband: Markdorf und Umland",
        "Thema: Kommunalpolitische Gruene Themen",
        "Output: Mehrkanal-Entwuerfe mit Compliance-Pruefung",
    ]
    for meta_line in meta_lines:
        pdf.drawString(left_margin, y, f"- {meta_line}")
        y -= 14

    y -= 8
    pdf.setStrokeColor(colors.HexColor("#CFD8DC"))
    pdf.setLineWidth(0.8)
    pdf.line(left_margin, y, left_margin + content_width, y)
    y -= 18

    for paragraph in str(report_text).splitlines():
        line = paragraph.strip()

        if y <= bottom_margin:
            pdf.showPage()
            page_number += 1
            draw_page_chrome(page_number)
            y = top_margin

        if not line:
            y -= 10
            continue

        is_heading = line.endswith(":") and len(line) < 80
        if is_heading:
            pdf.setFillColor(colors.HexColor("#1B5E20"))
            pdf.setFont("Helvetica-Bold", 12)
            wrapped_lines = wrap(line, width=90)
        else:
            pdf.setFillColor(colors.black)
            pdf.setFont("Helvetica", 10.5)
            wrapped_lines = wrap(line, width=max_chars)

        for wrapped_line in wrapped_lines:
            if y <= bottom_margin:
                pdf.showPage()
                page_number += 1
                draw_page_chrome(page_number)
                y = top_margin
                if is_heading:
                    pdf.setFillColor(colors.HexColor("#1B5E20"))
                    pdf.setFont("Helvetica-Bold", 12)
                else:
                    pdf.setFillColor(colors.black)
                    pdf.setFont("Helvetica", 10.5)

            pdf.drawString(left_margin, y, wrapped_line)
            y -= 14 if is_heading else 13

        y -= 4

    pdf.save()
    return pdf_path

def build_markdorf_pr_crew(api_key):
    flash_model = os.getenv("GEMINI_FLASH_MODEL", "gemini/gemini-2.5-flash")
    pro_model = os.getenv("GEMINI_PRO_MODEL", "gemini/gemini-2.5-flash")

    gemini_flash = LLM(model=flash_model, api_key=api_key, temperature=0.7)
    gemini_pro = LLM(model=pro_model, api_key=api_key, temperature=0.3)

    researcher = Agent(
        role="Lokal-Researcher Markdorf und Umland",
        goal="Finde 3 aktuelle, brisante politische Themen in Markdorf und Umland.",
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

    task_research = Task(
        description="Recherchiere 3 aktuelle kommunalpolitische Themen in Markdorf und Umland (Woche: Mai 2026).",
        expected_output="Eine Liste mit 3 News-Themen inkl. Quellenangabe oder kurzer Zusammenfassung.",
        agent=researcher,
    )

    task_background = Task(
        description="Wähle das relevanteste Thema aus und ergänze es um grüne Hintergründe und Argumente.",
        expected_output="Ein inhaltliches Briefing mit Fakten-Check und Bezug zum grünen Programm.",
        agent=expert,
        context=[task_research],
    )

    task_creation = Task(
        description="""Erstelle auf Basis des Briefings vier getrennte Entwürfe:
    1. einen Instagram-Post,
    2. einen Facebook-Beitrag,
    3. einen kurzen Website-Artikel,
    4. eine kurze Messenger-Nachricht für Broadcast oder Gruppenversand.
    Passe Ton, Länge und Call-to-Action an den jeweiligen Kanal an.""",
        expected_output="""Format:
    ---
    INSTAGRAM:
    [Text inkl. Hashtags und Bildidee]

    FACEBOOK:
    [Text inkl. Call-to-Action]

    WEBSEITE:
    [Kurzartikel mit Überschrift, Teaser und Haupttext]

    MESSENGER:
    [Kurznachricht für Broadcast oder Gruppe]
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

    return Crew(
        agents=[researcher, expert, social_media, compliance_officer],
        tasks=[task_research, task_background, task_creation, task_compliance],
        process=Process.sequential,
        verbose=True,
    )


def run_research(api_key, status_callback=None):
    if not api_key or not api_key.strip():
        raise ValueError("Bitte gib einen API-Key ein.")

    if status_callback:
        status_callback("Initialisiere Agenten...")
    crew = build_markdorf_pr_crew(api_key.strip())

    if status_callback:
        status_callback("Recherche läuft...")
    result = crew.kickoff()

    if status_callback:
        status_callback("Erstelle PDF-Report...")
    pdf_path = export_report_to_pdf(result)

    if status_callback:
        status_callback("Recherche abgeschlossen.")
    return str(result), str(pdf_path)


def get_app_icon_path():
    if getattr(sys, "frozen", False):
        base_path = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base_path = Path(__file__).resolve().parent
    return base_path / "assets" / "gruene_icon.svg"


class ResearchWorker(QObject):
    status_changed = Signal(str)
    result_ready = Signal(str, str)
    error_occurred = Signal(str)
    finished = Signal()

    def __init__(self, api_key):
        super().__init__()
        self.api_key = api_key

    def run(self):
        try:
            result, pdf_path = run_research(self.api_key, self.status_changed.emit)
            self.result_ready.emit(result, pdf_path)
        except Exception as exc:
            self.error_occurred.emit(f"{exc}\n\n{traceback.format_exc()}")
        finally:
            self.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gruene Themen Researcher - Ortsverband Markdorf und Umland")
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

        self.status_label = QLabel("Bereit")
        form_layout.addRow("Status:", self.status_label)
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
        self.worker = ResearchWorker(api_key)
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.status_changed.connect(self.set_status)
        self.worker.result_ready.connect(self.show_result)
        self.worker.error_occurred.connect(self.show_error)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.finished.connect(self.on_worker_finished)

        self.worker_thread.start()

    def set_status(self, status_text):
        self.status_label.setText(status_text)

    def show_result(self, result_text, pdf_path):
        self.result_text.setPlainText(result_text)
        self.result_text.append(f"\n\nPDF gespeichert unter: {pdf_path}")

    def show_error(self, error_text):
        self.set_status("Fehler bei der Recherche")
        self.result_text.setPlainText(error_text)

    def on_worker_finished(self):
        self.start_button.setEnabled(True)
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