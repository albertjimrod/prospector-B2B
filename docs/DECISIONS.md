# DECISIONS.md

Registro de decisiones técnicas y éticas no obvias. Cada entrada explica el contexto, la opción elegida y por qué se descartaron las alternativas.

---

## 001 — LLM: Claude API (Anthropic)

**Fecha:** Abril 2026
**Contexto:** El pipeline necesita un LLM para generar queries de búsqueda, validar encaje de empresas y sintetizar contenido de múltiples fuentes en informes estructurados.
**Decisión:** Claude API. Haiku para tareas de clasificación y generación de queries (coste bajo, velocidad alta). Sonnet para generación de informes (razonamiento más profundo).
**Descartado:** OpenAI — sin motivo técnico de exclusión, Claude es la primera opción. Se reevaluaría si la calidad de los informes no fuera suficiente.

---

## 002 — Base de datos: SQLite WAL mode

**Fecha:** Abril 2026
**Contexto:** Pipeline local, sin concurrencia real en la Fase 1.
**Decisión:** SQLite en WAL mode. Sin servidor, sin configuración, suficiente para el volumen esperado (cientos de leads, no millones).
**Descartado:** PostgreSQL — sobreingeniería para esta fase. Se migraría si el proyecto escala a múltiples usuarios o despliegue en servidor.

---

## 003 — Almacenamiento de contenido no estructurado: ficheros planos + SQLite

**Fecha:** Abril 2026
**Contexto:** El pipeline genera texto de tres fuentes (web, LinkedIn, YouTube) por empresa. Este contenido necesita estar disponible para el LLM y potencialmente para un RAG futuro.
**Decisión:** Ficheros `.txt` en `data/raw/{lead_id}/` para contenido no estructurado. SQLite para metadatos y referencias a rutas de ficheros. Esta separación permite que ChromaDB indexe `raw/` en cualquier momento sin modificar la arquitectura de datos.
**Descartado:** Guardar texto en SQLite directamente — limita el tamaño, complica la indexación futura y mezcla datos estructurados con texto libre.

---

## 004 — LinkedIn: scraping con sesión propia, sin API

**Fecha:** Abril 2026
**Contexto:** LinkedIn es la fuente más valiosa para prospección B2B pero no ofrece API pública accesible. El scraping sin autenticación devuelve contenido muy limitado.
**Decisión:** Selenium con sesión autenticada propia (cuenta personal del developer). Solo se extrae información visible para cualquier usuario logueado en la página pública de empresa. Delays aleatorios entre 6 y 12 segundos para comportamiento similar al humano. Máximo 30 empresas/día en consonancia con el límite de outreach.
**Riesgo asumido:** Esta práctica viola los ToS de LinkedIn (sección 8.2). El riesgo principal es la restricción temporal de la cuenta. Medidas de mitigación: volumen bajo, delays realistas, sin descarga masiva, solo info pública.
**Descartado:** Phantombuster/Apollo — herramientas de pago, añaden dependencia externa. Proxies rotativos — sobreingeniería para el volumen actual.
**Selectores CSS:** LinkedIn modifica su DOM con frecuencia. Si los selectores dejan de funcionar, inspeccionarlos manualmente en Chrome DevTools sobre una página de empresa real y actualizar `linkedin.py`. No hay alternativa automática a este mantenimiento.

---

## 005 — YouTube: yt-dlp Python library

**Fecha:** Abril 2026
**Contexto:** El developer ya tiene un script bash (`full_pipeline.sh`) que usa yt-dlp CLI para descargar transcripciones de canales completos para RAG personal.
**Decisión:** Usar yt-dlp como librería Python en lugar de invocar el script bash vía subprocess. Solo se reutilizan las Fases 1 (extracción de links) y 2 (descarga de subtítulos). Las Fases 3-4 (corpus y división) son específicas del caso RAG y no aplican aquí.
**Ventaja:** integración nativa en el pipeline Python, sin dependencias de shell ni de entorno conda `transcription`.

---

## 006 — Sin Docker

**Fecha:** Abril 2026
**Contexto:** BioPlace requería Docker para simular WordPress+WooCommerce+Dokan localmente. Prospector no tiene servidor local que simular.
**Decisión:** Sin Docker. El pipeline es puramente Python con llamadas a APIs externas (SerpAPI, Anthropic) y servicios web (LinkedIn, YouTube, webs corporativas). El único dato persistente es SQLite, un fichero local.
**Entorno de ejecución:** conda env `prospector` con las dependencias de `requirements.txt`.

---

## 007 — Ética y GDPR: datos B2B de fuentes públicas

**Fecha:** Abril 2026
**Contexto:** El pipeline recoge datos de empresas y, en algunos casos, de personas de contacto (nombre, cargo, email corporativo). El GDPR aplica a datos de personas físicas incluso en contexto profesional.
**Decisión:**
- Solo se recogen datos públicamente accesibles e indexados por buscadores.
- Los datos de personas (contactos) se limitan a información profesional pública (nombre, cargo, email corporativo).
- No se almacenan datos sensibles, privados ni de acceso restringido.
- El outreach es siempre manual y acotado (≤ 30/día). El sistema nunca envía mensajes automáticamente.
- Los datos se usan exclusivamente para comunicación comercial B2B legítima, no para perfilado, reventa ni ningún otro fin.
- Base legal para el tratamiento: interés legítimo (art. 6.1.f GDPR) en el contexto de prospección B2B directa.
**Ver también:** `docs/RULES.md` para las reglas operativas derivadas de esta decisión.

---

## 008 — Outreach: manual, acotado, nunca automatizado

**Fecha:** Abril 2026
**Contexto:** La tentación de automatizar el envío de mensajes existe (Selenium sobre LinkedIn Messaging, email masivo). Se descarta explícitamente.
**Decisión:** El sistema genera informes y registra contactos, pero el envío de cualquier mensaje es siempre manual y realizado por el developer. Límite: 30 contactos nuevos/día. Este límite es tanto ético (evitar spam) como práctico (LinkedIn penaliza el outreach masivo).
**Razón de fondo:** el valor del sistema está en la calidad del análisis previo, no en el volumen de mensajes. Un mensaje personalizado con datos reales de la empresa convierte mejor que cien mensajes genéricos.
