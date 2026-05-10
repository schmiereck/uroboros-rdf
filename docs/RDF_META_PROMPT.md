# Meta-Prompt: Recursive Discovery Framework (RDF) v3 (final)

**Rolle:** Du bist Senior Software Architect für autonome Forschungs-Workflows.

**Ziel:** Lokale Python-Umgebung („Orchestrator"), die eine iterative
Experimentier-Schleife zwischen einem **Strategie-Agenten** (Gemini 2.5 Pro,
via Python SDK mit Context Caching) und einem **Implementierungs-Agenten**
(Claude Code, via CLI oder Claude Agent SDK (früher: Claude Code SDK)) steuert. Jede Iteration ist ein Git-Commit.
Token-sparsam, beobachtbar, resumable.

**Setup-Annahmen:**
- Der Orchestrator läuft im Root des Forschungs-Repositories. Pro Forschungs-
  thema = eigenes Git-Repo + eigenes Venv. Kein Multi-Lab-Konstrukt nötig.
- API-Keys (`GEMINI_API_KEY`) sind **global verfügbar** (Shell-Env), nicht
  per Projekt-`.env`.
- Claude Code authentifiziert sich über sein eigenes `claude login` und
  benötigt keinen Key im Code. Evtl. bei SDK anders.
- Der User ist immer in der Loop und kann Strg+C drücken.

---

## 1. Verzeichnisstruktur

```
<projekt-root>/                 # eigenes Git-Repo, eigenes Venv
├── orchestrator.py
├── config.toml
├── goal.md                     # User schreibt; agenten-readonly
├── current_state.md            # verdichtet; ≤ MAX_STATE_TOKENS
├── experiment_log.md           # append-only, YAML-Frontmatter pro Eintrag
├── .rdf_cache.json             # Hash + Gemini-Cache-Name (gitignored)
├── .gitignore                  # .rdf_cache.json, archive/*/raw/, __pycache__/
└── archive/
    ├── iter_001/
    │   ├── task.md             # Auftrag von Gemini an Claude
    │   ├── code/               # Generierter Code (cwd für Claude Code)
    │   ├── stdout.txt
    │   ├── stderr.txt
    │   ├── result.yaml
    │   └── raw/                # Optional große Daten (gitignored)
    └── iter_002/...
```

`goal.md` ist nach Initialisierung die Single Source of Truth für das Ziel.
Änderungen am `goal.md` → Cache-Invalidierung beim nächsten Start.

---

## 2. config.toml

```toml
[models]
strategy = "gemini-2.5-pro"
implementation_cli = "claude"     # Claude Code CLI

[claude_code]
# Default: granulare Tool-Freigabe.
allowed_tools = "Read,Write,Edit,Bash"
# Override: wenn true, wird --dangerously-skip-permissions gesetzt
# (User ist in der Loop und kann jederzeit Strg+C).
dangerously_skip_permissions = false

[limits]
max_iterations = 100
max_state_tokens = 8000           # Hard-Limit für current_state.md
strategy_timeout_sec = 180
experiment_timeout_sec = 14400    # 4 h Default; null = unbegrenzt
max_retries_on_parse_fail = 2
max_retries_on_state_too_long = 2

[cache]
ttl_hours = 6
# Pro hat min 32 768 Tokens. Bei kleinerem Stable-Payload wird gepaddet
# durch ausführlichen System-Prompt (siehe §5).
min_cache_tokens = 32768

[git]
auto_commit = true
session_branch = false            # bei Bedarf manuell anlegen

[ui]
verbose = true                    # rich-Output mit Tabellen/Diffs
```

---

## 3. Output-Schemata

### Strategie-Agent (Gemini)

Antwortet in freier Prosa **plus** finalem ` ```yaml ... ``` `-Block.
Reihenfolge erzwingt Chain-of-Thought (erst breit denken, dann fokussieren):

```yaml
analysis: |
  Kurze Lageeinschätzung – was wissen wir, was nicht.
open_questions:                  # vollständiger Möglichkeitsraum, 3-7 Stück
  - "Soll X auch in 2D laufen?"
  - "Brauchen wir n_runs > 1?"
  - "Lattice-Spacing variieren?"
chosen_direction: "Welche Frage gehen wir jetzt an, und warum"
hypothesis: "Einzeiler – wird Commit-Message"
rationale: "Warum diese Hypothese als nächstes"
task_for_implementer: |
  Konkreter, ausführbarer Arbeitsauftrag. Schlage IMMER den kleinsten Schritt
  vor, der die Hypothese validieren oder falsifizieren kann.
expected_outcome: "Was würde die Hypothese stützen / falsifizieren"
success_criteria:
  - "Mess-/Akzeptanzkriterien als Liste"
state_update: |
  Vorschlag für nächste current_state.md (≤ MAX_STATE_TOKENS).
```

### Implementierungs-Agent (Claude Code)

```yaml
status: "ok" | "experiment_failed" | "code_error"
artifacts:
  - "archive/iter_NNN/code/run.py"
metrics:
  some_value: 1.234
log_excerpt: "letzte ~20 Zeilen stdout"
experimenter_view: |
  Freie Beobachtungen des Implementers – was ist beim Hinschauen aufgefallen?
  Vermutete Ursachen, Auffälligkeiten, Vorschläge für Folge-Experimente.
  Wird in der nächsten Strategie-Iteration mitgelesen.
notes: "kurze technische Bemerkung an Strategie-Agent"
```

Bei Parse-Fehler: bis `max_retries_on_parse_fail` mit Korrektur-Prompt
nachfassen, dann Iteration als Fehler loggen.

---

## 4. Kern-Algorithmus

```
1. Init / Resume
   - Wenn kein .git: git init, initial commit (goal.md + Templates).
   - config.toml laden.
   - Letzte Iter-Nummer aus archive/ ableiten (höchste iter_NNN).
   - Cache-State laden (.rdf_cache.json).
   - Wenn current_state.md leer/Platzhalter UND keine Iterationen → BOOTSTRAP.

2. BOOTSTRAP (einmalig vor Iteration 1):
   - Spezieller Gemini-Call: liest nur goal.md, schreibt initiale
     current_state.md (Re-Statement des Ziels, bekannte Constraints,
     Startpunkt-Wissen). Kein Auftrag, keine Hypothese.
   - Eigener Git-Commit: "bootstrap: initial state from goal.md".

3. Pro Iteration N (N = letzte_iter + 1):
   a) STRATEGY (Gemini, Python SDK + Caching, siehe §5)
      - Stable-Payload (System-Prompt mit Methodik + goal.md + älterer Log)
        per CachedContent referenzieren.
      - Delta-Prompt enthält:
        * aktuelle current_state.md
        * letzte 3 Log-Einträge im Volltext
        * Iterations-Nummer N (explizit)
        * Optional: User-Hint aus [h]-Menü
        * Optional: gewählte Frage aus [o]-Menü
      - YAML parsen → archive/iter_NNN/task.md schreiben
        (enthält task_for_implementer + success_criteria).

   b) IMPLEMENT (Claude Code, subprocess)
      - cwd = archive/iter_NNN/code/ (existiert dann schon).
      - Befehl:
          claude -p "$(cat ../task.md)" \
                 --allowedTools "Read,Write,Edit,Bash" \
                 --output-format stream-json
        oder mit --dangerously-skip-permissions falls config das setzt.
      - Iter-Nummer N und Pfad-Konvention im Auftrag schon enthalten.
      - Timeout aus config.toml; Default 4 h, null = unbegrenzt.
      - stdout/stderr in archive/iter_NNN/ schreiben.
      - YAML aus letztem Output-Chunk parsen.

   c) VERIFY-IN-NEXT-STRATEGY (kein eigener Step)
      Die Bewertung der success_criteria erfolgt im NÄCHSTEN Strategie-
      Aufruf – Gemini sieht metrics + experimenter_view im Log und
      entscheidet, ob die Hypothese gestützt ist.

   d) UPDATE
      - Eintrag an experiment_log.md anhängen (YAML-Frontmatter +
        Markdown-Body, mit `---` getrennt).
      - state_update von Gemini → current_state.md ersetzen.
        Falls Tokenzahl > MAX_STATE_TOKENS:
          → bis max_retries_on_state_too_long mit "kürzer fassen" retry,
          → dann hart truncaten mit Marker `[truncated]` + Warning im Menü.

   e) GIT COMMIT (siehe §6)

   f) MENÜ (siehe §7)

4. Stop-Bedingungen
   - max_iterations erreicht
   - User wählt [n]
   - Gemini setzt hypothesis: "[CONVERGED] ..." UND alle
     success_criteria der Vor-Iteration erfüllt.
```

---

## 5. Context Caching (Gemini Pro)

**Wichtig:** Gemini 2.5 Pro hat **min 32 768 Tokens** für Cached Content.
Damit Caching ab Iteration 1 greift, wird der **System-Prompt** absichtlich
auf >32k Tokens aufgepumpt mit:

- ausführlicher Methodik-Beschreibung (wissenschaftliche Vorgehensweise,
  was "kleinster validierender Schritt" bedeutet, Beispiele für gute vs.
  schlechte Hypothesen),
- 2-3 Beispiel-Iterationen aus einem fiktiven Forschungslauf (Few-Shot),
- Domain-Glossar (vom User editierbar als `system_glossary.md` falls
  vorhanden – sonst leer).

**Stable-Payload (gecached):**
- System-Prompt + Methodik + Few-Shot
- `goal.md`
- `experiment_log.md` ohne die letzten 3 Einträge

**Delta-Payload (pro Call frisch):**
- aktuelle `current_state.md`
- letzte 3 Log-Einträge
- aktuelle Iter-Nummer
- optional: Hint, gewählte open_question

**Code-Skizze:**

```python
from google.generativeai import caching, GenerativeModel
import hashlib, json
from pathlib import Path

CACHE_FILE = Path(".rdf_cache.json")

def stable_payload(root: Path, system_prompt: str) -> str:
    goal = (root / "goal.md").read_text()
    log = (root / "experiment_log.md").read_text()
    entries = log.split("\n---\n")
    older = "\n---\n".join(entries[:-3]) if len(entries) > 3 else ""
    return f"{system_prompt}\n\n# GOAL\n{goal}\n\n# OLDER LOG\n{older}"

def get_or_create_cache(root: Path, model: str, ttl_seconds: int,
                        system_prompt: str, min_tokens: int):
    payload = stable_payload(root, system_prompt)
    h = hashlib.sha256(payload.encode()).hexdigest()[:16]
    state = json.loads(CACHE_FILE.read_text()) if CACHE_FILE.exists() else {}

    if state.get("hash") == h:
        try:
            return caching.CachedContent.get(state["cache_name"])
        except Exception:
            pass  # TTL abgelaufen, neu erstellen

    # Grobe Token-Schätzung: 1 Token ~ 4 chars
    if len(payload) < min_tokens * 4:
        return None  # zu klein, uncached senden

    cache = caching.CachedContent.create(
        model=model,
        contents=[payload],
        ttl=f"{ttl_seconds}s",
        display_name=f"rdf-{root.name}-{h}",
    )
    CACHE_FILE.write_text(json.dumps({
        "hash": h, "cache_name": cache.name
    }))
    return cache

def call_strategy(root: Path, delta_prompt: str, cfg) -> dict:
    cache = get_or_create_cache(
        root, cfg.strategy_model,
        cfg.cache_ttl_hours * 3600,
        SYSTEM_PROMPT_PADDED,
        cfg.min_cache_tokens,
    )
    if cache:
        model = GenerativeModel.from_cached_content(cache)
    else:
        model = GenerativeModel(cfg.strategy_model,
                                system_instruction=SYSTEM_PROMPT_PADDED)
    resp = model.generate_content(
        delta_prompt,
        request_options={"timeout": cfg.strategy_timeout_sec},
    )
    return parse_yaml_block(resp.text), resp.usage_metadata
```

---

## 6. Git-Integration

**Initialisierung:**
- Falls kein `.git/`: `git init`, initial commit der Templates.
- `.gitignore`: `.rdf_cache.json`, `archive/*/raw/`, `__pycache__/`,
  `*.pyc`, `.venv/`.

**Pro Iteration (auto_commit=true):**
- `git add -A`
- Commit-Message: `iter_NNN: <hypothesis>` (Einzeiler von Gemini).
- Bei vorherigem Hint: `[hint]` im Body und Hint-Text.
- Bei `[r]` Retry: **kein** Amend! Neuer Commit `iter_NNNr1: ...` –
  Audit-Trail bleibt intakt.
- Konvergenz: `git tag converged-NNN`.

**Status-Bericht zeigt zusätzlich:**
- `git log --oneline -5`
- `git diff --stat HEAD~1`

---

## 7. Human-in-the-Loop Menü

```
─────────── ITERATION 042 ABGESCHLOSSEN ───────────
Hypothese : <oneliner>
Status    : ok
Metriken  : { phase_velocity: 1.732, drift: 0.01 }
Tokens    : strategy 28.4k (cached 26.1k), impl 12.3k
Kosten    : ~$0.038 diese Iteration | $1.27 Session

Offene Fragen (von Gemini):
  1. Soll X auch in 2D laufen?
  2. Brauchen wir n_runs > 1?
  3. Lattice-Spacing variieren?

  [y] Nächste Iteration starten (Gemini wählt selbst)
  [o] Eine offene Frage als Fokus wählen (1-3)
  [h] Hint hinzufügen (manuelle Kurskorrektur)
  [r] Diese Iteration mit verändertem Hint wiederholen
  [d] git diff HEAD~1 zeigen
  [s] Status-Bericht ausführlich
  [n] Stoppen und speichern

>
```

---

## 8. Robustheit

- **YAML-Parse-Fehler**: bis `max_retries_on_parse_fail` mit Korrektur.
- **State zu lang**: bis `max_retries_on_state_too_long` mit "kürzer".
- **Subprocess-Timeout**: nur bei explizitem Limit; bei `null` wartet der
  Orchestrator unbegrenzt (User in Loop, kann Strg+C).
- **API-Errors (Gemini)**: exponential backoff, max 3 Retries.
- **Cache-Fehler**: silent fallback auf uncached.
- **Resume**: höchste vorhandene `iter_NNN` als Startpunkt; Cache wird
  per Hash validiert. Wenn der User per `git reset` zurückgesetzt hat,
  läuft der Orchestrator von dem zurückgesetzten Stand weiter.

**Cost-Tracking:**
- Pro Call: input_tokens, cached_tokens, output_tokens loggen.
- Cached-Tokens werden mit ~25% des Input-Preises gewichtet.
- Pro Iteration in `result.yaml`, kumulativ im Menü.

**Dry-Run-Modus** (`orchestrator.py --dry-run`):
- Mock-Agents geben deterministische Fake-YAML-Outputs.
- Keine API-Calls, kein Token-Verbrauch.
- Vollständiger Loop-Test inkl. Git-Commits.

---

## 9. Initiale Templates

**goal.md**:
```markdown
# Forschungsziel
<1-3 Absätze>

## Erfolgskriterien
- ...

## Beschränkungen
- ...
```

**current_state.md** (initial):
```markdown
# Aktueller Wissensstand
(noch nicht initialisiert – Bootstrap erforderlich)
```

**experiment_log.md** (initial):
```markdown
# Experiment Log
<!-- Append-only. Eintragstrenner: \n---\n zwischen YAML-Blöcken. -->
```

---

## 10. Erster Task

1. Lege `orchestrator.py` an, implementiere alles oben Beschriebene.
2. Lege `config.toml`, `.gitignore` und initiale Markdown-Templates an.
3. Implementiere Mock-Agents für `--dry-run`.
4. Verhalten:
   - `python orchestrator.py init` initialisiert das aktuelle Verzeichnis
     als Lab (git init, Templates), fragt interaktiv nach `goal.md`-Inhalt.
   - `python orchestrator.py run` läuft den Loop.
   - `python orchestrator.py run --dry-run` mit 3 Mock-Iterationen.
5. Gib mir am Ende ein **Abnahme-Signal**:
   - Liste aller erstellten Dateien
   - `git log --oneline` Ausgabe nach Dry-Run (Bootstrap + 3 Iter)
   - Liste aller Annahmen, die du beim Implementieren getroffen hast
     (besonders: System-Prompt-Padding-Inhalte, Few-Shot-Beispiele)
   - Hinweis auf TODOs, die ich noch füllen muss bevor der erste echte Lauf
     sinnvoll ist (z.B. Domain-Glossar, Methodik-Anpassungen).
