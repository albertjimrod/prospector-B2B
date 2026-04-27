# Prospector B2B

Pipeline automatizado de descubrimiento, análisis y prospección de empresas para servicios de datos, scraping y automatización.

---

## ¿Qué es?

Prospector es un pipeline Python de 4 fases que automatiza la búsqueda de empresas (PYMEs y startups) que encajan con el perfil de servicios del analista. El perfil se define en `docs/perfil_analista.md` y es el eje central del sistema: todas las fases lo leen para validar el encaje de cada empresa, detectar los gaps relevantes y proponer soluciones concretas.

Para cada empresa descubierta, el sistema construye un perfil completo a partir de su web, presencia en LinkedIn y canal de YouTube, y genera un informe estructurado que responde a una pregunta concreta: **¿es esta empresa una buena candidata para recibir una propuesta, y qué propuesta específica tiene sentido dado su estado digital y el perfil del analista?**

El objetivo no es automatizar el outreach, sino **eliminar el ruido** del proceso de prospección: encontrar las empresas correctas, analizarlas en profundidad y llegar al primer contacto con información real y concreta sobre cada una.

---

## Flujo del pipeline

```
Directorios / búsqueda web
         │
         ▼
┌─────────────────────┐
│   FASE A            │  Claude Haiku genera queries → SerpAPI busca
│   Descubrimiento    │  → Claude Haiku valida encaje → SQLite
└────────┬────────────┘
         │ leads validados
         ▼
┌─────────────────────┐
│   FASE B            │  ┌─ web_audit.py  → stack, señales, RRSS
│   Enriquecimiento   │  ├─ linkedin.py   → descripción, posts recientes
│                     │  └─ youtube.py    → transcripciones de vídeos
└────────┬────────────┘
         │ raw/ por empresa
         ▼
┌─────────────────────┐
│   FASE C            │  Claude Sonnet lee todo el contenido
│   Informe           │  → genera informe .md con fit_score 0-1
└────────┬────────────┘
         │ reports/ por empresa
         ▼
┌─────────────────────┐
│   FASE D            │  Tracker interactivo de outreach
│   Outreach          │  Registro manual de contactos y respuestas
└─────────────────────┘
```

---

## Instalación

### Requisitos

