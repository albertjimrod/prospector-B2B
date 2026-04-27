# RULES.md — Reglas operativas de uso

Referencia rápida antes de cada sesión de trabajo con el sistema. Derivadas de las decisiones 007 y 008 de DECISIONS.md.

---

## Qué está permitido

- Recoger datos de empresas de fuentes públicas: webs corporativas, páginas públicas de LinkedIn, canales de YouTube, directorios empresariales (infocif, einforma, expansión, Crunchbase).
- Almacenar nombre de empresa, web, sector, CCAA, tech stack y señales de proceso manual.
- Almacenar datos profesionales públicos de personas de contacto: nombre, cargo, email corporativo, URL de perfil LinkedIn.
- Scraping de la página pública de empresa en LinkedIn usando sesión propia, con delays realistas y volumen bajo.
- Descargar transcripciones de vídeos públicos de YouTube.
- Generar informes internos de análisis para uso propio.
- Contactar manualmente con empresas por email, LinkedIn o teléfono.

## Qué NO está permitido

- Automatizar el envío de mensajes o el contacto directo con personas.
- Superar 30 contactos nuevos por día.
- Recoger datos privados, de acceso restringido o no indexados públicamente.
- Almacenar contraseñas, tokens de sesión o credenciales de terceros.
- Revender, ceder o compartir los datos recogidos con terceros.
- Usar los datos para perfilado de personas físicas más allá del contexto B2B profesional.
- Ignorar `robots.txt` o condiciones de uso de las fuentes cuando prohíban expresamente el scraping automatizado.
- Crear cuentas falsas o usar proxies para eludir restricciones de plataformas.
- Contactar a personas que hayan solicitado no ser contactadas (opt-out).

## Límites operativos

| Parámetro | Límite | Razón |
|---|---|---|
| Contactos nuevos/día | ≤ 30 | Evitar spam y penalizaciones de LinkedIn |
| Scrapes LinkedIn/día | ≤ 30 | Proporcional al límite de contactos |
| Queries SerpAPI/día | ≤ 50 | Cuota del plan gratuito (100/mes) |
| Vídeos YouTube por empresa | ≤ 20 | Suficiente para perfil, sin abuso de API |

## Ante una duda

Si no está claro si una acción está permitida, la regla es: **¿estaría cómodo explicando esto públicamente?** Si la respuesta es no, no hacerlo.
