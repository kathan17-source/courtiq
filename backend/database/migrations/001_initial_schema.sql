-- CourtIQ migration 001: initial normalized tennis schema.

CREATE TABLE IF NOT EXISTS players (
    id BIGSERIAL PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    tour TEXT NOT NULL CHECK (tour IN ('atp', 'wta')),
    hand TEXT,
    birth_date DATE,
    country_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (canonical_name, tour)
);

CREATE TABLE IF NOT EXISTS player_aliases (
    id BIGSERIAL PRIMARY KEY,
    player_id BIGINT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    UNIQUE (alias, player_id)
);

CREATE TABLE IF NOT EXISTS tournaments (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    level TEXT,
    surface TEXT CHECK (surface IN ('Hard', 'Clay', 'Grass', 'Carpet', 'Unknown')),
    location TEXT,
    country_code TEXT
);

CREATE TABLE IF NOT EXISTS matches (
    id BIGSERIAL PRIMARY KEY,
    source_match_id TEXT UNIQUE,
    tour TEXT NOT NULL CHECK (tour IN ('atp', 'wta')),
    match_date DATE NOT NULL,
    tournament_id BIGINT REFERENCES tournaments(id),
    round TEXT,
    best_of SMALLINT NOT NULL CHECK (best_of IN (3, 5)),
    surface TEXT NOT NULL,
    winner_id BIGINT NOT NULL REFERENCES players(id),
    loser_id BIGINT NOT NULL REFERENCES players(id),
    winner_rank INTEGER,
    loser_rank INTEGER,
    winner_rank_points INTEGER,
    loser_rank_points INTEGER,
    score TEXT,
    minutes INTEGER,
    is_walkover BOOLEAN NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(match_date);
CREATE INDEX IF NOT EXISTS idx_matches_players ON matches(winner_id, loser_id);
CREATE INDEX IF NOT EXISTS idx_matches_surface ON matches(surface);

CREATE TABLE IF NOT EXISTS match_statistics (
    match_id BIGINT PRIMARY KEY REFERENCES matches(id) ON DELETE CASCADE,
    winner_aces INTEGER,
    loser_aces INTEGER,
    winner_double_faults INTEGER,
    loser_double_faults INTEGER,
    winner_first_serve_in INTEGER,
    loser_first_serve_in INTEGER,
    winner_first_serve_total INTEGER,
    loser_first_serve_total INTEGER,
    winner_first_serve_points_won INTEGER,
    loser_first_serve_points_won INTEGER,
    winner_first_serve_points_total INTEGER,
    loser_first_serve_points_total INTEGER,
    winner_second_serve_points_won INTEGER,
    loser_second_serve_points_won INTEGER,
    winner_second_serve_points_total INTEGER,
    loser_second_serve_points_total INTEGER,
    winner_break_points_saved INTEGER,
    loser_break_points_saved INTEGER,
    winner_break_points_faced INTEGER,
    loser_break_points_faced INTEGER
);

CREATE TABLE IF NOT EXISTS point_events (
    id BIGSERIAL PRIMARY KEY,
    match_id BIGINT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    point_number INTEGER NOT NULL,
    server_id BIGINT REFERENCES players(id),
    winner_id BIGINT REFERENCES players(id),
    set_number SMALLINT,
    game_number SMALLINT,
    score_before TEXT,
    rally_length INTEGER,
    serve_number SMALLINT CHECK (serve_number IN (1, 2)),
    serve_direction TEXT CHECK (serve_direction IN ('wide', 'body', 't', 'unknown')),
    point_ending TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (match_id, point_number)
);

CREATE INDEX IF NOT EXISTS idx_point_events_match ON point_events(match_id, point_number);
CREATE INDEX IF NOT EXISTS idx_point_events_server ON point_events(server_id);

CREATE TABLE IF NOT EXISTS elo_history (
    id BIGSERIAL PRIMARY KEY,
    player_id BIGINT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    match_id BIGINT REFERENCES matches(id) ON DELETE CASCADE,
    rating_date DATE NOT NULL,
    overall_elo NUMERIC(8, 2) NOT NULL,
    hard_elo NUMERIC(8, 2) NOT NULL,
    clay_elo NUMERIC(8, 2) NOT NULL,
    grass_elo NUMERIC(8, 2) NOT NULL,
    matches_played INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_elo_player_date ON elo_history(player_id, rating_date);

CREATE TABLE IF NOT EXISTS model_versions (
    id BIGSERIAL PRIMARY KEY,
    version TEXT NOT NULL UNIQUE,
    feature_version TEXT NOT NULL,
    trained_at TIMESTAMPTZ,
    train_start DATE,
    train_end DATE,
    metrics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    artifact_path TEXT
);

CREATE TABLE IF NOT EXISTS model_predictions (
    id BIGSERIAL PRIMARY KEY,
    model_version_id BIGINT REFERENCES model_versions(id),
    match_id BIGINT REFERENCES matches(id),
    player1_id BIGINT REFERENCES players(id),
    player2_id BIGINT REFERENCES players(id),
    player1_win_probability NUMERIC(6, 5) NOT NULL,
    predicted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    features_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    factors_json JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS model_backtests (
    id BIGSERIAL PRIMARY KEY,
    model_version_id BIGINT REFERENCES model_versions(id),
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    test_start DATE NOT NULL,
    test_end DATE NOT NULL,
    tour TEXT CHECK (tour IN ('atp', 'wta', 'combined')),
    surface TEXT,
    matches_tested INTEGER NOT NULL,
    accuracy NUMERIC(6, 5),
    roc_auc NUMERIC(6, 5),
    log_loss NUMERIC(8, 5),
    brier_score NUMERIC(8, 5),
    calibration_json JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS player_surface_snapshots (
    id BIGSERIAL PRIMARY KEY,
    player_id BIGINT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    tour TEXT NOT NULL CHECK (tour IN ('atp', 'wta')),
    hard_matches INTEGER NOT NULL DEFAULT 0,
    clay_matches INTEGER NOT NULL DEFAULT 0,
    grass_matches INTEGER NOT NULL DEFAULT 0,
    hold_rate NUMERIC(6, 5),
    break_rate NUMERIC(6, 5),
    first_serve_points_won NUMERIC(6, 5),
    second_serve_points_won NUMERIC(6, 5),
    recent_form_rating NUMERIC(8, 2),
    UNIQUE (player_id, snapshot_date)
);

CREATE TABLE IF NOT EXISTS uploaded_analysis_jobs (
    id UUID PRIMARY KEY,
    player_id BIGINT REFERENCES players(id),
    status TEXT NOT NULL CHECK (status IN ('queued', 'processing', 'completed', 'failed', 'expired')),
    media_sha256 TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    result_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_uploaded_jobs_status_created ON uploaded_analysis_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_uploaded_jobs_expires_at ON uploaded_analysis_jobs(expires_at);
