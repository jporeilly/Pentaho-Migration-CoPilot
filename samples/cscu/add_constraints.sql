-- CSCU demo database: add PK/FK constraints so the schema browser and the
-- schema-grounded chat can show real join relationships.
-- Run as the table OWNER (pdc_user lacks ALTER rights):
--   psql -h 192.168.1.200 -p 5433 -U <owner> -d cscu_core -f add_constraints.sql

ALTER TABLE cscu_core.members             ADD PRIMARY KEY (mbr_id);
ALTER TABLE cscu_core.accounts            ADD PRIMARY KEY (acct_id);
ALTER TABLE cscu_core.branches            ADD PRIMARY KEY (br_id);
ALTER TABLE cscu_core.transactions        ADD PRIMARY KEY (txn_id);
ALTER TABLE cscu_core.loans               ADD PRIMARY KEY (ln_id);
ALTER TABLE cscu_core.cards               ADD PRIMARY KEY (card_id);
ALTER TABLE cscu_core.suspicious_activity ADD PRIMARY KEY (sar_id);
ALTER TABLE cscu_core.employees           ADD PRIMARY KEY (emp_id);
ALTER TABLE cscu_core.kyc_reviews         ADD PRIMARY KEY (kyc_id);

ALTER TABLE cscu_core.members      ADD FOREIGN KEY (br_id)   REFERENCES cscu_core.branches (br_id);
ALTER TABLE cscu_core.accounts     ADD FOREIGN KEY (mbr_id)  REFERENCES cscu_core.members (mbr_id);
ALTER TABLE cscu_core.accounts     ADD FOREIGN KEY (br_id)   REFERENCES cscu_core.branches (br_id);
ALTER TABLE cscu_core.transactions ADD FOREIGN KEY (acct_id) REFERENCES cscu_core.accounts (acct_id);
ALTER TABLE cscu_core.loans        ADD FOREIGN KEY (mbr_id)  REFERENCES cscu_core.members (mbr_id);
ALTER TABLE cscu_core.cards        ADD FOREIGN KEY (acct_id) REFERENCES cscu_core.accounts (acct_id);
ALTER TABLE cscu_core.suspicious_activity ADD FOREIGN KEY (mbr_id) REFERENCES cscu_core.members (mbr_id);
ALTER TABLE cscu_core.kyc_reviews  ADD FOREIGN KEY (mbr_id)  REFERENCES cscu_core.members (mbr_id);
ALTER TABLE cscu_core.employees    ADD FOREIGN KEY (br_id)   REFERENCES cscu_core.branches (br_id);
