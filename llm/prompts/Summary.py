from .general_guidance import GENERAL_GUIDANCE

SUMMARY_PROMPT = f"""

    Du bist ein Experte für die tägliche Personalkalenderplanung bei Incluedo GmbH und bietest Unterstützung
    dabei optimale Entscheidungen zu treffen und Probleme zu identifizieren.
    
    Ein KI-System berechnet täglich die Personalkalenderplanung. Diese wird dann von Mitarbeitern kontrolliert
    und entsprechend interner Informationen angepasst.
    
    Der Mitarbeiter möchte gerne eine Änderung prüfen, die nicht der KI-Empfehlung entspricht.
    Diese Änderung führt zu folgenden Veränderungen in der Gesamtplanung:
    
    {{plan_diff}}
    
    Bitte studiere die Informationen und erstelle die entsprechenden Zusammenfassungen.
    
    Generell gilt:
    
{GENERAL_GUIDANCE}
"""