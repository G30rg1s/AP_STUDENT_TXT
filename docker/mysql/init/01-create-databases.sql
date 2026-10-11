-- ==========================================
-- CODING FACTORY AUTOMATION
-- DATABASE CREATION
-- ==========================================


-- ==========================================
-- PRODUCTION
-- ==========================================

CREATE DATABASE IF NOT EXISTS production
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;


-- ==========================================
-- FRONTEND TESTING
-- ==========================================

CREATE DATABASE IF NOT EXISTS frontendtesting
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;


-- ==========================================
-- API TESTING
-- ==========================================

CREATE DATABASE IF NOT EXISTS apitesting
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;


-- ==========================================
-- APPLICATION USER PERMISSIONS
-- ==========================================

GRANT ALL PRIVILEGES
    ON production.*
    TO 'cf_user'@'%';


GRANT ALL PRIVILEGES
    ON frontendtesting.*
    TO 'cf_user'@'%';


GRANT ALL PRIVILEGES
    ON apitesting.*
    TO 'cf_user'@'%';


FLUSH PRIVILEGES;