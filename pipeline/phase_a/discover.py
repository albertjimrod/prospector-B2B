import json
import sqlite3
import requests
import anthropic
from datetime import datetime
from pipeline.config import DB_PATH, LLM_API_KEY, SERPAPI_KEY, PERFIL

CCAA_CONFIG = {
    'catalunya':  {'idioma': 'ca', 'pais': 'es', 'geo': 'Barcelona OR Catalunya OR Cataluña'},
    'madrid':     {'idioma': 'es', 'pais': 'es', 'geo': 'Madrid'},
    'valencia':   {'idioma': 'es', 'pais': 'es', 'geo': 'Valencia OR Comunitat Valenciana'},
    'euskadi':    {'idioma': 'es', 'pais': 'es', 'geo': 'Bilbao OR San Sebastián OR País Vasco'},
    'andalucia':  {'idioma': 'es', 'pais': 'es', 'geo': 'Sevilla OR Málaga OR Granada OR Andalucía'},
    'aragon':     {'idioma': 'es', 'pais': 'es', 'geo': 'Zaragoza OR Aragón'},
}

SECTORES_OBJETIVO = [
    'ecommerce', 'marketplace', 'SaaS B2B', 'agencia digital', 'retail online',
    'logística', 'distribución', 'inmobiliaria', 'hostelería', 'alimentación',
    'manufactura', 'industria', 'salud digital', 'fintech', 'legaltech',
    'proptech', 'edtech', 'startup tecnología', 'software empresarial',
]


def limpiar_json(texto):
    texto = texto.strip()
    if texto.startswith('```'):
        texto = texto.split('\n', 1)[-1]
        texto = texto.rsplit('```', 1)[0]
    texto = texto.strip()
    # Intenta parsear; si falla por JSON truncado, extrae solo los campos clave
    try:
        json.loads(texto)
        return texto
    except json.JSONDecodeError:
        import re
        valid = re.search(r'"valid"\s*:\s*(true|false)', texto)
        reason = re.search(r'"reason"\s*:\s*"([^"]*)', texto)
        sector = re.search(r'"sector_detectado"\s*:\s*"([^"]*)', texto)
        nombre = re.search(r'"empresa_nombre"\s*:\s*"([^"]*)', texto)
        web = re.search(r'"web_oficial"\s*:\s*"([^"]*)', texto)
        if valid:
            return json.dumps({
                'valid': valid.group(1) == 'true',
                'reason': reason.group(1) if reason else 'respuesta truncada',
                'sector_detectado': sector.group(1) if sector else '',
                'empresa_nombre': nombre.group(1) if nombre else '',
                'web_oficial': web.group(1) if web else None,
            })
        return texto


def generar_queries(client, ccaa, config, sector=None, n_queries=8):
    sectores = [sector] if sector else SECTORES_OBJETIVO[:10]
    prompt = f"""Genera {n_queries} queries de búsqueda web para encontrar PYMEs y startups en {ccaa} que podrían necesitar servicios de datos, scraping, ETL o automatización.

Geografía: {config['geo']}
Sectores: {', '.join(sectores)}

Objetivo: llegar directamente a la web corporativa de la empresa, no a su ficha en un directorio.
Combina: tipo empresa (PYME, startup, empresa) + sector + ubicación + términos operativos ("gestión manual", "catálogo", "tarifas", "solicitar presupuesto", "sin equipo técnico").
Excluye SIEMPRE en cada query: -site:linkedin.com -site:facebook.com -site:twitter.com -site:instagram.com -site:infocif.es -site:einforma.com -site:axesor.es -filetype:pdf -site:boe.es

Devuelve SOLO un JSON array de {n_queries} strings. Sin markdown, sin explicaciones."""

    resp = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=1024,
        messages=[{'role': 'user', 'content': prompt}]
    )
    return json.loads(limpiar_json(resp.content[0].text))


