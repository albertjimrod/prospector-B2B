import os
import re
import sqlite3
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from pipeline.config import DB_PATH, RAW_DIR

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
}

CMS_PATTERNS = {
    'WordPress':   [r'wp-content', r'wp-includes', r'xmlrpc\.php'],
    'Shopify':     [r'cdn\.shopify\.com', r'shopify\.theme'],
    'Wix':         [r'static\.wixstatic\.com', r'wixsite\.com'],
    'Squarespace': [r'squarespace\.com', r'squarespace-cdn'],
    'Webflow':     [r'webflow\.com'],
    'Joomla':      [r'joomla'],
    'Drupal':      [r'drupal'],
    'PrestaShop':  [r'prestashop'],
    'Magento':     [r'magento', r'mage/'],
}

SOCIAL_PATTERNS = {
    'linkedin_url': r'https?://(?:www\.)?linkedin\.com/company/[\w\-]+',
    'twitter_x':    r'https?://(?:www\.)?(?:twitter|x)\.com/[\w]+',
    'instagram':    r'https?://(?:www\.)?instagram\.com/[\w\.]+',
    'facebook':     r'https?://(?:www\.)?facebook\.com/[\w\.]+',
    'youtube_url':  r'https?://(?:www\.)?youtube\.com/(?:@[\w\-]+|channel/[\w\-]+|c/[\w\-]+)',
}

CRM_TAGS = ['hubspot', 'salesforce', 'pardot', 'zoho', 'pipedrive', 'intercom', 'zendesk', 'zopim', 'freshdesk']
RRSS_WHITELIST = {'linkedin_url', 'twitter_x', 'instagram', 'facebook', 'youtube_url', 'youtube_channel_id'}


def detectar_cms(html_lower):
    for cms, patterns in CMS_PATTERNS.items():
        if any(re.search(p, html_lower) for p in patterns):
            return cms
    return None


def detectar_stack(html_lower, response_headers):
    stack = []
    server = response_headers.get('Server', '').split('/')[0].strip()
    powered = response_headers.get('X-Powered-By', '').strip()
    if server:
        stack.append(server)
    if powered:
        stack.append(powered)
    if re.search(r'__reactroot|reactdom|react\.development', html_lower):
        stack.append('React')
    if re.search(r'__vue__|vue\.min\.js', html_lower):
        stack.append('Vue.js')
    if '_next/' in html_lower:
        stack.append('Next.js')
    if 'angular' in html_lower and 'ng-version' in html_lower:
        stack.append('Angular')
    return ', '.join(dict.fromkeys(stack)) or None


def detectar_rrss(html):
    encontrados = {}
    for campo, pattern in SOCIAL_PATTERNS.items():
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            encontrados[campo] = match.group(0)
    return encontrados


def detectar_senales(html_lower, soup):
    signals = []
    if soup.find_all('a', href=re.compile(r'\.pdf', re.I)):
        signals.append('catalogo_pdf')
    if soup.find_all(class_=re.compile(r'price|precio|tarifa|coste', re.I)):
        signals.append('precios_visibles')
    if 'whatsapp' in html_lower or 'wa.me/' in html_lower:
        signals.append('contacto_whatsapp')
    if not any(w in html_lower for w in ['añadir al carrito', 'add to cart', 'buy now', 'checkout', 'comprar ahora']):
        signals.append('sin_ecommerce')
    if soup.find_all('form'):
        signals.append('formularios')
    for crm in CRM_TAGS:
        if crm in html_lower:
            signals.append(f'crm_{crm}')
    if re.search(r'presupuesto|solicitar oferta|pedir precio|contacta para', html_lower):
        signals.append('precio_consultar')
    return signals


def descargar_web(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        return resp.text, dict(resp.headers)
    except Exception:
        return None, {}


def extraer_texto(html):
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'meta', 'link', 'noscript']):
        tag.decompose()
    return soup.get_text(separator=' ', strip=True)[:8000]


def guardar_raw(lead_id, contenido):
    path = os.path.join(RAW_DIR, str(lead_id), 'web.txt')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(contenido)
    return path


def guardar_audit(lead_id, cms, stack, signals, raw_path):
    has_crm = any('crm_' in s for s in signals)
    has_pdf = 'catalogo_pdf' in signals
    has_prices = 'precios_visibles' in signals
    tech = ' · '.join(filter(None, [cms, stack])) or 'desconocido'

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('''
            INSERT OR REPLACE INTO web_audit
            (lead_id, tech_stack, has_cms, has_crm, has_static_prices, has_pdf_catalog,
             manual_process_signals, raw_text_path, audited_at)
            VALUES (?,?,?,?,?,?,?,?,?)
        ''', (lead_id, tech, 1 if cms else 0, 1 if has_crm else 0,
              1 if has_prices else 0, 1 if has_pdf else 0,
              ', '.join(signals), raw_path, datetime.now().isoformat()))
        conn.commit()
    finally:
        conn.close()


def guardar_rrss(lead_id, rrss):
    if not rrss:
        return
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('INSERT OR IGNORE INTO rrss (lead_id) VALUES (?)', (lead_id,))
        for campo, valor in rrss.items():
            if campo in RRSS_WHITELIST:
                conn.execute(f'UPDATE rrss SET {campo}=? WHERE lead_id=?', (valor, lead_id))
        conn.commit()
    finally:
        conn.close()


def actualizar_status(lead_id, status):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('UPDATE leads SET status=? WHERE id=?', (status, lead_id))
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


def run(lead_id=None):
    conn = sqlite3.connect(DB_PATH)
    if lead_id:
        leads = conn.execute(
            'SELECT id, empresa, web FROM leads WHERE id=? AND status IN ("pending","enriching")',
            (lead_id,)
        ).fetchall()
    else:
        leads = conn.execute(
            'SELECT id, empresa, web FROM leads WHERE status="pending"'
        ).fetchall()
    conn.close()

    print(f'[Fase B · web_audit] {len(leads)} leads a procesar')
    ok = err = 0

    for lid, empresa, web in leads:
        if not web:
            continue
        print(f'  Auditando: {empresa} ({web})')
        html, resp_headers = descargar_web(web)
        if not html:
            print(f'  ⚠ No se pudo descargar {web}')
            err += 1
            continue

        html_lower = html.lower()
        soup = BeautifulSoup(html, 'html.parser')
        cms = detectar_cms(html_lower)
        stack = detectar_stack(html_lower, resp_headers)
        rrss = detectar_rrss(html)
        signals = detectar_senales(html_lower, soup)

        texto = extraer_texto(html)
        raw_path = guardar_raw(lid, texto)
        guardar_audit(lid, cms, stack, signals, raw_path)
        guardar_rrss(lid, rrss)
        actualizar_status(lid, 'enriching')

        rrss_found = ', '.join(k for k in rrss) or '—'
        print(f'  ✓ CMS:{cms or "—"} | Stack:{stack or "—"} | RRSS:{rrss_found} | Señales:{len(signals)}')
        ok += 1

    registrar_run('B_web', 'ok', f'{ok} auditados, {err} errores')
    print(f'\n[web_audit completado] {ok} ok, {err} errores')
