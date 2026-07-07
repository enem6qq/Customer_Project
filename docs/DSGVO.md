# DSGVO- und Compliance-Hinweise

Dieses Grundgerüst ist so gebaut, dass ein DSGVO-konformer Betrieb möglich ist.
Konformität entsteht aber erst durch das konkrete Deployment und die Verträge –
diese Punkte müssen pro Kunde geklärt werden.

## Was die Architektur bereits leistet

- **Selbst hostbar:** Backend, Index und Dokumente laufen vollständig auf eigener
  Infrastruktur (Server in Deutschland / eigenes Rechenzentrum). Es gibt keine
  verpflichtenden Drittdienste.
- **Lokales LLM möglich:** Mit dem Ollama-Provider verlässt kein einziges Byte
  der Dokumente den Server – auch nicht zur Antwortgenerierung.
- **Berechtigungen vor der KI:** Der RBAC-Filter greift in der Retrieval-Schicht,
  bevor Inhalte an ein LLM übergeben werden. Ein Benutzer kann keine Inhalte
  „herausfragen", auf die er keinen Zugriff hat.
- **Keine Geheimnisse im Code:** API-Keys und JWT-Secret kommen ausschließlich
  aus Umgebungsvariablen.

## Was pro Kunde zu klären ist (Checkliste)

1. **Hosting:** Eigenes RZ, deutscher IaaS-Anbieter (z. B. IONOS, STACKIT,
   Hetzner, plusserver) oder On-Premise beim Kunden. Für öffentliche
   Auftraggeber ggf. BSI C5 / IT-Grundschutz-Anforderungen prüfen.
2. **AVV (Auftragsverarbeitungsvertrag):** mit jedem eingesetzten Dienstleister
   (Hosting, ggf. LLM-API-Anbieter) nach Art. 28 DSGVO.
3. **Externes LLM nur mit Prüfung:** Wird `openai_compatible` mit einem externen
   Endpunkt genutzt, müssen Auftragsverarbeitung, Speicherort (EU) und
   No-Training-Zusagen vertraglich gesichert sein. Im Zweifel: lokales Modell.
4. **Verzeichnis von Verarbeitungstätigkeiten** (Art. 30) und ggf.
   **Datenschutz-Folgenabschätzung** (Art. 35) – insbesondere wenn
   Personaldokumente indiziert werden.
5. **Löschkonzept:** Wird ein Dokument aus der Ablage entfernt, verschwindet es
   mit dem nächsten Reindex aus dem Index. Für Produktivbetrieb: automatischer
   Reindex + definierte Aufbewahrungsfristen.
6. **Protokollierung:** Der Prototyp speichert keine Chatverläufe. Falls
   Protokollierung gewünscht ist (Qualitätssicherung), braucht es
   Rechtsgrundlage, Betriebsvereinbarung und Anonymisierung.
7. **Mitbestimmung:** Bei Einführung in Behörden/größeren Unternehmen früh
   Personalrat/Betriebsrat und Datenschutzbeauftragte einbinden – das ist in
   der Praxis der häufigste Verzögerungsgrund, nicht die Technik.

## Sicherheit (Stand Prototyp → Produktion)

| Thema            | Prototyp                    | Produktion                              |
|------------------|-----------------------------|------------------------------------------|
| Anmeldung        | YAML-Benutzer + JWT         | SSO: LDAP / Active Directory / OIDC     |
| Transport        | HTTP lokal                  | TLS (Reverse Proxy, z. B. nginx/Traefik) |
| Rechte           | Gruppe = Ordnername         | ACLs aus Quellsystem (AD-Gruppen) spiegeln |
| Geheimnisse      | .env                        | Secret-Store (z. B. Vault)              |
| Audit            | keine                       | Zugriffs- und Admin-Audit-Log           |
