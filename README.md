# Wissens-Chatbot – Grundgerüst für unternehmensinterne KI-Wissensdatenbanken

Ein wiederverwendbares Grundgerüst (Template) für einen **unternehmensinternen KI-Chatbot**,
der Fragen auf Basis der eigenen Dokumentenablage beantwortet und Dokumente sowie
Ansprechpartner findet – DSGVO-konform, on-premise-fähig und mit **Benutzerrechten (RBAC)**.

Zielgruppe: deutsche Unternehmen und öffentlicher Dienst, bei denen Wissen in
Dateiablagen verstreut liegt und Dokumente mangels Auffindbarkeit doppelt erstellt werden.

---

## Kernprinzipien

1. **Datenhoheit:** Alle Komponenten sind selbst hostbar (Server in Deutschland / eigenes
   Rechenzentrum). Es gibt **keinen** verpflichtenden Cloud-Dienst außerhalb der EU.
2. **Rechte zuerst:** Jeder Dokument-Chunk trägt eine Zugriffsgruppe. Die Suche filtert
   **vor** der Antwortgenerierung nach den Gruppen des angemeldeten Benutzers –
   ein Benutzer kann also niemals Inhalte in einer Antwort sehen, die er nicht sehen darf.
3. **Austauschbare Bausteine:** LLM, Retrieval und Dokumenten-Quellen sind über
   Schnittstellen (Provider) abstrahiert und per Konfiguration wählbar.
4. **Ein Template, viele Unternehmen:** Pro Kunde wird nur `config/tenant.yaml`,
   `config/users.yaml` und der Dokumentenordner angepasst – kein Code.

---

## Architektur

```
┌────────────┐      ┌──────────────────────────────────────────────┐
│  Frontend  │      │                Backend (FastAPI)             │
│  Chat-UI   │◄────►│                                              │
│ (statisch) │ JWT  │  Auth (JWT) ──► RBAC-Filter                  │
└────────────┘      │                    │                         │
                    │  Ingestion ──► Chunking ──► Index (BM25/     │
                    │  (PDF/DOCX/        │        Vektor-DB)       │
                    │   TXT/MD)          ▼                         │
                    │              Retrieval (nur erlaubte Chunks) │
                    │                    │                         │
                    │                    ▼                         │
                    │  LLM-Provider (Ollama lokal / EU-API /      │
                    │  extraktiver Fallback ohne LLM)              │
                    └──────────────────────────────────────────────┘
```

- **Ingestion:** liest Dokumente aus einem oder mehreren Ablageorten. Der oberste
  Ordnername ist die Zugriffsgruppe (z. B. `allgemein`, `personal`, `finanzen`).
  Unterstützte Formate: **PDF, Word (.docx), PowerPoint (.pptx, inkl. Notizen),
  Excel (.xlsx), CSV, HTML, Markdown, Text**.
- **Retrieval:** Standard ist BM25 (rein Python, läuft überall sofort).
  Optional **Hybrid-Suche** (BM25 + semantische Embeddings mit einem lokalen,
  mehrsprachigen Modell): findet auch Umschreibungen wie „freie Tage" →
  Urlaubsregelung. Aktivieren:
  `pip install -r backend/requirements-embeddings.txt` und in `config/tenant.yaml`
  `retrieval.provider: "hybrid"` setzen. Das Embedding-Modell
  (`intfloat/multilingual-e5-small`) wird beim ersten Start einmalig
  heruntergeladen und läuft danach komplett lokal auf der CPU.
  Berechnete Embeddings landen in einer **lokalen Vektor-Datenbank**
  (SQLite, `data/vektoren.sqlite`): Nach einem Neustart werden nur neue oder
  geänderte Dokumente neu berechnet – der Start bleibt auch bei großen
  Ablagen schnell.
- **Streaming:** Antworten erscheinen Wort für Wort, sobald das LLM liefert –
  die Quellen stehen sofort, noch bevor die Antwort fertig formuliert ist.
- **LLM:** Standard ist der **extraktive Modus** (keinerlei LLM nötig – gibt die besten
  Fundstellen strukturiert zurück). Für echte generierte Antworten:
  - `ollama` – lokales LLM auf eigenem Server (empfohlen für maximale Datenhoheit)
  - `openai_compatible` – jeder OpenAI-kompatible EU-Endpunkt (z. B. IONOS AI Model Hub,
    STACKIT, Azure OpenAI mit EU-Region – je nach Compliance-Anforderung des Kunden)

---

## Schnellstart am eigenen Rechner

