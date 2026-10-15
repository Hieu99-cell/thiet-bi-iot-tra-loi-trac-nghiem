-- Additive, safe to run again. Run after migration_v2.sql with a schema admin.
CREATE TABLE IF NOT EXISTS presentation_state (
    session_id INT NOT NULL,
    revealed_question_id INT NULL,
    PRIMARY KEY (session_id),
    CONSTRAINT fk_presentation_session FOREIGN KEY (session_id)
        REFERENCES quiz_sessions(id) ON DELETE CASCADE,
    CONSTRAINT fk_presentation_question FOREIGN KEY (revealed_question_id)
        REFERENCES questions(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
