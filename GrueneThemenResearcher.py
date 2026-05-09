import os
from datetime import datetime
from pathlib import Path
from textwrap import wrap

from crewai import Agent, Task, Crew, Process, LLM
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def export_report_to_pdf(report_text, output_dir="reports"):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_path = output_path / f"finaler_report_{timestamp}.pdf"

    pdf = canvas.Canvas(str(pdf_path), pagesize=A4)
    page_width, page_height = A4
    left_margin = 50
    top_margin = page_height - 50
    bottom_margin = 50
    line_height = 14
    max_chars = 95

    text_object = pdf.beginText(left_margin, top_margin)
    text_object.setFont("Helvetica-Bold", 16)
    text_object.textLine("Finaler Redaktionsreport")
    text_object.setFont("Helvetica", 10)
    text_object.textLine(f"Erstellt am: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
    text_object.textLine("")
    text_object.setFont("Helvetica", 11)

    for paragraph in str(report_text).splitlines():
        wrapped_lines = wrap(paragraph, width=max_chars) or [""]
        for line in wrapped_lines:
            if text_object.getY() <= bottom_margin:
                pdf.drawText(text_object)
                pdf.showPage()
                text_object = pdf.beginText(left_margin, top_margin)
                text_object.setFont("Helvetica", 11)
            text_object.textLine(line)

    pdf.drawText(text_object)
    pdf.save()
    return pdf_path

# 1. API-Konfiguration
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("Bitte setze die Umgebungsvariable GOOGLE_API_KEY.")

# Optional ueberschreibbar per Umgebungsvariablen.
flash_model = os.getenv("GEMINI_FLASH_MODEL", "gemini/gemini-2.5-flash")
pro_model = os.getenv("GEMINI_PRO_MODEL", "gemini/gemini-2.5-flash")

# Definition der "Gehirne"
# Flash für Geschwindigkeit und einfache Aufgaben
gemini_flash = LLM(
    model=flash_model,
    api_key=api_key,
    temperature=0.7
)

# Pro für Tiefenanalyse und politische Präzision
gemini_pro = LLM(
    model=pro_model,
    api_key=api_key,
    temperature=0.3
)

# 2. Die Agenten-Definitionen

researcher = Agent(
    role='Lokal-Researcher Markdorf',
    goal='Finde 3 aktuelle, brisante politische Themen in Markdorf und dem Bodenseekreis.',
    backstory="""Du bist der Infopool des Ortsverbands. Du scannst Lokalnachrichten, 
    Gemeinderatsprotokolle und regionale Mitteilungen. Dein Fokus liegt auf absoluter 
    Aktualität und lokaler Relevanz für grüne Kernthemen.""",
    llm=gemini_flash,
    verbose=True
)

expert = Agent(
    role='Grüner Grundsatz-Experte',
    goal='Liefere fundierte Hintergründe und die offizielle grüne Position zu den Themen.',
    backstory="""Du bist der inhaltliche Anker. Du verknüpfst lokale Ereignisse mit dem 
    Landesprogramm BW und Bundesvorgaben. Du lieferst die harten Fakten und Argumente, 
    warum ein Thema aus grüner Sicht relevant ist.""",
    llm=gemini_pro,
    verbose=True
)

social_media = Agent(
    role='Content Manager Markdorf',
    goal='Erstelle kanalgenaue Entwürfe für Instagram, Facebook, Webseite und Messenger.',
    backstory="""Du bist die Stimme des Ortsverbands nach außen. Du schreibst packend, 
    nahbar und nutzt regionale Schlagworte. Du passt Ton, Länge und Struktur 
    an den jeweiligen Kanal an und erstellst aus trockenen Fakten 
    emotionale und aktivierende Inhalte für Social Media, Website und Direktnachrichten.""",
    llm=gemini_flash,
    verbose=True
)

compliance_officer = Agent(
    role='Politischer Chef-Redakteur & Strategie-Berater',
    goal='Prüfe Posts auf Parteilinie, schreibe sie ggf. um und begründe Änderungen.',
    backstory="""Du bist die letzte Instanz. Du stellst sicher, dass kein Post gegen die 
    Linie von Bund, Land oder Kreis verstößt. Du polierst die Texte diplomatisch auf 
    und erklärst deine Korrekturen, um das Team strategisch zu schulen.""",
    llm=gemini_pro,
    verbose=True
)

# 3. Die Aufgaben-Definitionen

task_research = Task(
    description='Recherchiere 3 aktuelle kommunalpolitische Themen in Markdorf (Woche: Mai 2026).',
    expected_output='Eine Liste mit 3 News-Themen inkl. Quellenangabe oder kurzer Zusammenfassung.',
    agent=researcher
)

task_background = Task(
    description='Wähle das relevanteste Thema aus und ergänze es um grüne Hintergründe und Argumente.',
    expected_output='Ein inhaltliches Briefing mit Fakten-Check und Bezug zum grünen Programm.',
    agent=expert,
    context=[task_research]
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
    context=[task_background]
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
    context=[task_creation]
)

# 4. Die Crew zusammenstellen
markdorf_pr_crew = Crew(
    agents=[researcher, expert, social_media, compliance_officer],
    tasks=[task_research, task_background, task_creation, task_compliance],
    process=Process.sequential,
    verbose=True
)

# 5. Ausführung
print("### Das PR-Team startet die Arbeit für Markdorf... ###")
result = markdorf_pr_crew.kickoff()
pdf_path = export_report_to_pdf(result)

print("\n\n################################")
print("## ERGEBNIS DER REDAKTIONSSITZUNG ##")
print("################################\n")
print(result)
print(f"\nPDF gespeichert unter: {pdf_path}")