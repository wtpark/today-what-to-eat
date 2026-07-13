PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS seed_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ingredient_master (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    category TEXT NOT NULL,
    default_storage TEXT NOT NULL,
    perishability_level INTEGER NOT NULL CHECK (perishability_level BETWEEN 1 AND 5),
    opened_window_days INTEGER NOT NULL CHECK (opened_window_days >= 1),
    freshness_window_days INTEGER NOT NULL DEFAULT 14 CHECK (freshness_window_days >= 1),
    condition_profile TEXT NOT NULL,
    common_units_json TEXT NOT NULL DEFAULT '[]',
    source_ids_json TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ingredient_id TEXT NOT NULL REFERENCES ingredient_master(id),
    detail_name TEXT NOT NULL DEFAULT '',
    quantity REAL NOT NULL CHECK (quantity >= 0),
    unit TEXT NOT NULL,
    storage TEXT NOT NULL CHECK (storage IN ('냉장','냉동','실온')),
    purchase_date TEXT NOT NULL,
    expiry_date TEXT,
    opened INTEGER NOT NULL DEFAULT 0 CHECK (opened IN (0,1)),
    opened_date TEXT,
    priority_override INTEGER NOT NULL DEFAULT 0 CHECK (priority_override IN (0,1)),
    condition_status TEXT NOT NULL DEFAULT 'normal'
        CHECK (condition_status IN ('normal','needs_review','excluded')),
    condition_notes_json TEXT NOT NULL DEFAULT '[]',
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_inventory_ingredient ON inventory(ingredient_id);
CREATE INDEX IF NOT EXISTS idx_inventory_purchase_date ON inventory(purchase_date);
CREATE INDEX IF NOT EXISTS idx_inventory_expiry_date ON inventory(expiry_date);

CREATE TABLE IF NOT EXISTS seasonings (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    owned INTEGER NOT NULL DEFAULT 0 CHECK (owned IN (0,1)),
    default_owned INTEGER NOT NULL DEFAULT 0 CHECK (default_owned IN (0,1)),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recipes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    cuisine TEXT NOT NULL,
    meal_type TEXT NOT NULL,
    cooking_method TEXT NOT NULL,
    cook_time INTEGER NOT NULL CHECK (cook_time > 0),
    tools_json TEXT NOT NULL DEFAULT '[]',
    min_core_count INTEGER NOT NULL DEFAULT 0 CHECK (min_core_count >= 0),
    image_path TEXT,
    source TEXT NOT NULL DEFAULT '',
    source_recipe_id TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recipe_ingredients (
    recipe_id TEXT NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    ingredient_id TEXT NOT NULL REFERENCES ingredient_master(id),
    role TEXT NOT NULL CHECK (role IN ('must','core','supporting')),
    weight REAL NOT NULL DEFAULT 1 CHECK (weight > 0),
    PRIMARY KEY (recipe_id, ingredient_id, role)
);

CREATE INDEX IF NOT EXISTS idx_recipe_ingredients_ingredient
    ON recipe_ingredients(ingredient_id);

CREATE TABLE IF NOT EXISTS recipe_seasonings (
    recipe_id TEXT NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    seasoning_id TEXT NOT NULL REFERENCES seasonings(id),
    required INTEGER NOT NULL DEFAULT 1 CHECK (required IN (0,1)),
    PRIMARY KEY (recipe_id, seasoning_id)
);

CREATE TABLE IF NOT EXISTS recommendation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    requested_at TEXT NOT NULL,
    recipe_id TEXT REFERENCES recipes(id),
    score REAL NOT NULL,
    mode TEXT NOT NULL,
    result_group TEXT NOT NULL CHECK (result_group IN ('direct','one_more')),
    selected INTEGER NOT NULL DEFAULT 0 CHECK (selected IN (0,1)),
    request_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_recommendation_history_time
    ON recommendation_history(requested_at DESC);

CREATE TABLE IF NOT EXISTS meal_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id TEXT NOT NULL REFERENCES recipes(id),
    eaten_at TEXT NOT NULL,
    meal_slot TEXT NOT NULL,
    cuisine TEXT NOT NULL,
    meal_type TEXT NOT NULL,
    cooking_method TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_meal_history_time ON meal_history(eaten_at DESC);

CREATE TABLE IF NOT EXISTS inventory_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inventory_id INTEGER NOT NULL,
    ingredient_id TEXT NOT NULL,
    recipe_id TEXT NOT NULL REFERENCES recipes(id),
    before_quantity REAL NOT NULL,
    remaining_quantity REAL NOT NULL,
    used_quantity REAL NOT NULL,
    unit TEXT NOT NULL,
    used_at TEXT NOT NULL
);