- Python 3.11+
- Conda o virtualenv
- Google Chrome instalado (para scraping LinkedIn con Selenium)
- Cuenta en [SerpAPI](https://serpapi.com) (plan gratuito: 100 búsquedas/mes)
- API key de [Anthropic](https://console.anthropic.com)

### Pasos

```bash
git clone https://github.com/albertjimrod/prospector.git
cd prospector

conda create -n prospector python=3.11 -y
conda activate prospector
pip install -r requirements.txt

cp .env.example .env
# Edita .env con tus claves

PYTHONPATH=. python db/init_db.py
```

---

## Configuración

### 1. Credenciales (`.env`)

```env
LLM_API_KEY=sk-ant-...          # Anthropic API key
SERPAPI_KEY=...                  # SerpAPI key
LINKEDIN_EMAIL=tu@email.com      # Tu cuenta LinkedIn (scraping ligero)
LINKEDIN_PASSWORD=...
```

### 2. Perfil del analista (`docs/perfil_analista.md`)

El fichero `docs/perfil_analista.md` define quién eres y qué servicios ofreces. El sistema lo lee en cada ejecución para validar el encaje de empresas y personalizar los informes. Edítalo con tu perfil real antes de ejecutar el pipeline.

Estructura recomendada:

```
PERFIL: [descripción breve de tu especialidad]
RELEVANCIA_CLAVE:
- [capacidad 1]
- [capacidad 2]
ENCAJE_STRATEGY: [tipo de cliente objetivo]
RESUMEN_CONTEXTO: [contexto adicional, proyectos relevantes, stack]
```

El pipeline lanza un error claro si el fichero no existe o está vacío.

---

## Uso

### Fase A — Descubrir leads

```bash
# Run estándar: 8 queries, hasta 10 resultados por query
PYTHONPATH=. python -m pipeline.run --phase A --ccaa catalunya

# Run controlado: parar al llegar a 20 leads válidos
PYTHONPATH=. python -m pipeline.run --phase A --ccaa madrid --max-leads 20

# Run mínimo de prueba
PYTHONPATH=. python -m pipeline.run --phase A --ccaa euskadi --queries 3 --results 5 --max-leads 5

# Sector específico
PYTHONPATH=. python -m pipeline.run --phase A --ccaa catalunya --sector ecommerce
```

CCAA disponibles: `catalunya`, `madrid`, `valencia`, `euskadi`, `andalucia`, `aragon`

### Fase B — Enriquecer empresa

```bash
# Procesar todos los leads pendientes
PYTHONPATH=. python -m pipeline.run --phase B

# Procesar un lead concreto
PYTHONPATH=. python -m pipeline.run --phase B --lead-id 5

# Con idioma de subtítulos YouTube específico
PYTHONPATH=. python -m pipeline.run --phase B --lang ca --max-videos 10
```

La Fase B ejecuta en orden: auditoría web → LinkedIn → YouTube. Los módulos que no encuentran datos (sin LinkedIn URL, sin canal YouTube) se saltan sin error.

### Fase C — Generar informe

```bash
# Generar todos los informes pendientes
PYTHONPATH=. python -m pipeline.run --phase C

# Generar informe de un lead concreto
PYTHONPATH=. python -m pipeline.run --phase C --lead-id 5
```

Los informes se guardan en `reports/{lead_id}.md` con estructura fija: perfil, madurez digital, gaps, encaje, soluciones propuestas, fit_score y gancho para el primer contacto.

### Fase D — Outreach tracker

```bash
PYTHONPATH=. python -m pipeline.run --phase D
```

Interfaz interactiva con comandos: `l` (listar por fit score), `v` (ver informe), `c` (registrar contacto), `u` (actualizar estado), `s` (salir).

---

## Estructura del proyecto

```
prospector/
├── db/
│   ├── schema.sql          — definición de tablas SQLite
│   └── init_db.py          — inicializa data/pipeline.db
├── pipeline/
│   ├── config.py           — constantes, rutas, PERFIL del developer
│   ├── run.py              — punto de entrada CLI
│   ├── phase_a/
│   │   └── discover.py     — descubrimiento y validación de leads
│   ├── phase_b/
│   │   ├── web_audit.py    — auditoría web y detección de RRSS
│   │   ├── linkedin.py     — scraping de página de empresa LinkedIn
│   │   └── youtube.py      — descarga de transcripciones de canal
│   ├── phase_c/
│   │   └── report.py       — generación de informe por empresa con LLM
│   └── phase_d/
│       └── outreach.py     — tracker interactivo de contactos
├── data/                   — pipeline.db + raw/ por empresa (gitignored)
├── reports/                — informes .md por empresa (gitignored)
├── docs/                   — documentación del proyecto
├── requirements.txt
└── .env.example
```

---

## Base de datos

SQLite en WAL mode (`data/pipeline.db`). 8 tablas:

| Tabla | Contenido |
|---|---|
| `leads` | Empresas descubiertas: nombre, CCAA, sector, web, status |
| `contactos` | Personas de contacto por empresa |
| `rrss` | URLs de redes sociales detectadas |
| `web_audit` | Tech stack, CMS, señales de proceso manual |
| `youtube_videos` | Metadatos y rutas de transcripciones descargadas |
| `reports` | Ruta del informe .md y fit_score |
| `outreach` | Registro de contactos realizados y su estado |
| `run_log` | Auditoría de cada ejecución del pipeline |

Los datos crudos (`data/raw/{empresa_id}/`) y los informes (`reports/`) nunca suben al repositorio.

---

## Stack técnico

| Componente | Herramienta |
|---|---|
| LLM · validación y queries | Claude Haiku (`claude-haiku-4-5-20251001`) |
| LLM · informes | Claude Sonnet (`claude-sonnet-4-6`) |
| Búsqueda web | SerpAPI (Google Search) |
| Web scraping | Requests + BeautifulSoup4 |
| LinkedIn scraping | Selenium + ChromeDriver |
| Transcripciones YouTube | yt-dlp |
| Base de datos | SQLite WAL |
| Variables de entorno | python-dotenv |

---

## Alcance y limitaciones éticas

Este sistema recoge únicamente información **públicamente accesible**:

- Contenido indexado por buscadores (webs corporativas, páginas públicas de LinkedIn)
- Vídeos y transcripciones públicas de YouTube
- Datos de empresa en directorios públicos (infocif, einforma, expansión)

**No recoge ni almacena:**
- Datos privados o de acceso restringido
- Contraseñas, tokens o credenciales de terceros
- Datos personales más allá del contacto profesional público (nombre, cargo, email corporativo)

El outreach es siempre **manual y acotado** (≤ 30 contactos/día). El sistema no automatiza el envío de mensajes ni el contacto directo con personas.

Ver `docs/RULES.md` para las reglas operativas completas.

---

## Datos de contacto

Alberto Jiménez · Python developer independiente · Barcelona/Tarragona
[LinkedIn](https://linkedin.com/in/albertjimrod) · albert@datablogcafe.com
