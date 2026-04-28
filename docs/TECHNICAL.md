# TECHNICAL.md — Documentación técnica de Prospector B2B

Descripción detallada de la arquitectura, ficheros, funciones y flujo de datos.
Para el historial de construcción, ver [JOURNAL.md](JOURNAL.md).
Para las decisiones de diseño, ver [DECISIONS.md](DECISIONS.md).

---

## Arquitectura general

El pipeline se estructura en 4 fases independientes y encadenadas. Cada fase lee de la BD el output de la fase anterior y escribe su propio output. Esto permite ejecutar fases por separado y relanzar cualquiera sin repetir las anteriores.

```mermaid
flowchart LR
    subgraph A["Fase A · Descubrimiento"]
        A1[Claude Haiku\ngenera queries] --> A2[SerpAPI\nbúsqueda web] --> A3[Claude Haiku\nvalida encaje]
    end
    subgraph B["Fase B · Enriquecimiento"]
        B1[Requests+BS4\nauditoría web] --> B2[Selenium\nLinkedIn empresa]
        B1 --> B3[yt-dlp\ntranscripciones YT]
    end
    subgraph C["Fase C · Informe"]
        C1[Claude Sonnet\nlee raw/ completo] --> C2[Informe .md\nfit_score 0-1]
    end
    subgraph D["Fase D · Outreach"]
        D1[Tracker interactivo\nregistro manual]
    end

    A --> |leads válidos| BD[(pipeline.db\nSQLite WAL)]
    BD --> B
    B --> |raw/ por empresa| BD
    BD --> C
    C --> |reports/ por empresa| BD
    BD --> D
```

---

## Estructura de ficheros

```
prospector/
├── db/
│   ├── schema.sql          — definición de tablas SQLite
│   └── init_db.py          — crea data/pipeline.db aplicando schema.sql
├── pipeline/
│   ├── config.py           — constantes globales, rutas y PERFIL del developer
│   ├── run.py              — punto de entrada CLI (--phase, --ccaa, --lead-id...)
│   ├── phase_a/
│   │   └── discover.py     — descubrimiento y validación de leads
│   ├── phase_b/
│   │   ├── web_audit.py    — auditoría web, detección de stack y RRSS
│   │   ├── linkedin.py     — scraping de página pública de empresa en LinkedIn
│   │   └── youtube.py      — descarga de transcripciones de canal YouTube
│   ├── phase_c/
│   │   └── report.py       — generación de informe estructurado con LLM
│   └── phase_d/
│       └── outreach.py     — tracker interactivo de contactos realizados
├── data/
│   ├── pipeline.db         — base de datos local (gitignored)
│   └── raw/
│       └── {lead_id}/
│           ├── web.txt         — texto extraído de la web corporativa
│           ├── linkedin.txt    — contenido scrapeado de LinkedIn
│           └── youtube/
│               └── {video_id}.txt  — transcripción por vídeo
├── reports/
│   └── {lead_id}.md        — informe generado por LLM (gitignored)
├── docs/
└── requirements.txt
```

---

## Base de datos: pipeline.db

SQLite en WAL mode. Permite lecturas concurrentes durante escrituras, evitando bloqueos si en el futuro el pipeline corre en paralelo. Ver decisión 002 en DECISIONS.md.

### Diagrama entidad-relación

```mermaid
erDiagram
    leads {
        INTEGER id PK
        TEXT empresa
        TEXT ccaa
        TEXT sector
        TEXT web UK
        TEXT fuente
        TEXT status
        DATETIME discovered_at
    }
    contactos {
        INTEGER id PK
        INTEGER lead_id FK
        TEXT nombre
        TEXT email UK
        TEXT cargo
        TEXT linkedin_profile_url
        INTEGER is_decision_maker
    }
    rrss {
        INTEGER id PK
        INTEGER lead_id FK
        TEXT linkedin_url
        TEXT twitter_x
        TEXT instagram
        TEXT facebook
        TEXT youtube_url
        TEXT youtube_channel_id
    }
    web_audit {
        INTEGER id PK
        INTEGER lead_id FK
        TEXT tech_stack
        INTEGER has_cms
        INTEGER has_api
        INTEGER has_crm
        INTEGER has_static_prices
        INTEGER has_pdf_catalog
        TEXT manual_process_signals
        TEXT raw_text_path
        DATETIME audited_at
    }
    youtube_videos {
        INTEGER id PK
        INTEGER lead_id FK
        TEXT video_id UK
        TEXT title
        TEXT published_at
        TEXT transcript_path
        DATETIME downloaded_at
    }
    reports {
        INTEGER id PK
        INTEGER lead_id FK
        TEXT report_path
        TEXT gap_summary
        REAL fit_score
        DATETIME generated_at
    }
    outreach {
        INTEGER id PK
        INTEGER lead_id FK
        TEXT channel
        TEXT status
        INTEGER attempt_number
        DATETIME sent_at
        DATETIME next_contact_at
        TEXT notes
        DATETIME created_at
    }
    run_log {
        INTEGER id PK
        TEXT phase
        TEXT status
        TEXT message
        DATETIME started_at
        DATETIME finished_at
    }

    leads ||--o{ contactos : "lead_id"
    leads ||--o| rrss : "lead_id"
    leads ||--o| web_audit : "lead_id"
    leads ||--o{ youtube_videos : "lead_id"
    leads ||--o| reports : "lead_id"
    leads ||--o{ outreach : "lead_id"
```

