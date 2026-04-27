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

---

## 009 — Taxonomía de leads: suspect / prospect / lead

**Fecha:** Abril 2026
**Contexto:** Tras análisis de la metodología de prospecta-gs.com, el campo `leads.status` inicial solo tenía 4 estados (`pending → enriching → reported → contacted`). Eso mezclaba el estado de proceso del pipeline con el estado comercial del lead.
**Decisión:** Extender el campo con la taxonomía B2B estándar: `suspect` (encaja en el ICP, vale la pena contactar), `prospect` (ha respondido, hay conversación), `lead` (reunión confirmada), `closed_won/lost`. La transición `reported → suspect` es manual (el developer decide si vale contactar tras leer el informe). Las demás transiciones son automáticas al actualizar el outreach.
**Descartado:** mantener `contacted` como único estado post-informe — pierde la granularidad necesaria para gestionar el embudo y medir conversiones reales.

---

## 010 — BANT estimado en informes: deducción, no encuesta

**Fecha:** Abril 2026
**Contexto:** El framework BANT (Budget, Authority, Need, Timing) es el estándar de calificación B2B. La información real de BANT requiere una conversación con el cliente. Sin embargo, parte de ella es deducible del contenido público analizado.
**Decisión:** Añadir una sección 7 "Análisis BANT estimado" al informe LLM. El LLM deduce señales (no respuestas definitivas) para cada dimensión: precios visibles → Budget, cargo del decisor en LinkedIn → Authority, criticidad de los gaps → Need, eventos recientes → Timing. El informe deja claro que son estimaciones, no datos confirmados.
**Valor:** permite al developer priorizar el outreach antes de cualquier conversación. Un lead con BANT favorable en todas las dimensiones sube en la cola aunque tenga fit_score medio.

---

## 011 — Outreach multi-touch: attempt_number + next_contact_at

**Fecha:** Abril 2026
**Contexto:** La Fase D original registraba un único contacto por lead. La investigación de metodología B2B indica que se necesitan entre 6 y 10 touchpoints para cerrar (Gartner). Un sistema de contacto único no refleja la realidad del ciclo de venta.
**Decisión:** La tabla `outreach` permite múltiples filas por lead, cada una con `attempt_number` auto-incrementado y `next_contact_at` para programar el seguimiento. La función `listar_seguimientos()` filtra leads con seguimiento vencido. La interfaz interactiva (Fase D) incluye el comando `f` para ver la cola de seguimientos del día.
**Límite operativo:** el developer sigue sin poder enviar más de 30 contactos/día (ver decisión 008). El multi-touch es para gestionar el ciclo largo, no para bombardear.

---

## 012 — Identificación de decisores: /people/ de LinkedIn + CARGOS_DECISOR

**Fecha:** Abril 2026
**Contexto:** Contactar al decisor real (quien tiene autoridad de compra) es más efectivo que contactar a cualquier persona de la empresa. La Fase B original extraía datos de la empresa pero no de las personas.
**Decisión:** Añadir en `linkedin.py` la función `extraer_decisores()` que navega a `{linkedin_url}/people/` y filtra perfiles por `CARGOS_DECISOR` (lista de 20 términos en ES/EN). Se guardan hasta 3 decisores por empresa en la tabla `contactos` con `is_decision_maker=1`. La Fase D los muestra con el comando `p`.
**Limitación:** la pestaña `/people/` solo muestra los primeros empleados que LinkedIn decide mostrar. No es una lista completa. En empresas pequeñas (<10 empleados) suele aparecer el fundador o CEO sin necesidad de filtrar.
**Complemento web:** `web_audit.py` extrae emails de la home y de la página de equipo/contacto. Combinados con los decisores de LinkedIn, el developer puede elegir el canal más directo.
