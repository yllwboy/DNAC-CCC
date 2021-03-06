-- Configuration Compliance Check
--
-- Copyright (c) 2021 Cisco and/or its affiliates.
--
-- This software is licensed to you under the terms of the Cisco Sample
-- Code License, Version 1.1 (the "License"). You may obtain a copy of the
-- License at
--
--                https://developer.cisco.com/docs/licenses
--
-- All use of the material herein must be in accordance with the terms of
-- the License. All rights not expressly granted by the License are
-- reserved. Unless required by applicable law or agreed to separately in
-- writing, software distributed under the License is distributed on an "AS
-- IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
-- or implied.
--
-- AUTHOR(s): Héctor Cavalcanti Saavedra <hcavalca@cisco.com>
-- CONTRIBUTOR(s): Sarah Louise Justin <sajustin@cisco.com>

-- Initialize the database.
-- Drop any existing data and create empty tables.

DROP TABLE IF EXISTS user_dnac;
DROP TABLE IF EXISTS user;
DROP TABLE IF EXISTS job;
DROP TABLE IF EXISTS backup;
DROP TABLE IF EXISTS device;
DROP TABLE IF EXISTS dnac;

CREATE TABLE user (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  password TEXT NOT NULL
);

CREATE TABLE dnac (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  addr TEXT NOT NULL UNIQUE
);

CREATE TABLE user_dnac (
  user_id INTEGER NOT NULL,
  dnac_id INTEGER NOT NULL,
  dnac_user TEXT NOT NULL,
  dnac_pass TEXT NOT NULL,
  restconf_user TEXT,
  restconf_pass TEXT,
  PRIMARY KEY (user_id, dnac_id),
  FOREIGN KEY (user_id) REFERENCES user (id),
  FOREIGN KEY (dnac_id) REFERENCES dnac (id)
);

CREATE TABLE job (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  author_id INTEGER NOT NULL,
  dnac_id INTEGER NOT NULL,
  created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  title TEXT NOT NULL,
  frequency UNSIGNED INTEGER NOT NULL,
  activated BIT NOT NULL DEFAULT 1,
  FOREIGN KEY (author_id) REFERENCES user (id),
  FOREIGN KEY (dnac_id) REFERENCES dnac (id)
);

CREATE TABLE device (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  dnac_id INTEGER NOT NULL,
  uuid CHAR(36) NOT NULL,
  hostname TEXT NOT NULL,
  addr TEXT NOT NULL,
  connected BIT NOT NULL DEFAULT 1,
  FOREIGN KEY (dnac_id) REFERENCES dnac (id)
);

CREATE TABLE backup (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  device_id INTEGER NOT NULL,
  created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  config_type TEXT NOT NULL,
  content LONGTEXT NOT NULL,
  FOREIGN KEY (device_id) REFERENCES device (id)
);