### Estados del campo `leads.status`

El campo progresa en una sola dirección. Nunca retrocede salvo intervención manual en la BD.

| Status | Quién lo asigna | Significado |
|---|---|---|
| `pending` | Fase A | Lead descubierto, sin enriquecer |
| `enriching` | Fase B | Enriquecimiento web completado (linkedin/YouTube pueden faltar) |
| `reported` | Fase C | Informe generado y fit_score asignado |
| `suspect` | Fase D manual | Calificado por el developer: encaja, vale la pena contactar |
| `prospect` | Fase D automático | Ha respondido al primer contacto |
| `lead` | Fase D automático | Reunión confirmada |
| `closed_won` | Fase D manual | Proyecto cerrado con éxito |
| `closed_lost` | Fase D manual | Descartado definitivamente |

---

## pipeline/config.py

Constantes globales cargadas una sola vez al importar el módulo.

| Constante | Tipo | Descripción |
|---|---|---|
| `BASE_DIR` | str | Raíz del proyecto (directorio padre de `pipeline/`) |
| `DB_PATH` | str | Ruta absoluta a `data/pipeline.db` |
| `RAW_DIR` | str | Ruta absoluta a `data/raw/` |
| `REPORTS_DIR` | str | Ruta absoluta a `reports/` |
| `LLM_API_KEY` | str | Clave Anthropic leída de `.env` |
| `SERPAPI_KEY` | str | Clave SerpAPI leída de `.env` |
| `LINKEDIN_EMAIL` | str | Email LinkedIn leído de `.env` |
| `LINKEDIN_PASSWORD` | str | Contraseña LinkedIn leída de `.env` |
| `PERFIL` | str | Bloque de texto con el perfil del developer, usado en prompts LLM |

---

## pipeline/run.py — Punto de entrada CLI

### Argumentos

| Argumento | Tipo | Default | Aplica a | Descripción |
|---|---|---|---|---|
| `--phase` | A/B/C/D | obligatorio | todas | Fase a ejecutar |
| `--ccaa` | str | `catalunya` | solo A | CCAA objetivo |
| `--sector` | str | None | solo A | Sector específico (opcional) |
| `--lead-id` | int | None | B, C | Procesar un lead concreto |
| `--queries` | int | 8 | solo A | Queries a generar |
| `--results` | int | 10 | solo A | Resultados SerpAPI por query |
| `--max-leads` | int | None | solo A | Techo de leads válidos |
| `--lang` | str | `es` | solo B | Idioma subtítulos YouTube |
| `--max-videos` | int | 20 | solo B | Máx vídeos a transcribir por canal |

---

## pipeline/phase_a/discover.py — Descubrimiento de leads

### Propósito
Descubrir PYMEs y startups potencialmente cliente a través de SerpAPI, validar su encaje con el perfil del developer mediante LLM y guardarlas en `leads`.

### Diagrama de secuencia

```mermaid
sequenceDiagram
    participant CLI as run.py
    participant D as discover.py
    participant LLM as Claude Haiku
    participant SERP as SerpAPI
    participant DB as pipeline.db

    CLI->>D: run(ccaa, sector, n_queries, results_per_query, max_leads)
    D->>LLM: generar_queries(ccaa, config, sector, n_queries)
    LLM-->>D: ["query1", ..., "queryN"]

    loop para cada query (para si max_leads alcanzado)
        D->>SERP: buscar_leads(query, idioma, pais, num)
        SERP-->>D: [{url, title, snippet}, ...]

        loop para cada resultado
            D->>LLM: validar_lead(title, url, snippet)
            LLM-->>D: {valid, reason, sector_detectado, empresa_nombre, web_oficial}
            alt válido
                D->>DB: guardar_lead(empresa, ccaa, sector, web, fuente)
            end
        end
    end

    D->>DB: registrar_run(phase, status, message)
```

