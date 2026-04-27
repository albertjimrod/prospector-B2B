import os
import sqlite3
from datetime import datetime
from pipeline.config import DB_PATH, REPORTS_DIR


def listar_leads(min_fit=0.5):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute('''
        SELECT l.id, l.empresa, l.ccaa, l.sector, l.web, l.status,
               COALESCE(r.fit_score, 0) as fit,
               o.status as out_status
        FROM leads l
        LEFT JOIN reports r ON l.id=r.lead_id
        LEFT JOIN outreach o ON l.id=o.lead_id
        WHERE COALESCE(r.fit_score, 0) >= ?
        ORDER BY fit DESC
    ''', (min_fit,)).fetchall()
    conn.close()
    return rows


def ver_informe(lead_id):
    path = os.path.join(REPORTS_DIR, f'{lead_id}.md')
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            print(f.read())
    else:
        print(f'Sin informe generado para lead {lead_id}. Ejecuta Fase C primero.')


def registrar_contacto(lead_id, canal, notas=''):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('''
            INSERT INTO outreach (lead_id, channel, status, sent_at, notes)
            VALUES (?,?,?,?,?)
        ''', (lead_id, canal, 'sent', datetime.now().isoformat(), notas))
        conn.execute('UPDATE leads SET status="contacted" WHERE id=?', (lead_id,))
        conn.commit()
    finally:
        conn.close()


def actualizar_outreach(lead_id, nuevo_status, notas=''):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            'UPDATE outreach SET status=?, notes=? WHERE lead_id=?',
            (nuevo_status, notas, lead_id)
        )
        conn.commit()
    finally:
        conn.close()


def run():
    print('\n══════════════════════════════════════')
    print('  PROSPECTOR · Outreach Tracker')
    print('══════════════════════════════════════')
    print('Comandos: [l]istar  [v]er  [c]ontactar  [u]pdate  [s]alir\n')

    while True:
        try:
            cmd = input('> ').strip().lower()
        except (KeyboardInterrupt, EOFError):
            break

        if cmd in ('s', 'salir', 'q', 'exit'):
            break

        elif cmd in ('l', 'listar'):
            fit_input = input('Fit mínimo (0.0-1.0, Enter=0.5): ').strip()
            min_fit = float(fit_input) if fit_input else 0.5
            rows = listar_leads(min_fit)
            if not rows:
                print('Sin resultados con ese fit mínimo.\n')
                continue
            print(f'\n{"ID":>4}  {"Empresa":<28}  {"Fit":>5}  {"Status":<12}  {"Outreach":<10}  CCAA')
            print('─' * 80)
            for lid, empresa, ccaa, sector, web, status, fit, out_status in rows:
                print(f'{lid:>4}  {(empresa or "")[:26]:<28}  {fit:>5.2f}  {(status or ""):<12}  {(out_status or "—"):<10}  {ccaa or ""}')
            print()

        elif cmd in ('v', 'ver'):
            lid = input('ID del lead: ').strip()
            if lid.isdigit():
                ver_informe(int(lid))

        elif cmd in ('c', 'contactar'):
            lid = input('ID del lead: ').strip()
            canal = input('Canal (email/linkedin/phone): ').strip()
            notas = input('Notas: ').strip()
            if lid.isdigit():
                registrar_contacto(int(lid), canal, notas)
                print(f'✓ Contacto registrado para lead {lid}\n')

        elif cmd in ('u', 'update'):
            lid = input('ID del lead: ').strip()
            nuevo_status = input('Nuevo status (sent/replied/no_reply/discarded): ').strip()
            notas = input('Notas adicionales: ').strip()
            if lid.isdigit():
                actualizar_outreach(int(lid), nuevo_status, notas)
                print(f'✓ Actualizado\n')

        else:
            print('Comando no reconocido. Usa: l, v, c, u, s\n')
