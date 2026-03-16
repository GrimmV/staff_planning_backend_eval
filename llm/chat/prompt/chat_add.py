CHAT_ADD_PROMPT = """

    Dieser prompt, gemeinsam mit den änderungen und statistiken, wurde genutzt, um die Bewertung und Erläuterungen zu erzeugen.
    
    - Deine Aufgabe ist, eine Bewertung der Lage abzugeben. 
    - Antworte in ganzen Sätzen aber schreib nicht mehr als notwendig, um die Lage darzustellen.
    
    Priorisierung der Eigenschaften:
    
    1. Anzahl der versorgten Klienten
    2. Anzahl der hoch priorisierten Klienten
    3. Durchschnittliche Fahrtzeit und Ausreißer mit hoher Fahrtzeit
    4. Mitarbeiter kann Klienten den ganzen Tag betreuen
    4. Erfahrung mit Klienten
    4. Erfahrung mit Schule
    4. Mitarbeiter kann Klienten für alle Vertretungstage betreuen
    
    Folgende Fragen sollst du beantworten (und nichts anderes):
    
    - Welche Konsequenzen hat die Veränderung insgesamt? -> Gibt es Besondere Beobachtungen?
    - Welche Konsequenzen hat die Veränderung auf individueller Zuordnungsebene? -> Gibt es hinzugefügte Zuordnungen die signifikant schlechtere/bessere Werte aufweisen, als die entfernten?
    
    Bedenke, die Änderungen werden sogut wie immer etwas schlechter sein, als die ursprüngliche Planung. Daher solltest du nicht zu kritisch sein. Dennoch sollten (eher) Ablehnungen eine Option sein.
"""
