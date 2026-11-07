-- Structured, user-declared personal colour preferences for the Style Desk.
-- Objective complexion/undertone analysis is deliberately not stored as a preference.
CREATE TABLE IF NOT EXISTS identity_usi_color_profiles (
    subject_id VARCHAR(128) PRIMARY KEY,
    profile_version INTEGER NOT NULL DEFAULT 1 CHECK (profile_version >= 1),
    liked_colors JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(liked_colors) = 'array'),
    disliked_colors JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(disliked_colors) = 'array'),
    best_version_colors JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(best_version_colors) = 'array'),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
