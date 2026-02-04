-- DANGER: This script will delete existing data. Use only for manual refactor.

-- 1. Drop old tables (if they exist)
DROP TABLE IF EXISTS history_trail CASCADE;
DROP TABLE IF EXISTS submissions CASCADE; -- Old name
DROP TABLE IF EXISTS agency_plans CASCADE; -- New name
DROP TABLE IF EXISTS briefs CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS agencies CASCADE;
DROP TABLE IF EXISTS clients CASCADE;

-- 2. Create Clients Table
CREATE TABLE clients (
    id SERIAL PRIMARY KEY, -- Auto-Inc Integer
    name VARCHAR UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
);

-- 3. Create Agencies Table
CREATE TABLE agencies (
    id SERIAL PRIMARY KEY, -- Auto-Inc Integer
    name VARCHAR UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    created_by INTEGER,
    updated_by INTEGER
);

-- 4. Create Users Table
CREATE TABLE users (
    id SERIAL PRIMARY KEY, -- Auto-Inc Integer
    email VARCHAR UNIQUE,
    password VARCHAR, -- For Real Auth
    name VARCHAR,
    role VARCHAR, -- 'DS_GROUP' or 'AGENCY'
    client_id INTEGER REFERENCES clients(id),
    agency_id INTEGER REFERENCES agencies(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
);

-- 5. Create Briefs Table
CREATE TABLE briefs (
    id SERIAL PRIMARY KEY,
    client_id INTEGER REFERENCES clients(id),
    brand_name VARCHAR,
    division VARCHAR,
    creative_name VARCHAR,
    objective TEXT,
    brief_type VARCHAR,
    total_budget VARCHAR,
    start_date DATE,
    end_date DATE,
    status VARCHAR DEFAULT 'ACTIVE', -- ACTIVE, COMPLETED
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    created_by INTEGER REFERENCES users(id), -- Strict FK
    updated_by INTEGER REFERENCES users(id), -- Strict FK
    
    -- Production Fields
    demographics_age VARCHAR,
    demographics_gender VARCHAR,
    demographics_nccs VARCHAR,
    demographics_etc VARCHAR,
    psychographics TEXT,
    key_markets TEXT,
    p1_markets TEXT,
    p2_markets TEXT,
    edit_durations VARCHAR,
    acd VARCHAR,
    dispersion VARCHAR,
    advertisement_link VARCHAR,
    creative_languages VARCHAR,
    scheduling_preference TEXT,
    miscellaneous TEXT,
    remarks TEXT
    -- Removed target_agency_ids (JSON) as we use agency_plans as Through Table
);

-- 6. Create Agency Plans Table (The Slot)
CREATE TABLE agency_plans (
    id SERIAL PRIMARY KEY,
    brief_id INTEGER REFERENCES briefs(id),
    agency_id INTEGER REFERENCES agencies(id),
    status VARCHAR DEFAULT 'DRAFT', -- DRAFT, PENDING_REVIEW, ACCEPTED, REJECTED
    version_number INTEGER DEFAULT 1,
    plan_file_name VARCHAR,
    plan_file_url VARCHAR,
    submitted_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC'),
    created_by INTEGER REFERENCES users(id), -- Strict FK
    updated_by INTEGER REFERENCES users(id) -- Strict FK
);

-- 7. Create History Trail Table
CREATE TABLE history_trail (
    id SERIAL PRIMARY KEY,
    agency_plan_id INTEGER REFERENCES agency_plans(id),
    action VARCHAR,
    user_id INTEGER REFERENCES users(id), -- Valid FK
    details TEXT,
    comment TEXT, -- New Comment Field
    created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
);

-- 8. Final Constraints (Resolving Circular Dependencies)
ALTER TABLE agencies ADD CONSTRAINT fk_agencies_created_by FOREIGN KEY (created_by) REFERENCES users(id);
ALTER TABLE agencies ADD CONSTRAINT fk_agencies_updated_by FOREIGN KEY (updated_by) REFERENCES users(id);

-- Indexes for performance
CREATE INDEX idx_briefs_brand ON briefs(brand_name);
CREATE INDEX idx_briefs_client ON briefs(client_id);
CREATE INDEX idx_agency_plans_brief ON agency_plans(brief_id);
CREATE INDEX idx_agency_plans_agency ON agency_plans(agency_id);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_client ON users(client_id);
CREATE INDEX idx_users_agency ON users(agency_id);
CREATE INDEX idx_history_plan ON history_trail(agency_plan_id);
