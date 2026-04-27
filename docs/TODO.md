# TODO.md

Màxim 3 coses. Quan n'entri una, en surt una.

---

## Ara mateix

1. Recrear BD con el schema actualizado: `rm data/pipeline.db && conda run -n prospector python db/init_db.py`
2. Fix Fase A: `max_tokens` 256 → 512 en `validar_lead` + prompt `generar_queries` para evitar URLs de LinkedIn y directorios
3. Commit y push a GitHub

---

## Pendent (no tocar fins que les 3 de dalt estiguin fetes)

- Verificar selectores Selenium de LinkedIn con una empresa real (tras primer run completo)
- Añadir CCAA adicionales al CCAA_CONFIG (Galicia, Canarias, Murcia)
- Implementar exportación de informes a CSV para revisión masiva
