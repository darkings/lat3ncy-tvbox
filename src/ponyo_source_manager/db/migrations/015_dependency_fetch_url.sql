-- Record the exact mirror URL that supplied bytes for static validation.
ALTER TABLE dependency_asset_evidence ADD COLUMN fetched_url TEXT;
