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

- **Ingestion:** liest Dokumente aus `data/documents/<gruppe>/...`. Der oberste
  Ordnername ist die Zugriffsgruppe (z. B. `allgemein`, `personal`, `finanzen`).
- **Retrieval:** Standard ist BM25 (rein Python, läuft überall sofort). Eine
  Vektor-Suche (Embeddings) kann als Provider ergänzt werden, ohne die API zu ändern.
- **LLM:** Standard ist der **extraktive Modus** (keinerlei LLM nötig – gibt die besten
  Fundstellen strukturiert zurück). Für echte generierte Antworten:
  - `ollama` – lokales LLM auf eigenem Server (empfohlen für maximale Datenhoheit)
  - `openai_compatible` – jeder OpenAI-kompatible EU-Endpunkt (z. B. IONOS AI Model Hub,
    STACKIT, Azure OpenAI mit EU-Region – je nach Compliance-Anforderung des Kunden)

---

## Schnellstart (lokal, ohne Docker)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Demo-Konfiguration und Demo-Dokumente liegen bereits im Repo
uvicorn app.main:app --reload
```

Dann im Browser: **http://localhost:8000**

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

1. Repository als Vorlage klonen (`Use this template` / Fork).
2. `config/tenant.yaml` anpassen: Name, LLM-Provider, Ansprechpartner, Chunking.
3. `config/users.yaml` anlegen – Hashes erzeugen mit:
   `python backend/scripts/hash_password.py`
   (später ersetzbar durch LDAP/Active-Directory/Keycloak-Anbindung).
4. Dokumente nach `data/documents/<zugriffsgruppe>/` legen.
5. Starten – der Index wird beim Start automatisch aufgebaut
   (neu einlesen im Betrieb: `POST /api/admin/reindex`, nur Rolle `admin`).

## Konfiguration

Zentrale Datei: `config/tenant.yaml` (Pfad überschreibbar via `TENANT_CONFIG`).
Geheimnisse (API-Keys, JWT-Secret) kommen **nur** aus Umgebungsvariablen – siehe `.env.example`.

## API-Überblick

| Methode | Pfad                  | Beschreibung                                  |
|---------|-----------------------|-----------------------------------------------|
| POST    | `/api/auth/login`     | Login, liefert JWT                            |
| GET     | `/api/auth/me`        | Eigene Rollen/Gruppen                         |
| POST    | `/api/chat`           | Frage stellen → Antwort + Quellen             |
| GET     | `/api/documents/search?q=` | Reine Dokumentsuche (ohne LLM)           |
| POST    | `/api/admin/reindex`  | Index neu aufbauen (Rolle `admin`)            |
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
