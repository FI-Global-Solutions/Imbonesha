-- Initial database setup for Imbonesha development.
-- The main `imbonesha` database is created automatically by the postgres image.
-- We add a second database for the mock permit service so it has clean isolation
-- from the main app — this mirrors how the real KUBAKA system would be a separate
-- database we don't control.

CREATE DATABASE permit_mock OWNER imbonesha;

\c imbonesha
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

\c permit_mock
CREATE EXTENSION IF NOT EXISTS postgis;