### Constante: CCAA_CONFIG
Diccionario estructurado por CCAA con `idioma` (código ISO 639-1 para SerpAPI `hl=`), `pais` (código ISO 3166-1 para SerpAPI `gl=`) y `geo` (términos geográficos para las queries).

### Constante: SECTORES_OBJETIVO
Lista de 18 sectores objetivo preconfigurados. Se usan cuando no se especifica `--sector`. El LLM combina estos sectores con la geografía para generar queries diversas.

### Función: limpiar_json(texto)
Elimina bloques de markdown (` ```json ... ``` `) del texto devuelto por el LLM antes de parsear con `json.loads()`. Necesaria porque Claude Haiku envuelve habitualmente las respuestas JSON en markdown. Ver la misma función en BioPlace/discover.py — comportamiento idéntico.

### Función: generar_queries(client, ccaa, config, sector, n_queries)
Prompt al LLM que genera `n_queries` queries de búsqueda combinando CCAA, sectores objetivo, tipo de empresa y operadores de exclusión de RRSS y PDFs. Devuelve lista de strings.

**`max_tokens`:** 1024 — necesario para n_queries > 5.
**Modelo:** `claude-haiku-4-5-20251001`.

### Función: buscar_leads(query, idioma, pais, num)
Llama a SerpAPI REST con los parámetros geográficos de la CCAA. Extrae `link`, `title` y `snippet` de los resultados orgánicos. 1 llamada a SerpAPI por invocación.

### Función: validar_lead(client, title, url, snippet)
Prompt de clasificación: el LLM evalúa si la empresa encaja con el PERFIL del developer. Devuelve JSON con `valid` (bool), `reason`, `sector_detectado`, `empresa_nombre` y `web_oficial` (URL de la web corporativa si la detección en el snippet la revela — útil cuando el resultado de SerpAPI apunta a una ficha de directorio).

**`max_tokens`:** 512 — 256 era insuficiente; el campo `reason` quedaba truncado y el JSON resultaba inválido.

### Función: guardar_lead(empresa, ccaa, sector, web, fuente)
`INSERT OR IGNORE` en `leads`. La constraint `UNIQUE` sobre `web` evita duplicados entre ejecuciones.

---

## pipeline/phase_b/web_audit.py — Auditoría web

### Propósito
Descargar la web corporativa, detectar stack tecnológico, señales de proceso manual y URLs de redes sociales. Guardar el texto extraído en `data/raw/{lead_id}/web.txt`.

### Constantes: TERMINOS_EQUIPO, REGEX_EMAIL, EMAIL_IGNORADOS, EXTENSIONES_IMG
Usadas por las funciones de extracción de emails. `TERMINOS_EQUIPO` contiene términos que aparecen en enlaces a páginas de equipo/contacto (en castellano, catalán e inglés). `EMAIL_IGNORADOS` filtra emails de ejemplo, noreply y herramientas de tracking. `EXTENSIONES_IMG` descarta falsos positivos que acaban en extensión de imagen.

### Constante: CMS_PATTERNS
Dict de CMS → lista de patrones regex. Detecta: WordPress, Shopify, Wix, Squarespace, Webflow, Joomla, Drupal, PrestaShop, Magento.

### Constante: SOCIAL_PATTERNS
Dict de campo → regex para extraer URLs de LinkedIn, Twitter/X, Instagram, Facebook y YouTube directamente del HTML de la web. Fuente más fiable que SerpAPI para encontrar el canal YouTube correcto.

### Función: detectar_stack(html_lower, response_headers)
Extrae tech stack de cabeceras HTTP (`Server`, `X-Powered-By`) y del HTML (React, Vue.js, Next.js, Angular). Devuelve string con los elementos encontrados separados por `, `.

### Función: detectar_rrss(html)
Aplica `SOCIAL_PATTERNS` sobre el HTML completo. Devuelve dict con los campos encontrados. Solo incluye campos con valor — no devuelve nulls.

