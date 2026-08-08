-- Bind approvals to the exact path and immutable Git object verified at review time.
ALTER TABLE dependency_asset_approval ADD COLUMN upstream_path TEXT;
ALTER TABLE dependency_asset_approval ADD COLUMN git_blob_sha TEXT;
ALTER TABLE dependency_asset_approval ADD COLUMN provenance_verified_at TEXT;

ALTER TABLE dependency_asset_approval_event ADD COLUMN upstream_path TEXT;
ALTER TABLE dependency_asset_approval_event ADD COLUMN git_blob_sha TEXT;
ALTER TABLE dependency_asset_approval_event ADD COLUMN provenance_verified_at TEXT;