def buscar_leads(query, idioma, pais, num=10):
    if not SERPAPI_KEY:
        raise EnvironmentError('SERPAPI_KEY no configurada en .env')
    params = {
        'api_key': SERPAPI_KEY,
        'q': query,
        'hl': idioma,
        'gl': pais,
        'num': num,
        'engine': 'google',
    }
    resp = requests.get('https://serpapi.com/search', params=params, timeout=30)
    resp.raise_for_status()
    return [
        {'url': r.get('link'), 'title': r.get('title', ''), 'snippet': r.get('snippet', '')}
        for r in resp.json().get('organic_results', [])
        if r.get('link')
    ]


def validar_lead(client, title, url, snippet):
    prompt = f"""Evalúa si esta empresa podría beneficiarse de servicios de un Python developer especializado en web scraping, ETL, pricing intelligence y automatización para PYMEs.

PERFIL DEL DEVELOPER:
{PERFIL}

EMPRESA:
Nombre: {title}
URL: {url}
Descripción: {snippet}

VÁLIDO si: PYME o startup sin equipo de datos propio, señales de proceso manual, datos sin estructurar, precios o catálogos sin gestionar, sector con volumen de datos explotable.
NO VÁLIDO si: gran corporación con equipo propio, empresa de servicios de datos (competencia directa), perfil irrelevante.

Si la URL es una ficha de directorio (infocif, einforma, linkedin.com/company...), extrae la web oficial de la empresa si aparece en el snippet.

Responde SOLO con JSON:
{{"valid": true/false, "reason": "...", "sector_detectado": "...", "empresa_nombre": "...", "web_oficial": "URL o null"}}"""

    resp = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=512,
        messages=[{'role': 'user', 'content': prompt}]
    )
    return json.loads(limpiar_json(resp.content[0].text))


def guardar_lead(empresa, ccaa, sector, web, fuente):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            'INSERT OR IGNORE INTO leads (empresa, ccaa, sector, web, fuente) VALUES (?,?,?,?,?)',
            (empresa, ccaa, sector, web, fuente)
        )
        conn.commit()
    finally:
        conn.close()


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


def run(ccaa='catalunya', sector=None, n_queries=8, results_per_query=10, max_leads=None):
    if not SERPAPI_KEY:
        raise EnvironmentError('SERPAPI_KEY no configurada en .env')
    if not LLM_API_KEY:
        raise EnvironmentError('LLM_API_KEY no configurada en .env')

    client = anthropic.Anthropic(api_key=LLM_API_KEY)
    config = CCAA_CONFIG.get(ccaa, CCAA_CONFIG['catalunya'])

    print(f'[Fase A · {ccaa}] Generando {n_queries} queries...')
    try:
        queries = generar_queries(client, ccaa, config, sector, n_queries)
    except Exception as e:
        registrar_run('A', 'error', str(e))
        raise

    validos = 0
    for i, query in enumerate(queries, 1):
        if max_leads and validos >= max_leads:
            print(f'  Límite alcanzado ({max_leads} leads). Parando.')
            break
        print(f'  Query {i}/{len(queries)}: {query}')
        try:
            resultados = buscar_leads(query, config['idioma'], config['pais'], results_per_query)
        except Exception as e:
            print(f'  ⚠ Error SerpAPI: {e}')
            continue

        for r in resultados:
            if max_leads and validos >= max_leads:
                break
            try:
                v = validar_lead(client, r['title'], r['url'], r['snippet'])
                if v.get('valid'):
                    web = v.get('web_oficial') or r['url']
                    guardar_lead(
                        empresa=v.get('empresa_nombre') or r['title'],
                        ccaa=ccaa,
                        sector=v.get('sector_detectado') or sector or '',
                        web=web,
                        fuente=query,
                    )
                    validos += 1
                    print(f'  ✓ {v.get("empresa_nombre") or r["title"]} → {web}')
                else:
                    print(f'  ✗ {r["url"][:60]} — {v.get("reason", "")}')
            except Exception as e:
                print(f'  ⚠ Error validando {r["url"]}: {e}')

    msg = f'{validos} leads válidos guardados para {ccaa}'
    registrar_run('A', 'ok', msg)
    print(f'\n[Fase A completada] {msg}')
