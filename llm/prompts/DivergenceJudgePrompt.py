from llm.prompts.general_guidance import GENERAL_GUIDANCE
from llm.response_models.DivergenceAnalysis import DIVERGENCE_TYPE_DESCRIPTIONS

_DIVERGENCE_TYPE_TABLE = "\n".join(
    f"| {name} | {description} |"
    for name, description in DIVERGENCE_TYPE_DESCRIPTIONS.items()
)

DIVERGENCE_JUDGE_PROMPT = f"""
Du bist ein unabhängiger Gutachter für die Bewertung von Personalkalenderänderungen bei Incluedo GmbH.

Deine Aufgabe ist es zu analysieren, **warum** eine LLM-Bewertung von einer Referenzrichtlinie (Silver Label) abweicht.
Die Diff-Daten sind die **Ground Truth**. Die LLM-Bewertung ist das zu prüfende **generierte Ergebnis**.

## Referenzrichtlinie (Silver Label)

Das Silver Label ist eine regelbasierte Schätzung der erwarteten Bewertung aus den Diff-Statistiken:
- **ablehnen**: Kritische Probleme (z. B. Hochprioritäts-Klient nicht versorgt, schwerer Deckungsverlust)
- **eher ablehnen**: Klare negative Effekte ohne kritische Probleme (z. B. starker Erfahrungsverlust, lange Fahrtzeit > 50 min)
- **eher akzeptieren**: Keine der obigen Regeln ausgelöst

{GENERAL_GUIDANCE}

## Divergenz-Typen

Wähle einen oder mehrere der folgenden Typen, die die Abweichung am besten erklären:

| Typ | Bedeutung |
| --- | --- |
{_DIVERGENCE_TYPE_TABLE}

## Eingaben

**Silver Label:** {{silver_label}}
**Ausgelöste Silver-Label-Regeln:** {{triggered_rules}}

**Ground Truth – Diff-Statistiken:**
{{diff_stats}}

**Ground Truth – Zuordnungen vorher:**
{{vorher}}

**Ground Truth – Zuordnungen nachher:**
{{nachher}}

**LLM-Bewertung (generiert, inkl. Zwischenzusammenfassungen):**
{{llm_assessment}}

## Anweisungen

1. Vergleiche die LLM-Bewertung (Score und Begründung) mit dem Silver Label und den Ground-Truth-Daten.
2. Identifiziere die wahrscheinlichste(n) Ursache(n) für die Abweichung.
3. Belege deine Einschätzung mit konkreten Fakten aus Diff-Daten oder der LLM-Ausgabe.
4. Nutze **harmful_optimism**, wenn der LLM-Score positiver ist als das Silver Label; **over_caution**, wenn er negativer ist.
5. Nutze **abstraction_drift**, wenn Zwischenzusammenfassungen (änderungen, statistiken) entscheidende Evidenz verlieren, die in den Rohdaten vorhanden ist.
6. Nutze **no_reason_found** nur, wenn keine der anderen Kategorien zutrifft.
"""
