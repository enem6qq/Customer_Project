# Roadmap: Vom Prototyp zum Produkt

## Phase 0 – Prototyp (dieses Repository) ✅

- RAG-Grundgerüst: Ingestion → Chunking → BM25-Suche → Antwort mit Quellen
- Benutzerrechte (RBAC) auf Chunk-Ebene, Filterung vor der LLM-Anfrage
- Austauschbare LLM-Provider (extraktiv / Ollama lokal / EU-Endpunkt)
- Chat-Oberfläche, Ansprechpartner-Vorschläge, Docker-Setup, Tests

## Phase 1 – Überzeugende Demo (1–2 Wochen)

- ✅ **Hybrid-Suche:** BM25 + Embeddings (`intfloat/multilingual-e5-small`,
  läuft lokal) mit Reciprocal Rank Fusion – bessere Treffer bei Umschreibungen
- ✅ **Privat-Modus:** lokale Einzelnutzung ohne Login (`./start.sh privat`),
  eigener Dokumentenordner per `DOCUMENTS_PATH`
- ✅ Ollama-Anbindung mit automatischem Fallback (per Test abgesichert)
- ✅ Lokales LLM in der Praxis erprobt (Ollama, `llama3.1:8b`)
- ✅ Dokument-Download/-Vorschau direkt aus der Quellenliste (+ Pfad kopieren)
- ✅ Gesprächsverlauf (Rückfragen im Kontext)
- ✅ Office-Formate: PowerPoint, Excel, CSV, HTML (zusätzlich zu PDF/Word/Text)
- ✅ Automatischer Reindex (Datei-Wächter), Feedback-Buttons 👍/👎
- ✅ Admin-Dashboard (/admin): Status, Feedback-Auswertung, Reindex
- ✅ UI: Beispielfragen-Chips, Dark Mode, formatierte Antworten
- ✅ Streaming-Antworten (Wort für Wort, Quellen sofort)
- ✅ Lokale Vektor-Datenbank (SQLite-Embedding-Cache, schneller Neustart)
- Echte Kundendokumente eines Pilotpartners einspielen (anonymisiert testen)

## Phase 2 – Pilotkunde (4–8 Wochen)

- **SSO:** Anbindung an Active Directory / LDAP / Keycloak (OIDC);
  Zugriffsgruppen aus AD-Gruppen statt Ordnernamen
- **Konnektoren:** Netzlaufwerke (SMB), SharePoint, E-Mail-Archive –
  inkl. Übernahme der Original-Berechtigungen (ACL-Spiegelung)
- Server-Vektor-Datenbank (Qdrant oder pgvector) für sehr große Bestände
  und mehrere Backend-Instanzen (die lokale SQLite-Vektor-DB ist bis in den
  sechsstelligen Chunk-Bereich völlig ausreichend)
- Audit-Log, Feedback-Buttons („Antwort hilfreich?") zur Qualitätsmessung

## Phase 3 – Produkt / Mehrmandantenfähigkeit

- Ein Deployment pro Kunde (empfohlen für öffentliche Auftraggeber) ODER
  echte Mandantenfähigkeit mit strikter Datentrennung
- Admin-Oberfläche: Benutzer, Gruppen, Quellen, Index-Status
- Betriebspaket: Monitoring, Backups, Update-Prozess, SLA
- Compliance-Paket: AVV-Vorlagen, TOMs, DSFA-Vorlage, BSI-C5-konformes Hosting

## Bewusste Nicht-Ziele des Prototyps

- Kein eigenes Training von Modellen (RAG reicht und ist wartbar)
- Keine Schreibzugriffe auf Quellsysteme (nur Lesen/Finden)
- Keine Cloud-Pflicht