### Función: detectar_senales(html_lower, soup)
Detecta señales de proceso manual y madurez digital: catálogos PDF, precios visibles, contacto por WhatsApp, ausencia de e-commerce, formularios de contacto, presencia de CRM (HubSpot, Salesforce, Zoho, etc.), texto "solicitar presupuesto". Devuelve lista de strings.

### Función: extraer_emails(html)
Aplica `REGEX_EMAIL` sobre el HTML completo. Filtra por `EMAIL_IGNORADOS` y `EXTENSIONES_IMG`. Devuelve hasta 5 emails únicos. Los emails encontrados se guardan en `contactos` via `guardar_contacto_web()`.

### Función: encontrar_url_equipo(soup, url_base)
Busca en todos los `<a>` de la página un enlace que contenga alguno de los `TERMINOS_EQUIPO` (en el texto o en la URL). Devuelve la URL absoluta construida con `urljoin` o `None` si no encuentra ninguna. Permite extraer emails de la página de equipo/contacto, donde suelen aparecer emails individuales.

### Función: guardar_contacto_web(lead_id, email)
`INSERT OR IGNORE` en `contactos` — el constraint `UNIQUE(lead_id, email)` impide duplicados si la misma dirección aparece en home y en la página de equipo.

### Función: guardar_rrss(lead_id, rrss)
`INSERT OR IGNORE` para crear la fila si no existe, seguido de `UPDATE` por campo. Los nombres de campo se validan contra `RRSS_WHITELIST` antes de usarlos en la query SQL — previene inyección aunque el dict proceda de código interno.

---

## pipeline/phase_b/linkedin.py — Scraping LinkedIn

### Propósito
Scraping ligero de la página pública de empresa en LinkedIn usando Selenium con sesión autenticada. Solo información públicamente visible para cualquier usuario logueado. Guarda el contenido en `data/raw/{lead_id}/linkedin.txt`.

### Constante: CARGOS_DECISOR
Lista de 20 términos (ES/EN) que identifican roles con capacidad de decisión de compra: CEO, CTO, director, gerente, fundador, socio, propietario, etc. Se aplica sobre el cargo detectado en la pestaña `/people/` de LinkedIn para filtrar decisores reales.

### Por qué Selenium y no requests
LinkedIn renderiza el contenido de las páginas de empresa con JavaScript. Requests solo obtiene el HTML inicial, sin el contenido dinámico. Selenium con Chrome headless renderiza la página completa.

### Función: init_driver()
Inicia Chrome con flags anti-detección: `--disable-blink-features=AutomationControlled`, `excludeSwitches: enable-automation`, `useAutomationExtension: false`, User-Agent real. Desactiva la propiedad `navigator.webdriver` via JavaScript. Ver decisión 004 en DECISIONS.md.

### Función: login(driver)
Login en linkedin.com/login con las credenciales de `.env`. Añade delays aleatorios entre acciones (2-4s, 0.5-1.5s) para comportamiento similar al humano.

Tras el click de submit, comprueba la URL resultante. Si contiene `checkpoint`, `challenge`, `verification` o `pin`, LinkedIn ha lanzado una verificación por email/SMS o captcha. En ese caso el script imprime un aviso en la terminal y ejecuta `input()` — pausa indefinida hasta que el usuario complete la verificación en el navegador y pulse Enter. Sin este mecanismo el scraping continuaría sin sesión válida.

### Función: scrape_company(driver, linkedin_url)
Extrae: descripción/about, datos de empresa (tamaño, sector, sede, fundación, especialidades) y últimos 5 posts. Incluye scroll para cargar el feed. Devuelve texto plano estructurado con encabezados markdown.

**Selectores activos (verificados abril 2026):**
- Descripción: lista de 4 fallbacks — `p.break-words.white-space-pre-wrap.t-black--light.text-body-medium`, `p.break-words.t-black--light`, `.org-about-us-organization-description__text`, `p.break-words`. Se usa el primero que devuelva texto.
- Datos de empresa: `dd.t-black--light.text-body-medium` — selector común para sector, tamaño, sede, fundación y especialidades.
- Posts: 3 selectores en cascada — `.feed-shared-update-v2__description-wrapper`, `.attributed-text-segment-list__content`, `[data-test-id="main-feed-activity-card"] span`.

**Nota sobre selectores:** LinkedIn modifica su DOM con frecuencia. Si los selectores dejan de funcionar, inspeccionar manualmente en Chrome DevTools sobre una página de empresa real y actualizar. Ver decisión 004 en DECISIONS.md.

