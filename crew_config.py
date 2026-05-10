import os
from crewai import Agent, Task, Crew, Process, LLM


def create_task(description, expected_output, agent, context=None):
    """
    Erstellt eine Task für einen Agenten mit Beschreibung, erwartetem Output und optionalem Kontext.
    """
    return Task(description=description, expected_output=expected_output, agent=agent, context=context or [])


def build_markdorf_pr_crew(api_key):
    """
    Erstellt und konfiguriert die Crew von Agenten für die Recherche und Erstellung des Reports.
    """
    flash_model = os.getenv("GEMINI_FLASH_MODEL", "gemini/gemini-2.5-flash")
    pro_model = os.getenv("GEMINI_PRO_MODEL", "gemini/gemini-2.5-pro")

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
        goal="Erzeuge aus dem finalen Report ein modernes, visuell klares Markdown-Layout mit sinnvollen Bildhinweisen.",
        backstory="""Du bist Art Director fuer politische Kommunikation. Du strukturierst Inhalte lesefreundlich,
    definierst klare Abschnittstitel und gibst gezielte Bildhinweise fuer lokale, nachhaltige und gruene Themen.
    Dein Stil wirkt modern, ruhig und glaubwuerdig fuer den Ortsverband Markdorf und Umland.""",
        llm=gemini_pro,
        verbose=True,
    )

    task_research = create_task(
        description="Recherchiere 3 aktuelle kommunalpolitische Themen in Markdorf und Umland (Woche: Mai 2026). Stelle sicher, dass jedes Thema klar voneinander abgrenzbar und lokal relevant ist.",
        expected_output="Eine Liste mit 3 News-Themen inkl. Quellenangabe oder kurzer Zusammenfassung, getrennt nach Thema.",
        agent=researcher,
    )

    task_background = create_task(
        description="Vertiefe jedes der 3 recherchierten Themen und ergänze sie um grüne Hintergründe, Argumente und klare Relevanz für Markdorf und Umland.",
        expected_output="Ein inhaltliches Briefing zu den 3 Themen mit Fakten-Check, grünem Bezug und jeweils einem kurzen Fokusargument.",
        agent=expert,
        context=[task_research],
    )

    task_creation = create_task(
        description="""Erstelle auf Basis des Briefings zu den 3 Themen für jedes Thema je einen Instagram-, Facebook-, Website- und Messenger-Beitrag.
    Gliedere die Ausgabe in Kapitel: THEMA 1, THEMA 2, THEMA 3.
    Passe Ton, Länge und Call-to-Action an den jeweiligen Kanal an.""",
        expected_output="""Format:
    ---
    THEMA 1:
    INSTAGRAM: [Text inkl. Hashtags und Bildidee]
    FACEBOOK: [Text inkl. Call-to-Action]
    WEBSEITE: [Kurzartikel mit Ueberschrift, Teaser und Haupttext]
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

    task_compliance = create_task(
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

    task_layout = create_task(
        description="""Layoutiere den finalen Report fuer einen modernen Markdown-Report in einem klaren Stil passend zu Gruene Markdorf.
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