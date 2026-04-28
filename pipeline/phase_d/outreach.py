import os
import subprocess
import sqlite3
from datetime import datetime, date
from pipeline.config import DB_PATH, REPORTS_DIR


def listar_leads(min_fit=0.5, status=None):
    conn = sqlite3.connect(DB_PATH)
    query = '''
        SELECT l.id, l.empresa, l.ccaa, l.sector, l.status,
               COALESCE(r.fit_score, 0) as fit,
               COUNT(o.id) as intentos,
               MAX(o.sent_at) as ultimo_contacto,
               MIN(CASE WHEN o.next_contact_at IS NOT NULL THEN o.next_contact_at END) as proximo
        FROM leads l
        LEFT JOIN reports r ON l.id=r.lead_id
        LEFT JOIN outreach o ON l.id=o.lead_id
        WHERE COALESCE(r.fit_score, 0) >= ?
    '''
    params = [min_fit]
    if status:
        query += ' AND l.status=?'
        params.append(status)
    query += ' GROUP BY l.id ORDER BY fit DESC'
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


def listar_seguimientos():
    """Leads con seguimiento pendiente para hoy o anterior."""
    hoy = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute('''
        SELECT l.id, l.empresa, l.ccaa, l.status,
               COALESCE(r.fit_score, 0) as fit,
               o.next_contact_at, o.channel, o.attempt_number
        FROM leads l
        JOIN outreach o ON l.id=o.lead_id
        LEFT JOIN reports r ON l.id=r.lead_id
        WHERE o.next_contact_at <= ?
          AND l.status NOT IN ('closed_won','closed_lost')
        ORDER BY o.next_contact_at ASC
    ''', (hoy,)).fetchall()
    conn.close()
    return rows


def ver_informe(lead_id):
    path = os.path.join(REPORTS_DIR, f'{lead_id}.md')
    if os.path.exists(path):
        subprocess.run(['less', '-R', path])
    else:
        print(f'Sin informe para lead {lead_id}. Ejecuta Fase C primero.')


def ver_historial(lead_id):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute('''
        SELECT attempt_number, channel, status, sent_at, next_contact_at, notes
        FROM outreach WHERE lead_id=? ORDER BY attempt_number ASC
    ''', (lead_id,)).fetchall()
    empresa = conn.execute('SELECT empresa FROM leads WHERE id=?', (lead_id,)).fetchone()
    conn.close()

    if not rows:
        print(f'Sin historial de contacto para lead {lead_id}.')
        return

    print(f'\n── Historial: {empresa[0] if empresa else lead_id} ──')
    for num, canal, status, sent_at, next_at, notes in rows:
        print(f'  #{num} [{canal}] {status} · {sent_at[:10] if sent_at else "—"}')
        if next_at:
            print(f'     Próximo: {next_at[:10]}')
        if notes:
            print(f'     Notas: {notes}')
    print()


def ver_contactos(lead_id):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute('''
        SELECT nombre, cargo, email, linkedin_profile_url, is_decision_maker
        FROM contactos WHERE lead_id=? ORDER BY is_decision_maker DESC
    ''', (lead_id,)).fetchall()
    conn.close()
    if not rows:
        print(f'Sin contactos registrados para lead {lead_id}.')
        return
    print(f'\n── Contactos lead {lead_id} ──')
    for nombre, cargo, email, li_url, decisor in rows:
        tag = ' [DECISOR]' if decisor else ''
        print(f'  {nombre or "—"} · {cargo or "—"} · {email or "—"}{tag}')
        if li_url:
            print(f'     {li_url}')
    print()


def registrar_contacto(lead_id, canal, notas='', next_contact_at=None):
    conn = sqlite3.connect(DB_PATH)
    try:
        ultimo = conn.execute(
            'SELECT MAX(attempt_number) FROM outreach WHERE lead_id=?', (lead_id,)
        ).fetchone()[0] or 0
        attempt = ultimo + 1

        conn.execute('''
            INSERT INTO outreach (lead_id, channel, status, attempt_number, sent_at, next_contact_at, notes)
            VALUES (?,?,?,?,?,?,?)
        ''', (lead_id, canal, 'sent', attempt, datetime.now().isoformat(), next_contact_at, notas))

        # Avanzar status del lead si procede
        status_actual = conn.execute('SELECT status FROM leads WHERE id=?', (lead_id,)).fetchone()[0]
        if status_actual in ('reported', 'suspect'):
            conn.execute('UPDATE leads SET status="suspect" WHERE id=?', (lead_id,))
        conn.commit()
    finally:
        conn.close()