### Función: extraer_decisores(driver, linkedin_url)
Navega a `{linkedin_url}/people/` y extrae hasta 3 contactos cuyo cargo contenga algún término de `CARGOS_DECISOR`. Para cada uno guarda nombre, cargo, URL de perfil y `is_decision_maker=1`. Falla silenciosamente si la pestaña no está disponible (plan gratuito de la empresa o restricción de LinkedIn).

**Selectores activos (verificados abril 2026):**
- Tarjeta: `.org-people-profile-card__profile-info`
- Nombre: `.artdeco-entity-lockup__title .lt-line-clamp--single-line`
- Cargo: `.artdeco-entity-lockup__subtitle .lt-line-clamp--multi-line`
- Perfil URL: `a[href*="/in/"]`

**Filtro de perfiles anónimos:** LinkedIn oculta el nombre de empleados sin conexión directa mostrando "Miembro de LinkedIn" o "LinkedIn Member". Estas tarjetas se saltan explícitamente — no aportan información útil.

### Función: guardar_contactos(lead_id, contactos)
`INSERT OR IGNORE` en `contactos` para cada decisor extraído. El constraint `UNIQUE(lead_id, email)` no aplica aquí porque los decisores de LinkedIn pueden no tener email — la unicidad la garantiza el constraint natural de la combinación nombre+cargo.

### Delays entre empresas
Entre 6 y 12 segundos aleatorios entre scrapes de empresas distintas. No hay patrón fijo que LinkedIn pueda detectar como bot.

---

## pipeline/phase_b/youtube.py — Transcripciones YouTube

### Propósito
Descargar transcripciones de los vídeos de un canal YouTube usando yt-dlp. Guarda cada transcripción en `data/raw/{lead_id}/youtube/{video_id}.txt` y registra los metadatos en `youtube_videos`.

### Por qué yt-dlp y no youtube-transcript-api
yt-dlp descarga tanto subtítulos manuales como automáticos y soporta múltiples idiomas con fallback. Coherente con el script bash existente (`full_pipeline.sh`) que el developer ya usa para RAG personal.

### Función: vtt_a_texto(contenido_vtt)
Equivalente Python de la función `subs_to_text` del script bash original. Elimina cabeceras WEBVTT, timestamps, tags HTML, entidades HTML y líneas duplicadas consecutivas. Añade saltos de párrafo en puntuación final.

### Función: obtener_videos_canal(channel_url, max_videos)
Usa `extract_flat='in_playlist'` con `playlistend=max_videos` para obtener metadatos de vídeos sin descargar. Devuelve lista de dicts con `id`, `title` y `url`.

### Función: descargar_transcript(video_url, lang)
Intenta subtítulos manuales primero, automáticos como fallback. Prioridad de idiomas: `lang` → `{lang}-ES` → `ca` → `en`. Usa directorio temporal (`tempfile.TemporaryDirectory`) para los ficheros VTT intermedios — se limpian automáticamente al salir del contexto.

**Por qué directorio temporal:** yt-dlp escribe ficheros intermedios en disco. Usando `tempfile` garantizamos que no quedan residuos aunque el proceso falle.

---

## pipeline/phase_c/report.py — Generación de informes

### Propósito
Leer todo el contenido raw de una empresa, enviarlo a Claude Sonnet y generar un informe estructurado en markdown con perfil, gaps, encaje y fit_score.

### Función: cargar_contenido(lead_id)
Lee `web.txt` (máx 6000 chars), `linkedin.txt` (máx 4000 chars) y hasta 5 transcripciones de YouTube (máx 2000 chars cada una). Los límites controlan el consumo de tokens del LLM. Devuelve dict con las claves disponibles — no incluye fuentes ausentes. Si el dict está vacío, `run()` descarta el lead automáticamente (ver más abajo).

### Función: generar_informe(client, empresa, web, contenido)
Prompt a Claude Sonnet que incluye el PERFIL completo del developer y todo el contenido disponible. Solicita informe con 8 secciones fijas.

**Modelo:** `claude-sonnet-4-6` — razonamiento más profundo necesario para síntesis y análisis cruzado de múltiples fuentes.
**`max_tokens`:** 2048.

**Extracción del fit_score:** regex sobre el texto generado busca `FIT_SCORE: [0.0-1.0]`. Si no encuentra el patrón, devuelve 0.5 como valor neutro. El score se clampea a [0.0, 1.0] como garantía.

### Secciones del informe

