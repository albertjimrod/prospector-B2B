# JOURNAL.md — Diario del proyecto Prospector B2B

Registro cronológico de qué se ha construido, en qué orden y por qué.
Para el detalle técnico de cada componente, ver [TECHNICAL.md](TECHNICAL.md).
Para las decisiones de diseño, ver [DECISIONS.md](DECISIONS.md).

---

## Sesión 1 — 27 de abril de 2026

### Contexto de partida
El proyecto arranca como evolución directa del trabajo de prospección activa sobre PYMEs (BioPlace, Condal Computer, Macaque Group). La experiencia manual demostró que el tiempo de análisis previo al primer contacto es el principal cuello de botella. El objetivo es automatizar ese análisis sin automatizar el contacto en sí.

La arquitectura y convenciones de documentación se toman directamente de BioPlace (JOURNAL, TECHNICAL, DECISIONS, TODO, README). El comando `/journal` se configura como comando local del proyecto en `.claude/commands/journal.md`.

### 1. Diseño del sistema y validación de fuentes de datos

Antes de escribir código se evaluó la viabilidad de cada fuente de datos:

- **YouTube:** API v3 disponible, yt-dlp robusto. Decisión: usar yt-dlp Python library directamente, reutilizando la lógica del script bash `full_pipeline.sh` ya existente. Solo Fases 1 y 2 del script original (links + transcripciones). El corpus (Fases 3-4) se reserva para RAG futuro.
- **LinkedIn:** sin API útil. Selenium con sesión propia como única vía viable. Scraping ligero, solo info pública, delays aleatorios. Riesgo de ToS asumido conscientemente (ver decisión 004).
- **Twitter/X, Instagram, Facebook:** descartados. API inaccesible o de pago elevado, valor B2B bajo.
- **Web corporativa:** Requests + BeautifulSoup4 sin Selenium de entrada. Detección de stack por headers HTTP y patrones HTML.

**Decisión sobre almacenamiento:** SQLite WAL para datos estructurados + ficheros `.txt` por empresa en `data/raw/{lead_id}/` para contenido no estructurado. Esta separación permite indexar `raw/` en ChromaDB en el futuro sin modificar la arquitectura. Ver decisión 003.

**Decisión sobre Docker:** no necesario. Sin servidor local que simular. El pipeline es puramente Python con llamadas a APIs externas y SQLite local.

### 2. Estructura del proyecto y base de datos

Se crea `/home/ion/projects/prospector` como directorio independiente. Estructura basada en BioPlace pero sin carpeta `docker-compose.yml` ni `setup_wp.sh`.

Base de datos con 8 tablas: `leads`, `contactos`, `rrss`, `web_audit`, `youtube_videos`, `reports`, `outreach`, `run_log`. Ver esquema ER completo en TECHNICAL.md.

Decisión clave: el campo `leads.status` tiene 4 estados progresivos (`pending → enriching → reported → contacted`) que permiten relanzar fases sin reprocesar lo ya hecho.

### 3. Implementación del pipeline completo

Se implementan los 4 módulos de la Fase B en orden de complejidad creciente:

**Fase A (`discover.py`):** misma lógica que BioPlace pero orientada a PYMEs cliente en lugar de proveedores bioenergéticos. El LLM devuelve `web_oficial` además de la validación — útil cuando SerpAPI apunta a fichas de directorio en lugar de la web corporativa.

**Fase B · web_audit (`web_audit.py`):** detección de CMS por 9 patrones, stack por headers HTTP y patrones JS, RRSS por regex sobre HTML completo, señales de proceso manual (PDF, WhatsApp, "solicitar presupuesto", ausencia de e-commerce). Texto extraído truncado a 8000 caracteres para el LLM.

**Fase B · linkedin (`linkedin.py`):** Selenium con Chrome headless, login con credenciales propias, delays aleatorios 6-12s entre empresas. Extrae: descripción, datos de empresa, especialidades y últimos 5 posts.

**Fase B · youtube (`youtube.py`):** `vtt_a_texto()` replica la función `subs_to_text` del script bash. `tempfile.TemporaryDirectory` garantiza limpieza de ficheros VTT intermedios incluso si el proceso falla. Prioridad de idiomas: es → es-ES → ca → en.

**Fase C (`report.py`):** Claude Sonnet lee web + linkedin + youtube (hasta 5 vídeos). Prompt estructurado en 7 secciones. El gancho para el primer contacto (sección 7) es el output más crítico — diferencia el outreach personalizado del spam genérico.

**Fase D (`outreach.py`):** tracker interactivo de consola. Comandos: listar por fit_score, ver informe, registrar contacto, actualizar estado.

### 4. Configuración compartida con BioPlace

Las claves `LLM_API_KEY` y `SERPAPI_KEY` son las mismas que BioPlace. Se copian en el `.env` del proyecto. No hay entorno Docker compartido — cada proyecto es autónomo.

### 5. Documentación

Se crean los 6 ficheros de `docs/`:
- `README.md` — orientado a GitHub, con diagrama del pipeline, instalación, uso y consideraciones éticas
- `TECHNICAL.md` — arquitectura completa, diagramas Mermaid, documentación de funciones
- `JOURNAL.md` — este fichero
- `DECISIONS.md` — decisiones técnicas y éticas/legales
- `RULES.md` — reglas operativas de uso del sistema
- `TODO.md` — máximo 3 tareas activas

El comando `/journal` se configura como comando local en `.claude/commands/journal.md`, independiente del de BioPlace.

### Pendiente (próxima sesión)

- Inicializar BD y ejecutar primera prueba de Fase A (entorno conda)
- Verificar selectores de LinkedIn con una empresa real
- Definir GitLab/GitHub como repositorio y hacer primer commit
