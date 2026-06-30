from llm.prompts.general_guidance import GENERAL_GUIDANCE

STEP_CONTEXT: dict[str, str] = {
    "assignments_summary": (
        "Zwischenschritt: Zusammenfassung der Zuordnungsänderungen. "
        "Die Eingabe enthält entfernte und/oder hinzugefügte Zuordnungen "
        "(oder Vorher/Nachher-Tabellen). Die Ausgabe listet die relevantesten "
        "Änderungen pro Mitarbeiter mit Effektbewertung."
    ),
    "statistics_summary": (
        "Zwischenschritt: Zusammenfassung der aggregierten Diff-Statistiken. "
        "Die Eingabe enthält berechnete Kennzahlen der Planänderung. "
        "Die Ausgabe fasst die relevantesten statistischen Veränderungen zusammen."
    ),
    "assessment": (
        "Abschlussbewertung: Die Eingabe kombiniert die Zuordnungszusammenfassung "
        "und die statistische Zusammenfassung. Die Ausgabe ist die finale "
        "Akzeptanzbewertung mit Begründung."
    ),
    "direct_assessment": (
        "Direktbewertung ohne Zwischenschritte: Die Eingabe enthält nur die "
        "Zuordnungsänderungen. Die Ausgabe ist die finale Akzeptanzbewertung "
        "mit Begründung."
    ),
}

CLARITY_JUDGE_PROMPT = f"""
Du bist ein unabhängiger Gutachter für LLM-generierte Texte im Kontext der
Personalkalenderplanung bei Incluedo GmbH.

Bewerte ausschließlich die **Klarheit** der generierten Ausgabe – unabhängig davon,
ob sie inhaltlich korrekt ist.

{GENERAL_GUIDANCE}

## Pipeline-Schritt

{{step_context}}

**Schrittname:** {{step_name}}

## Eingabe (an das generierende LLM)

{{input_text}}

## Ausgabe (vom generierenden LLM)

{{output_text}}

## Bewertungskriterien für Klarheit (0–10)

- **0–2:** Unverständlich, widersprüchlich formuliert oder ohne erkennbare Struktur.
- **3–4:** Schwer lesbar; zentrale Aussagen sind nur mit Mühe zu entnehmen.
- **5–6:** Grundsätzlich verständlich, aber unklare Formulierungen oder fehlende Struktur.
- **7–8:** Klar und gut strukturiert; Fachpersonal kann die Aussagen schnell erfassen.
- **9–10:** Sehr klar, präzise und übersichtlich; keine unnötige Redundanz.

Gib eine Ganzzahl von 0 bis 10 und eine kurze Begründung (1–2 Sätze).
"""

COHERENCE_JUDGE_PROMPT = f"""
Du bist ein unabhängiger Gutachter für LLM-generierte Texte im Kontext der
Personalkalenderplanung bei Incluedo GmbH.

Bewerte ausschließlich die **Kohärenz zwischen Eingabe und Ausgabe** – ob die
Ausgabe logisch aus der Eingabe folgt und durch diese belegbar ist.

{GENERAL_GUIDANCE}

## Pipeline-Schritt

{{step_context}}

**Schrittname:** {{step_name}}

## Eingabe (an das generierende LLM)

{{input_text}}

## Ausgabe (vom generierenden LLM)

{{output_text}}

## Bewertungskriterien für Kohärenz (0–10)

- **0–2:** Ausgabe widerspricht der Eingabe oder enthält offensichtliche Halluzinationen.
- **3–4:** Wesentliche Eingabefakten werden ignoriert oder falsch dargestellt.
- **5–6:** Teilweise konsistent; einige Aussagen sind schwach belegt oder unvollständig.
- **7–8:** Gut belegbar; die meisten Aussagen folgen direkt aus der Eingabe.
- **9–10:** Vollständig konsistent; keine unbelegten Behauptungen, keine kritischen Auslassungen.

Gib eine Ganzzahl von 0 bis 10 und eine kurze Begründung (1–2 Sätze).
"""