| # | Nombre | Descripción |
|---|---|---|
| 1 | Perfil de la empresa | Sector, tamaño estimado, mercado objetivo, propuesta de valor |
| 2 | Madurez digital | CMS, tech stack, RRSS, canal YouTube, calidad web |
| 3 | Gaps detectados | Lista numerada de problemas concretos observables |
| 4 | Encaje con el perfil | Servicios del developer que encajan y por qué |
| 5 | Soluciones propuestas | 2-3 propuestas accionables vinculadas a RELEVANCIA_CLAVE |
| 6 | Puntuación de encaje | FIT_SCORE (0.0-1.0) + justificación de 1-2 frases |
| 7 | Análisis BANT estimado | Budget, Authority, Need, Timing deducidos del contenido público |
| 8 | Gancho para el primer contacto | Detalle concreto de la web/LinkedIn/YouTube para abrir la conversación |

### Sección 7 — BANT estimado
Budget: señales de capacidad de inversión (tamaño, sector, precios visibles). Authority: probable decisor con nombre y cargo si detectado en LinkedIn o web. Need: urgencia real vs. nice-to-have. Timing: señales de momento óptimo (web desactualizada, crecimiento reciente, nuevo producto, evento sectorial).

### Sección 8 — Gancho para el primer contacto
La sección más accionable para el outreach. El LLM genera un detalle concreto y específico (elemento de la web, post reciente, tema recurrente en YouTube) que demuestra análisis real. Es el diferenciador frente al outreach genérico.

### Gestión de leads sin contenido raw

Si `cargar_contenido()` devuelve dict vacío (Fase B no generó ningún fichero raw), el lead se cierra automáticamente:
- `leads.status` → `closed_lost`
- INSERT en `outreach` con `channel="none"`, `status="discarded"`, nota "Sin contenido suficiente tras Fase B"

Evita leads bloqueados indefinidamente en `enriching` y mantiene el embudo limpio en Fase D.

---

## pipeline/phase_d/outreach.py — Tracker de outreach

### Propósito
Interfaz interactiva para consultar informes, registrar contactos y hacer seguimiento del estado de cada lead. El outreach es siempre manual — este módulo solo registra y organiza.

### Comandos disponibles

| Comando | Acción |
|---|---|
| `l` | Lista leads con fit_score ≥ mínimo, filtrables por status |
| `f` | Lista seguimientos pendientes (next_contact_at ≤ hoy) |
| `v` | Muestra el informe completo de un lead |
| `h` | Muestra el historial de contactos de un lead |
| `p` | Muestra los contactos (decisores + emails) de un lead |
| `q` | Califica un lead: transición manual `reported → suspect` |
| `c` | Registra un nuevo intento de contacto (canal + notas + próximo seguimiento) |
| `u` | Actualiza el status del último intento y avanza el lead si corresponde |
| `x` | Cierra un lead: `closed_won` o `closed_lost` |
| `s` | Sale del tracker |

### Transiciones automáticas de status al actualizar outreach

| Status outreach | Transición leads.status |
|---|---|
| `replied` | → `prospect` |
| `meeting_scheduled` | → `lead` |
| Cualquier otro | sin cambio |

### Funciones principales

| Función | Descripción |
|---|---|
| `listar_leads(min_fit, status)` | SELECT con JOIN a reports y outreach, agrupado por lead |
| `listar_seguimientos()` | Leads con `next_contact_at ≤ hoy` y status no cerrado |
| `ver_historial(lead_id)` | Imprime todos los intentos ordenados por attempt_number |
| `ver_contactos(lead_id)` | Imprime decisores y emails, marcando los is_decision_maker |
| `registrar_contacto(lead_id, canal, notas, next_contact_at)` | INSERT en outreach con attempt_number auto-incrementado |
| `calificar_lead(lead_id)` | UPDATE status `reported → suspect` |
| `actualizar_outreach(lead_id, nuevo_status, notas)` | UPDATE del último intento + transición de lead si aplica |
| `cerrar_lead(lead_id, resultado)` | UPDATE status a `closed_won` o `closed_lost` |

### Estados de outreach

| Status | Significado |
|---|---|
| `sent` | Mensaje enviado, sin respuesta aún |
| `replied` | Ha respondido (avanza lead a `prospect`) |
| `no_reply` | Sin respuesta tras el plazo de seguimiento |
| `meeting_scheduled` | Reunión confirmada (avanza lead a `lead`) |
| `discarded` | Descartado tras análisis posterior |
