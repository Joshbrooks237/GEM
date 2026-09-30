PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    seed INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    status TEXT NOT NULL,
    provider TEXT NOT NULL,
    runner TEXT NOT NULL,
    generations INTEGER NOT NULL,
    n_agents INTEGER NOT NULL,
    shock_generation INTEGER NOT NULL,
    heldout_every INTEGER NOT NULL,
    completed_generations INTEGER NOT NULL DEFAULT 0,
    config_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    run_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (run_id, key),
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS generation_marks (
    run_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    start_sha TEXT NOT NULL,
    finished INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, generation),
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS generation_stats (
    run_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    phase TEXT NOT NULL,
    success_count INTEGER NOT NULL,
    median_consumption REAL NOT NULL,
    PRIMARY KEY (run_id, generation, phase),
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    agent_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    token_usage INTEGER NOT NULL DEFAULT 0,
    tool_calls INTEGER NOT NULL DEFAULT 0,
    wall_time_s REAL NOT NULL DEFAULT 0,
    parent_sha TEXT,
    commit_sha TEXT,
    tests_passed INTEGER NOT NULL DEFAULT 0,
    tests_total INTEGER NOT NULL DEFAULT 0,
    correctness REAL NOT NULL DEFAULT 0,
    consumption REAL,
    resource_score REAL,
    reuse_score REAL NOT NULL DEFAULT 0,
    explainability_sampled INTEGER NOT NULL DEFAULT 0,
    explainability_score REAL,
    novelty_score REAL NOT NULL DEFAULT 0,
    fitness REAL NOT NULL DEFAULT 0,
    fitness_at_birth REAL,
    survived INTEGER NOT NULL DEFAULT 0,
    gamed INTEGER NOT NULL DEFAULT 0,
    quality_json TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS commits (
    run_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    agent_id TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    parent_sha TEXT,
    task_id TEXT,
    episode_id INTEGER,
    timestamp TEXT NOT NULL,
    token_usage INTEGER,
    wall_time_s REAL,
    fitness REAL,
    message TEXT,
    PRIMARY KEY (run_id, commit_sha),
    FOREIGN KEY (run_id) REFERENCES runs(run_id),
    FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    episode_id INTEGER,
    commit_sha TEXT NOT NULL,
    path TEXT NOT NULL,
    blob_sha TEXT,
    generation INTEGER NOT NULL,
    agent_id TEXT NOT NULL,
    task_id TEXT,
    archived INTEGER NOT NULL DEFAULT 0,
    pruned INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reuse_events (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    consumer_agent TEXT NOT NULL,
    consumer_episode INTEGER NOT NULL,
    consumer_task TEXT NOT NULL,
    producer_episode INTEGER NOT NULL,
    producer_commit TEXT NOT NULL,
    producer_path TEXT NOT NULL,
    evidence TEXT NOT NULL,
    kind TEXT NOT NULL,
    FOREIGN KEY (producer_episode) REFERENCES episodes(id) ON DELETE CASCADE,
    FOREIGN KEY (consumer_episode) REFERENCES episodes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS shocks (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    shock_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    shock_type TEXT NOT NULL,
    old_path TEXT,
    new_path TEXT,
    origin_commit TEXT,
    commit_sha TEXT,
    applied INTEGER NOT NULL DEFAULT 0,
    reason TEXT,
    detail_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS explainability (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    episode_id INTEGER NOT NULL,
    commit_sha TEXT NOT NULL,
    path TEXT NOT NULL,
    sampled INTEGER NOT NULL,
    sample_key TEXT NOT NULL,
    explainer TEXT NOT NULL,
    explanation TEXT,
    score REAL,
    FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS antigaming (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    episode_id INTEGER NOT NULL,
    commit_sha TEXT,
    trigger TEXT NOT NULL,
    reason TEXT NOT NULL,
    FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    episode_id INTEGER,
    tokens INTEGER NOT NULL,
    request_json TEXT NOT NULL,
    response_text TEXT NOT NULL,
    FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY,
    episode_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    cmd TEXT NOT NULL,
    exit_code INTEGER,
    stdout_excerpt TEXT,
    stderr_excerpt TEXT,
    FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_episodes_run_gen ON episodes(run_id, generation);
CREATE INDEX IF NOT EXISTS idx_reuse_producer ON reuse_events(producer_episode);
CREATE INDEX IF NOT EXISTS idx_artifacts_path ON artifacts(run_id, path);
