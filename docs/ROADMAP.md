# Roadmap: Vom Prototyp zum Produkt

## Phase 0 – Prototyp (dieses Repository) ✅

- RAG-Grundgerüst: Ingestion → Chunking → BM25-Suche → Antwort mit Quellen
- Benutzerrechte (RBAC) auf Chunk-Ebene, Filterung vor der LLM-Anfrage
- Austauschbare LLM-Provider (extraktiv / Ollama lokal / EU-Endpunkt)
- Chat-Oberfläche, Ansprechpartner-Vorschläge, Docker-Setup, Tests

## Phase 1 – Überzeugende Demo (1–2 Wochen)

- Lokales LLM anbinden (Ollama, z. B. `llama3.1:8b` oder ein deutsches Modell)
- **Hybrid-Suche:** BM25 + Embeddings (z. B. `intfloat/multilingual-e5-base`,
  läuft lokal) mit Reranking – deutlich bessere Treffer bei deutschen Fragen
- Dokument-Download/-Vorschau direkt aus der Quellenliste
- Echte Kundendokumente eines Pilotpartners einspielen (anonymisiert testen)

## Phase 2 – Pilotkunde (4–8 Wochen)

- **SSO:** Anbindung an Active Directory / LDAP / Keycloak (OIDC);
  Zugriffsgruppen aus AD-Gruppen statt Ordnernamen
- **Konnektoren:** Netzlaufwerke (SMB), SharePoint, E-Mail-Archive –
  inkl. Übernahme der Original-Berechtigungen (ACL-Spiegelung)
- Automatischer, inkrementeller Reindex (Watcher statt manuellem Endpoint)
- Vektor-Datenbank (Qdrant oder pgvector) statt In-Memory-Index
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
