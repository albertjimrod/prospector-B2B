import json
import sqlite3
import requests
import anthropic
from datetime import datetime
from pipeline.config import DB_PATH, LLM_API_KEY, SERPAPI_KEY, PERFIL

DIRECTORIOS_BLACKLIST = [
    'elreferente.es', 'expansion.com', 'infocif.es', 'einforma.com', 'axesor.es',
    'empresite.eleconomista.es', 'infoempresa.com', 'guiaempresas.eu',
    'kompass.com', 'europages.es', 'paginasamarillas.es', 'qdq.com',
    'infonegociosgalicia.es', 'bcncl.es', 'hosteltactil.com',
]

CCAA_CONFIG = {
    'españa':     {'idioma': 'es', 'pais': 'es', 'geo': 'España'},
    'catalunya':  {'idioma': 'ca', 'pais': 'es', 'geo': 'Barcelona OR Catalunya OR Cataluña'},
    'madrid':     {'idioma': 'es', 'pais': 'es', 'geo': 'Madrid'},
    'valencia':   {'idioma': 'es', 'pais': 'es', 'geo': 'Valencia OR Comunitat Valenciana'},
    'euskadi':    {'idioma': 'es', 'pais': 'es', 'geo': 'Bilbao OR San Sebastián OR País Vasco'},
    'andalucia':  {'idioma': 'es', 'pais': 'es', 'geo': 'Sevilla OR Málaga OR Granada OR Andalucía'},
    'aragon':     {'idioma': 'es', 'pais': 'es', 'geo': 'Zaragoza OR Aragón'},
}

SECTORES_OBJETIVO = [
    'startup SaaS B2B', 'startup datos', 'startup ecommerce',
    'scaleup tecnología', 'empresa producto digital',
    'marketplace online', 'plataforma SaaS',
    'ecommerce con catálogo grande', 'retail tech',
    'proptech', 'fintech pequeña', 'legaltech',
    'healthtech', 'edtech', 'insurtech',
    'agencia datos', 'consultora analytics pequeña',
    'empresa con equipo producto pero sin data engineer',
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
    prompt = f"""Genera {n_queries} queries de búsqueda para encontrar startups y empresas tecnológicas españolas con producto digital propio.

Geografía: {config['geo']}
Sectores (elige los más adecuados): {', '.join(sectores)}

TÉCNICA: busca webs corporativas de empresas con producto tech propio, no agencias ni consultoras.
Usa frases que aparecen en webs de producto:
- "nuestra plataforma" OR "nuestro producto" + sector + España
- "startup" + sector + España + "equipo"
- inurl:about OR inurl:nosotros + sector tech + España
- "SaaS" + sector + España + "pricing" OR "planes"
- "marketplace" OR "plataforma" + sector + España site:.es

Cada query debe:
1. Apuntar a la web corporativa de una startup o empresa con producto digital.
2. Excluir portales de empleo y directorios: -site:linkedin.com -site:infojobs.net -site:tecnoempleo.com -site:indeed.com -site:glassdoor.com -site:freelancer.es -site:bebee.com -site:talent.com -site:infocif.es -site:einforma.com -filetype:pdf

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


def es_directorio(url):
    return any(d in url for d in DIRECTORIOS_BLACKLIST)


def validar_lead(client, title, url, snippet):
    if es_directorio(url):
        return {'valid': False, 'reason': 'URL de directorio en blacklist', 'sector_detectado': '', 'empresa_nombre': title, 'web_oficial': None}

    prompt = f"""Evalúa si esta empresa es un cliente potencial para un Python developer freelance especializado en scraping, ETL, pricing intelligence y ML aplicado.

PERFIL DEL DEVELOPER:
{PERFIL}

EMPRESA:
Nombre: {title}
URL: {url}
Descripción: {snippet}

VÁLIDO si se cumple AL MENOS UNA de estas condiciones:
1. Startup o empresa tech con producto propio que externaliza o busca colaboración en datos, scraping, ETL o ML — aunque tenga equipo técnico interno.
2. Empresa con volumen de datos (catálogo, precios, marketplace, usuarios) que necesita automatización o inteligencia de datos y no tiene data engineer dedicado.
3. Señal explícita de búsqueda de freelance o colaboración externa en áreas de datos/Python.

NO VÁLIDO si:
- Es una gran corporación con departamento de datos propio consolidado.
- Es competencia directa (agencia de datos, consultoría analytics que ofrece los mismos servicios).
- Es un directorio, artículo, portal de empleo, incubadora o medio de comunicación.
- No hay ninguna relación con datos, automatización o tecnología.

Responde SOLO con JSON:
{{"valid": true/false, "reason": "señal concreta que justifica la decisión", "sector_detectado": "...", "empresa_nombre": "...", "web_oficial": "URL o null"}}"""

    resp = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=512,
        messages=[{'role': 'user', 'content': prompt}]
    )
    return json.loads(limpiar_json(resp.content[0].text))


def url_ya_procesada(url):
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute('SELECT id FROM leads WHERE web=?', (url,)).fetchone()
        return row is not None
    finally:
        conn.close()


def guardar_lead(empresa, ccaa, sector, web, fuente, status='pending'):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            'INSERT OR IGNORE INTO leads (empresa, ccaa, sector, web, fuente, status) VALUES (?,?,?,?,?,?)',
            (empresa, ccaa, sector, web, fuente, status)
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
            url = r['url']
            if url_ya_procesada(url):
                print(f'  · {url[:60]} — ya procesada, saltando')
                continue
            try:
                v = validar_lead(client, r['title'], url, r['snippet'])
                web = v.get('web_oficial') or url
                if v.get('valid'):
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
                    guardar_lead(
                        empresa=v.get('empresa_nombre') or r['title'],
                        ccaa=ccaa,
                        sector=v.get('sector_detectado') or sector or '',
                        web=web,
                        fuente=query,
                        status='closed_lost',
                    )
                    print(f'  ✗ {r["title"][:50]} — {v.get("reason", "")}')
            except Exception as e:
                print(f'  ⚠ Error validando {url}: {e}')

    msg = f'{validos} leads válidos guardados para {ccaa}'
    registrar_run('A', 'ok', msg)
    print(f'\n[Fase A completada] {msg}')