Voraussetzung: Python 3.11+ ([python.org](https://www.python.org/downloads/),
bei Windows im Installer „Add python to PATH" anhaken).

> **Windows-Hinweis:** Das Projekt in einen **kurzen Pfad** legen, z. B.
> `C:\Projekte\chatbot` – nicht tief verschachtelt auf dem Desktop. Windows
> begrenzt Pfade auf 260 Zeichen; bei zu langen Pfaden bricht die Installation
> mit „No such file or directory" ab. Alternativ
> [Windows Long Paths aktivieren](https://pip.pypa.io/warnings/enable-long-paths).

```bash
# Linux / macOS                 # Windows (Eingabeaufforderung)
./start.sh                      start.bat
```

Das Skript richtet beim ersten Start automatisch alles ein (virtuelle Umgebung,
Abhängigkeiten) und startet den Server. Dann im Browser: **http://localhost:8000**

### Privat-Modus: eigene Dokumente, kein Login

Zum persönlichen Ausprobieren mit der eigenen Ablage – ohne Benutzerverwaltung:

```bash
# Linux / macOS
DOCUMENTS_PATH="$HOME/Dokumente" ./start.sh privat

# Windows
set DOCUMENTS_PATH=C:\Users\DeinName\Dokumente
start.bat privat
```

Der Chatbot indiziert dann den angegebenen Ordner (inkl. Unterordner;
`.pdf`, `.docx`, `.pptx`, `.xlsx`, `.csv`, `.html`, `.txt`, `.md`)
und ist sofort ohne Anmeldung nutzbar.
Alle Einstellungen dazu: `config/tenant.privat.yaml`.
**Es verlässt dabei nichts deinen Rechner** – Indizierung und Suche laufen
komplett lokal.

**Mehrere Ablageorte gleichzeitig** (unabhängig vom Projektordner) trägst du
in der tenant.yaml als Liste ein – Windows-Pfade mit `/` schreiben:

```yaml
dokumente_pfad:
  - "C:/Users/DeinName/Dokumente"
  - "C:/Ablage/Vertraege"
  - "data/documents"
```

**Quellen sind klickbar:** Ein Klick auf eine Quelle öffnet das Original
(PDF/Text im Browser, Word als Download), „Pfad kopieren" legt den
Originalpfad in die Zwischenablage. Beides ist RBAC-geprüft – Benutzer
können nur Dokumente ihrer eigenen Gruppen abrufen.

Demo-Benutzer (siehe `config/users.yaml`):

| Benutzer   | Passwort      | Gruppen                  |
|------------|---------------|--------------------------|
| `admin`    | `admin123`    | alle (`*`)               |
| `mmuster`  | `demo123`     | `allgemein`, `personal`  |
| `gast`     | `gast123`     | `allgemein`              |

> `mmuster` findet z. B. Personaldokumente, `gast` nicht – gleiche Frage, andere Antwort.

## Schnellstart (Docker)

```bash
docker compose up --build
# optional mit lokalem LLM:
docker compose --profile llm up --build
```

---

## Neues Unternehmen aufsetzen (Template-Nutzung)

Damit dieses Repository als Vorlage dient: auf GitHub unter
**Settings → General → Template repository** den Haken setzen. Danach kann
für jedes Unternehmen mit **„Use this template"** ein eigenes Repository
erzeugt werden.

1. Repository als Vorlage klonen (`Use this template` / Fork).
2. `config/tenant.yaml` anpassen: Name, LLM-Provider, Ansprechpartner, Chunking.
3. `config/users.yaml` anlegen – Hashes erzeugen mit:
   `python backend/scripts/hash_password.py`
   (später ersetzbar durch LDAP/Active-Directory/Keycloak-Anbindung).
4. Dokumente nach `data/documents/<zugriffsgruppe>/` legen.
5. Starten – der Index wird beim Start aufgebaut. Neue oder geänderte
   Dateien werden danach **automatisch** erkannt und eingelesen
   (Prüfintervall: `auto_reindex_sekunden` in der tenant.yaml, Standard 30 s;
   0 schaltet es ab, sofort geht per `POST /api/admin/reindex`).

**Feedback-Auswertung:** Jede Antwort hat 👍/👎-Buttons. Die Bewertungen
landen in `data/feedback.jsonl` (nicht im Git) und sind für Admins unter
`/api/admin/feedback` abrufbar – so siehst du, wo die Wissensbasis Lücken hat.

**Admin-Dashboard:** Unter **http://localhost:8000/admin** (Link erscheint im
Chat-Kopf für Admins) gibt es eine Übersichtsseite: Dokument-/Index-Status,
Zugriffsgruppen, Ablageorte, Feedback-Auswertung und ein Reindex-Button.

**Oberfläche:** Beispielfragen als klickbare Chips (konfigurierbar über
`beispiel_fragen` in der tenant.yaml), Hell-/Dunkel-Modus (🌓 im Kopf),
formatierte Antworten (Fett/Listen aus LLM-Antworten werden dargestellt).

## Konfiguration

Zentrale Datei: `config/tenant.yaml` (Pfad überschreibbar via `TENANT_CONFIG`).
Geheimnisse (API-Keys, JWT-Secret) kommen **nur** aus Umgebungsvariablen – siehe `.env.example`.

## API-Überblick

| Methode | Pfad                  | Beschreibung                                  |
|---------|-----------------------|-----------------------------------------------|
| POST    | `/api/auth/login`     | Login, liefert JWT (entfällt im Privat-Modus) |
| GET     | `/api/auth/me`        | Eigene Rollen/Gruppen                         |
| POST    | `/api/chat`           | Frage stellen (+ Verlauf) → Antwort + Quellen |
| POST    | `/api/chat/stream`    | Wie `/api/chat`, Antwort als NDJSON-Stream    |
| GET     | `/api/documents/search?q=` | Reine Dokumentsuche (ohne LLM)           |
| GET     | `/api/documents/file?name=` | Originaldatei einer Quelle (RBAC-geprüft) |
| POST    | `/api/feedback`       | 👍/👎-Bewertung einer Antwort speichern        |
| GET     | `/api/admin/feedback` | Gesammeltes Feedback einsehen (Rolle `admin`) |
| POST    | `/api/admin/reindex`  | Index sofort neu aufbauen (Rolle `admin`)     |
| GET     | `/api/health`         | Statusprüfung                                 |

## Tests

```bash
cd backend && python -m pytest
```

## DSGVO & Compliance

Siehe [`docs/DSGVO.md`](docs/DSGVO.md) – Hosting, Auftragsverarbeitung, Löschkonzept,
Protokollierung und was vor einem Produktivbetrieb noch zu klären ist.

## Roadmap zum Produkt

Siehe [`docs/ROADMAP.md`](docs/ROADMAP.md) – vom Prototyp zu Pilotkunde und Produkt
(Vektor-Suche, SSO/AD-Anbindung, Konnektoren für SharePoint/Netzlaufwerke, Mandantenfähigkeit).
