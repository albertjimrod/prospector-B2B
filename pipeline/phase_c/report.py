import os
import re
import sqlite3
import anthropic
from datetime import datetime
from pipeline.config import DB_PATH, RAW_DIR, REPORTS_DIR, LLM_API_KEY, PERFIL


def cargar_contenido(lead_id):
    contenido = {}
    base = os.path.join(RAW_DIR, str(lead_id))

    web_path = os.path.join(base, 'web.txt')
    if os.path.exists(web_path):
        with open(web_path, encoding='utf-8') as f:
            contenido['web'] = f.read()[:6000]

    linkedin_path = os.path.join(base, 'linkedin.txt')
    if os.path.exists(linkedin_path):
        with open(linkedin_path, encoding='utf-8') as f:
            contenido['linkedin'] = f.read()[:4000]

    youtube_dir = os.path.join(base, 'youtube')
    if os.path.exists(youtube_dir):
        transcripts = []
        for fname in sorted(os.listdir(youtube_dir))[:5]:
            fpath = os.path.join(youtube_dir, fname)
            with open(fpath, encoding='utf-8') as f:
                transcripts.append(f.read()[:2000])
        if transcripts:
            contenido['youtube'] = '\n\n---\n\n'.join(transcripts)

    return contenido


def generar_informe(client, empresa, web, contenido):
    partes = []
    if 'web' in contenido:
        partes.append(f'## CONTENIDO WEB\n{contenido["web"]}')
    if 'linkedin' in contenido:
        partes.append(f'## LINKEDIN\n{contenido["linkedin"]}')
    if 'youtube' in contenido:
        partes.append(f'## TRANSCRIPCIONES YOUTUBE\n{contenido["youtube"]}')

    if not partes:
        return None, 0.0

    prompt = f"""Eres un asistente de prospección B2B. Analiza la empresa y genera un informe estructurado para determinar si encaja con el perfil del developer y qué soluciones ofrecerle.

PERFIL DEL DEVELOPER:
{PERFIL}

EMPRESA:
Nombre: {empresa}
Web: {web}

CONTENIDO ANALIZADO:
{''.join(partes)}

Genera el informe en markdown con esta estructura exacta:

# Informe: {empresa}

## 1. Perfil de la empresa
[Sector, tamaño estimado, mercado objetivo, propuesta de valor, clientes típicos]

## 2. Madurez digital
[CMS detectado, tech stack, presencia en RRSS, canal YouTube activo o no, calidad general de la web]

## 3. Gaps detectados
[Lista numerada de problemas concretos: datos sin estructurar, procesos manuales visibles, precios sin gestión dinámica, ausencia de CRM/automatización, catálogos PDF, etc.]

## 4. Encaje con el perfil
[Qué servicios específicos del developer encajan y por qué. Cita tecnologías concretas del PERFIL.]

## 5. Soluciones propuestas
[2-3 propuestas accionables y concretas, vinculadas a RELEVANCIA_CLAVE]

## 6. Puntuación de encaje
FIT_SCORE: [0.0-1.0]
JUSTIFICACIÓN: [1-2 frases explicando la puntuación]

## 7. Análisis BANT estimado
BUDGET: [señales de capacidad de inversión: tamaño empresa, sector, precios visibles, facturación estimada, si tienen equipo o externalizan]
AUTHORITY: [probable decisor según LinkedIn y web: nombre si detectado, cargo, rol en la decisión de compra tecnológica]
NEED: [urgencia del need: ¿los gaps son críticos o nice-to-have? ¿hay señales de que están buscando solución activamente?]
TIMING: [señales de momento óptimo: web desactualizada, crecimiento reciente, nuevo producto/servicio, cambio de dirección, evento sectorial próximo]

## 8. Gancho para el primer contacto
[Detalle concreto y específico — un elemento de la web, un post reciente de LinkedIn, o un tema recurrente en YouTube — que demuestre análisis real. Debe ser el punto de partida natural de la conversación, no un elogio genérico.]"""

    resp = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=2048,
        messages=[{'role': 'user', 'content': prompt}]
    )

    informe = resp.content[0].text
    match = re.search(r'FIT_SCORE:\s*([\d.]+)', informe)
    fit_score = float(match.group(1)) if match else 0.5

    return informe, min(max(fit_score, 0.0), 1.0)


def guardar_informe(lead_id, informe, fit_score):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    path = os.path.join(REPORTS_DIR, f'{lead_id}.md')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(informe)

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('''
            INSERT OR REPLACE INTO reports (lead_id, report_path, fit_score, generated_at)
            VALUES (?,?,?,?)
        ''', (lead_id, path, fit_score, datetime.now().isoformat()))
        conn.execute('UPDATE leads SET status="reported" WHERE id=?', (lead_id,))
        conn.commit()
    finally:
        conn.close()

    return path


def registrar_run(phase, status, message):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            'INSERT INTO run_log (phase, status, message, finished_at) VALUES (?,?,?,?)',
            (phase, status, message, datetime.now().isoformat())
        )
        conn.commit()
    finally:
        conn.close()


def run(lead_id=None):
    if not LLM_API_KEY:
        raise EnvironmentError('LLM_API_KEY no configurada en .env')

    client = anthropic.Anthropic(api_key=LLM_API_KEY)

    conn = sqlite3.connect(DB_PATH)
    if lead_id:
        leads = conn.execute(
            'SELECT id, empresa, web FROM leads WHERE id=? AND status IN ("pending","enriching")',
            (lead_id,)
        ).fetchall()
    else:
        leads = conn.execute(
            'SELECT id, empresa, web FROM leads WHERE status IN ("pending","enriching")'
        ).fetchall()
    conn.close()

    print(f'[Fase C · report] {len(leads)} informes a generar')
    ok = err = 0

    for lid, empresa, web in leads:
        print(f'  Generando: {empresa}')
        try:
            contenido = cargar_contenido(lid)
            if not contenido:
                print(f'  ⚠ Sin contenido raw para {empresa}. Ejecuta Fase B primero.')
                continue

            informe, fit_score = generar_informe(client, empresa, web, contenido)
            if not informe:
                continue

            path = guardar_informe(lid, informe, fit_score)
            print(f'  ✓ fit_score={fit_score:.2f} → {path}')
            ok += 1
        except Exception as e:
            print(f'  ✗ Error en {empresa}: {e}')
            err += 1

    registrar_run('C', 'ok', f'{ok} informes generados, {err} errores')
    print(f'\n[report completado] {ok} ok, {err} errores')