def calificar_lead(lead_id):
    """Transición manual de reported → suspect: decisión de contactar."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            'UPDATE leads SET status="suspect" WHERE id=? AND status="reported"',
            (lead_id,)
        )
        conn.commit()
    finally:
        conn.close()


def actualizar_outreach(lead_id, nuevo_status, notas=''):
    """Actualiza el último intento de contacto y avanza el status del lead si corresponde."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('''
            UPDATE outreach SET status=?, notes=?
            WHERE lead_id=? AND attempt_number=(
                SELECT MAX(attempt_number) FROM outreach WHERE lead_id=?
            )
        ''', (nuevo_status, notas, lead_id, lead_id))

        if nuevo_status == 'replied':
            conn.execute('UPDATE leads SET status="prospect" WHERE id=?', (lead_id,))
        elif nuevo_status == 'meeting_scheduled':
            conn.execute('UPDATE leads SET status="lead" WHERE id=?', (lead_id,))
        conn.commit()
    finally:
        conn.close()


def cerrar_lead(lead_id, resultado):
    """resultado: won | lost"""
    status = 'closed_won' if resultado == 'won' else 'closed_lost'
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('UPDATE leads SET status=? WHERE id=?', (status, lead_id))
        conn.commit()
    finally:
        conn.close()


def _menu():
    print('\nComandos:')
    print('  [l] listar leads     [f] seguimientos pendientes')
    print('  [v] ver informe      [h] historial contacto')
    print('  [p] ver contactos    [q] calificar (reported→suspect)')
    print('  [c] registrar contacto  [u] actualizar status')
    print('  [x] cerrar lead      [s] salir')


def run():
    print('\n══════════════════════════════════════════════')
    print('  PROSPECTOR · Outreach Tracker')
    print('══════════════════════════════════════════════')
    _menu()

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
            status_f = input('Filtrar por status (Enter=todos): ').strip() or None
            rows = listar_leads(min_fit, status_f)
            if not rows:
                print('Sin resultados.\n')
                continue
            print(f'\n{"ID":>4}  {"Empresa":<26}  {"Fit":>5}  {"Status":<12}  {"#":>3}  Próximo contacto')
            print('─' * 75)
            for lid, empresa, ccaa, sector, status, fit, intentos, ultimo, proximo in rows:
                prox = proximo[:10] if proximo else '—'
                print(f'{lid:>4}  {(empresa or "")[:24]:<26}  {fit:>5.2f}  {(status or ""):<12}  {intentos:>3}  {prox}')
            print()
            _menu()

        elif cmd in ('f', 'seguimientos'):
            rows = listar_seguimientos()
            if not rows:
                print('Sin seguimientos pendientes para hoy.\n')
                continue
            print(f'\n{"ID":>4}  {"Empresa":<26}  {"Fit":>5}  {"Status":<10}  {"Canal":<10}  Fecha límite')
            print('─' * 72)
            for lid, empresa, ccaa, status, fit, next_at, canal, attempt in rows:
                print(f'{lid:>4}  {(empresa or "")[:24]:<26}  {fit:>5.2f}  {(status or ""):<10}  {(canal or ""):<10}  {next_at[:10] if next_at else "—"}')
            print()
            _menu()

        elif cmd in ('v', 'ver'):
            lid = input('ID del lead: ').strip()
            if lid.isdigit():
                ver_informe(int(lid))
            _menu()

        elif cmd in ('h', 'historial'):
            lid = input('ID del lead: ').strip()
            if lid.isdigit():
                ver_historial(int(lid))
            _menu()

        elif cmd in ('p', 'contactos'):
            lid = input('ID del lead: ').strip()
            if lid.isdigit():
                ver_contactos(int(lid))
            _menu()

        elif cmd in ('q', 'calificar'):
            lid = input('ID del lead (reported → suspect): ').strip()
            if lid.isdigit():
                calificar_lead(int(lid))
                print(f'✓ Lead {lid} calificado como suspect')
            _menu()

        elif cmd in ('c', 'contactar'):
            lid = input('ID del lead: ').strip()
            canal = input('Canal (email/linkedin/phone): ').strip()
            notas = input('Notas: ').strip()
            next_at = input('Próximo seguimiento (YYYY-MM-DD, Enter=ninguno): ').strip() or None
            if lid.isdigit():
                registrar_contacto(int(lid), canal, notas, next_at)
                print(f'✓ Intento registrado para lead {lid}')
            _menu()

        elif cmd in ('u', 'update'):
            lid = input('ID del lead: ').strip()
            print('Status: sent / replied / no_reply / meeting_scheduled / discarded')
            nuevo_status = input('Nuevo status: ').strip()
            notas = input('Notas: ').strip()
            if lid.isdigit():
                actualizar_outreach(int(lid), nuevo_status, notas)
                print(f'✓ Actualizado')
            _menu()

        elif cmd in ('x', 'cerrar'):
            lid = input('ID del lead: ').strip()
            resultado = input('Resultado (won/lost): ').strip()
            if lid.isdigit() and resultado in ('won', 'lost'):
                cerrar_lead(int(lid), resultado)
                print(f'✓ Lead {lid} cerrado como {resultado}')
            _menu()

        else:
            print('Comando no reconocido.')
            _menu()
