PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS leads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa     TEXT NOT NULL,
    ccaa        TEXT,
    sector      TEXT,
    web         TEXT UNIQUE,
    fuente      TEXT,
    status      TEXT DEFAULT 'pending',
    discovered_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contactos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id             INTEGER NOT NULL REFERENCES leads(id),
    nombre              TEXT,
    email               TEXT,
    cargo               TEXT,
    linkedin_profile_url TEXT
);

CREATE TABLE IF NOT EXISTS rrss (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id             INTEGER NOT NULL REFERENCES leads(id) UNIQUE,
    linkedin_url        TEXT,
    twitter_x           TEXT,
    instagram           TEXT,
    facebook            TEXT,
    youtube_url         TEXT,
    youtube_channel_id  TEXT
);

CREATE TABLE IF NOT EXISTS web_audit (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id                 INTEGER NOT NULL REFERENCES leads(id) UNIQUE,
    tech_stack              TEXT,
    has_cms                 INTEGER DEFAULT 0,
    has_api                 INTEGER DEFAULT 0,
    has_crm                 INTEGER DEFAULT 0,
    has_static_prices       INTEGER DEFAULT 0,
    has_pdf_catalog         INTEGER DEFAULT 0,
    manual_process_signals  TEXT,
    raw_text_path           TEXT,
    audited_at              DATETIME
);

CREATE TABLE IF NOT EXISTS youtube_videos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id         INTEGER NOT NULL REFERENCES leads(id),
    video_id        TEXT UNIQUE,
    title           TEXT,
    published_at    TEXT,
    transcript_path TEXT,
    downloaded_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reports (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id      INTEGER NOT NULL REFERENCES leads(id) UNIQUE,
    report_path  TEXT,
    gap_summary  TEXT,
    fit_score    REAL,
    generated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS outreach (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id    INTEGER NOT NULL REFERENCES leads(id),
    channel    TEXT,
    status     TEXT DEFAULT 'pending',
    sent_at    DATETIME,
    notes      TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS run_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    phase       TEXT NOT NULL,
    status      TEXT NOT NULL,
    message     TEXT,
    started_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    finished_at DATETIME
);
