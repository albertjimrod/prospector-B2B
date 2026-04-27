import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH     = os.path.join(BASE_DIR, 'data', 'pipeline.db')
RAW_DIR     = os.path.join(BASE_DIR, 'data', 'raw')
REPORTS_DIR = os.path.join(BASE_DIR, 'reports')

LLM_API_KEY       = os.environ.get('LLM_API_KEY', '')
SERPAPI_KEY       = os.environ.get('SERPAPI_KEY', '')
LINKEDIN_EMAIL    = os.environ.get('LINKEDIN_EMAIL', '')
LINKEDIN_PASSWORD = os.environ.get('LINKEDIN_PASSWORD', '')

_PERFIL_PATH = os.path.join(BASE_DIR, 'docs', 'perfil_analista.md')

def _cargar_perfil():
    if not os.path.exists(_PERFIL_PATH):
        raise FileNotFoundError(
            f'Falta docs/perfil_analista.md. Crea el fichero con tu perfil antes de ejecutar el pipeline.'
        )
    with open(_PERFIL_PATH, encoding='utf-8') as f:
        contenido = f.read().strip()
    if not contenido:
        raise ValueError('docs/perfil_analista.md está vacío. Rellénalo antes de ejecutar el pipeline.')
    return contenido

PERFIL = _cargar_perfil()
