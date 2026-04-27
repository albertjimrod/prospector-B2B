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

---

## Sesión 2 — 27 de abril de 2026

### 1. Análisis de metodología B2B y gap de la Sesión 1

Se analiza el contenido de prospecta-gs.com (proceso de prospección B2B) para identificar qué conceptos del sistema estándar no estaban implementados. Los gaps principales detectados:

- **Taxonomía de leads:** el sistema solo tenía `contacted` como estado post-informe, sin diferenciar suspect, prospect y lead. En B2B esto es crítico porque el ciclo de venta es largo y la calidad del contacto importa más que el volumen.
- **Multi-touch:** un único registro de contacto por empresa no refleja el ciclo real de 6-10 touchpoints (Gartner). Faltaban seguimientos programados.
- **BANT:** framework de calificación estándar. Parte de Budget, Authority, Need y Timing es deducible del contenido público sin ninguna conversación previa.
- **Decisores:** contactar a la persona correcta (CEO, director, fundador) es determinante. La Fase B no identificaba personas, solo contenido corporativo.

### 2. Cambios en la base de datos (schema.sql)

Se amplía `leads.status` con la taxonomía completa: `pending → enriching → reported → suspect → prospect → lead → closed_won / closed_lost`. La transición `reported → suspect` es la única manual (decisión del developer). Las demás las dispara el sistema al actualizar el outreach.

Se añaden a `outreach`: `attempt_number` (secuencia de intentos por lead) y `next_contact_at` (fecha del próximo seguimiento). Estos dos campos son la base del sistema multi-touch.

Se añaden a `contactos`: `is_decision_maker INTEGER DEFAULT 0` y `UNIQUE(lead_id, email)` para evitar duplicados entre web y LinkedIn.

**Nota:** la BD existente debe recrearse con `python db/init_db.py` después de borrar `data/pipeline.db`.

### 3. Fase B · web_audit: extracción de emails

Se añaden cuatro constantes (`TERMINOS_EQUIPO`, `REGEX_EMAIL`, `EMAIL_IGNORADOS`, `EXTENSIONES_IMG`) y tres funciones nuevas:
- `extraer_emails()`: regex sobre el HTML completo, con filtros para evitar falsos positivos
- `encontrar_url_equipo()`: detecta el enlace a la página de equipo/contacto para extraer emails individuales
- `guardar_contacto_web()`: INSERT OR IGNORE en `contactos` con el constraint de unicidad

El resultado es que web_audit ya no solo extrae datos de empresa sino también emails de contacto reales, complementando lo que LinkedIn aporta.

### 4. Fase B · linkedin: identificación de decisores

Se añade `CARGOS_DECISOR` (20 términos ES/EN) y dos funciones:
- `extraer_decisores()`: navega a `/people/` y filtra por cargo. Devuelve hasta 3 decisores.
- `guardar_contactos()`: guarda los decisores en `contactos` con `is_decision_maker=1`

La función `run()` ahora llama a `scrape_company()` y `extraer_decisores()` en secuencia para cada empresa.

### 5. Fase C · report: BANT como sección 7

El prompt del informe pasa de 7 a 8 secciones. La nueva sección 7 (BANT estimado) analiza Budget, Authority, Need y Timing a partir del contenido público. El gancho para el primer contacto pasa a ser la sección 8.

### 6. Fase D · outreach: reescritura completa

El tracker original era mínimo (listar + ver + contactar). Se reescribe completamente con:
- `listar_seguimientos()`: cola de seguimientos vencidos ordenada por fecha
- `ver_historial()`: histórico completo de intentos de un lead
- `ver_contactos()`: muestra decisores y emails, marcando is_decision_maker
- `registrar_contacto()`: INSERT con attempt_number auto-calculado + next_contact_at
- `calificar_lead()`: transición manual `reported → suspect`
- `actualizar_outreach()`: UPDATE del último intento + transición automática de lead
- `cerrar_lead()`: cierre definitivo won/lost

Los comandos del menú interactivo pasan de 4 a 9 (l, f, v, h, p, q, c, u, x).

### 7. Documentación

TECHNICAL.md, DECISIONS.md, JOURNAL.md y TODO.md actualizados para reflejar todos los cambios. Se añaden las decisiones 009-012.

### Pendiente (próxima sesión)

- Recrear BD: `rm data/pipeline.db && conda run -n prospector python db/init_db.py`
- Fix Fase A discover.py: max_tokens 256 → 512 en `validar_lead` + actualizar prompt de `generar_queries` para evitar URLs de LinkedIn y directorios
- Commit y push a GitHub (https://github.com/albertjimrod/prospector-B2B.git)
