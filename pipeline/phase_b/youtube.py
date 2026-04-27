import os
import re
import sqlite3
import tempfile
from datetime import datetime
from yt_dlp import YoutubeDL
from pipeline.config import DB_PATH, RAW_DIR


def vtt_a_texto(contenido_vtt):
    """Convierte VTT a texto plano limpio. Equivalente a subs_to_text del pipeline bash."""
    lines = contenido_vtt.split('\n')
    textos = []
    prev = ''
    for line in lines:
        line = line.strip()
        if (not line
                or line.startswith('WEBVTT')
                or line.startswith('Kind:')
                or line.startswith('Language:')
                or line.startswith('NOTE')
                or re.match(r'^\d{2}:\d{2}', line)
                or re.match(r'^\d+$', line)
                or 'align:' in line
                or 'position:' in line):
            continue
        line = re.sub(r'<[^>]+>', ' ', line)
        line = re.sub(r'&[a-z]+;', ' ', line)
        line = ' '.join(line.split())
        if line and line != prev:
            textos.append(line)
            prev = line
    texto = ' '.join(textos)
    texto = re.sub(r'([.!?]) ', r'\1\n', texto)
    return texto.strip()


def obtener_videos_canal(channel_url, max_videos=20):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': 'in_playlist',
        'skip_download': True,
        'playlistend': max_videos,
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)
        if not info:
            return []
        entries = info.get('entries') or []
        return [
            {
                'id': e.get('id'),
                'title': e.get('title', ''),
                'url': e.get('url') or f"https://www.youtube.com/watch?v={e.get('id')}",
            }
            for e in entries if e and e.get('id')
        ]


def descargar_transcript(video_url, lang='es'):
    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': [lang, f'{lang}-ES', 'ca', 'en'],
            'subtitlesformat': 'vtt',
            'outtmpl': os.path.join(tmpdir, '%(id)s.%(ext)s'),
        }
        try:
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
        except Exception:
            return None

        for fname in os.listdir(tmpdir):
            if fname.endswith('.vtt'):
                with open(os.path.join(tmpdir, fname), 'r', encoding='utf-8', errors='ignore') as f:
                    return vtt_a_texto(f.read())
    return None


def guardar_transcript(lead_id, video_id, titulo, contenido):
    path = os.path.join(RAW_DIR, str(lead_id), 'youtube', f'{video_id}.txt')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f'# Título: {titulo}\n# Video ID: {video_id}\n\n{contenido}')
    return path


def guardar_video_db(lead_id, video_id, titulo, transcript_path):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('''
            INSERT OR IGNORE INTO youtube_videos (lead_id, video_id, title, transcript_path)
            VALUES (?,?,?,?)
        ''', (lead_id, video_id, titulo, transcript_path))
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


def run(lead_id=None, lang='es', max_videos=20):
    conn = sqlite3.connect(DB_PATH)
    if lead_id:
        leads = conn.execute('''
            SELECT l.id, l.empresa, r.youtube_url
            FROM leads l JOIN rrss r ON l.id=r.lead_id
            WHERE l.id=? AND r.youtube_url IS NOT NULL
        ''', (lead_id,)).fetchall()
    else:
        leads = conn.execute('''
            SELECT l.id, l.empresa, r.youtube_url
            FROM leads l JOIN rrss r ON l.id=r.lead_id
            WHERE r.youtube_url IS NOT NULL AND l.status IN ("pending","enriching")
        ''').fetchall()
    conn.close()

    if not leads:
        print('[Fase B · youtube] Sin leads con canal YouTube. Saltando.')
        return

    print(f'[Fase B · youtube] {len(leads)} canales a procesar')
    ok = err = 0

    for lid, empresa, youtube_url in leads:
        print(f'  Canal: {empresa} ({youtube_url})')
        try:
            videos = obtener_videos_canal(youtube_url, max_videos)
            if not videos:
                print(f'  ⚠ Canal sin vídeos accesibles')
                continue

            print(f'  → {len(videos)} vídeos encontrados')
            transcritos = 0
            for video in videos:
                vid_id = video['id']
                titulo = video['title']
                transcript = descargar_transcript(video['url'], lang)
                if transcript:
                    path = guardar_transcript(lid, vid_id, titulo, transcript)
                    guardar_video_db(lid, vid_id, titulo, path)
                    transcritos += 1

            print(f'  ✓ {transcritos}/{len(videos)} transcripciones descargadas')
            ok += 1
        except Exception as e:
            print(f'  ✗ Error en {empresa}: {e}')
            err += 1

    registrar_run('B_youtube', 'ok', f'{ok} canales procesados, {err} errores')
    print(f'\n[youtube completado] {ok} ok, {err} errores')
