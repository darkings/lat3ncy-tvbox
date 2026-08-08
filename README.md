# Ponyo Source Manager


## Production drpy2 adapter

The bundled `drpy2/index.js` is a fail-closed bridge, not a mock engine. Set
`DRPY2_ADAPTER` to a real Node.js adapter before deep probing. The adapter
must export a function or `execute(request)` and return the real result for
`search`, `detail`, `episode`, and `play` actions.

Example:

```bash
export DRPY2_ADAPTER=/opt/drpy2-adapter/index.js
node drpy2/index.js
```

If the adapter is missing, the bridge exits non-zero and no source can receive
a false playback pass. Placeholder URLs such as `example.com/mock.m3u8` are
also rejected by the Python runner.

### Isolated drpy2 script runtime

Legacy drpy2 scripts run in a separate container and never replace the drpyS
service on port 5757. Build only from the reviewed commit and a rule bundle
containing `rule-map.json` plus matching `rules/*.js` files:

```bash
DRPY2_BUNDLE_DIR=/opt/ponyo-drpy2-bundle \
  ./scripts/provision-drpy2-runtime.sh
```

Use `drpy2/hybrid-http-adapter.js` only after the isolated runtime is listening
on loopback. The drpy2 side requires an exact reviewed registry match and fails
closed for unknown rules:

```bash
export DRPY2_ADAPTER=/app/drpy2/hybrid-http-adapter.js
export DRPY2_DR2_BASE_URL=http://127.0.0.1:5758
export DRPY2_DR2_PWD='replace-with-runtime-password'
export DRPY2_RULE_MAP_FILE=/app/data/drpy2-runtime/rule-map.json
```

Do not enable the hybrid adapter until the bundle passes search, detail,
episode, real HLS manifest, segment, and media-duration checks.

Build the reviewed rule bundle on the no-proxy server. GitHub Raw rules use
the same reviewed jsDelivr fallback as the published subscription, while the
registry key remains the original rule URL:

```bash
python -m ponyo_source_manager.discovery.build_drpy2_bundle \
  --audit reports/source-type-audit.json \
  --asset-health reports/resolved-asset-health.json \
  --output data/drpy2-runtime \
  --report reports/drpy2-bundle-report.json
```

### Multi-entry discovery

Profile-driven repository search expands beyond the fixed watch list while
feeding every discovered TVBox config through the same candidate isolation,
normalization, provenance, and deduplication pipeline:

```bash
python -m ponyo_source_manager.discovery.profile_search_collector \
  --db data/sources.db \
  --profiles config/discovery_profiles.json \
  --report reports/profile-discovery-report.json
```

Profiles only influence repository discovery and attribution. A repository or
filename match never counts as a validation pass. Search, detail, episode,
playback, HLS segment, media duration, and multi-timeslot gates remain mandatory.
The global query cursor rotates profiles fairly; each query also keeps an
independent page cursor. Per-run query and repository budgets prevent GitHub
search limits or one large repository from starving the scheduler.

The scheduler runs profile search, fixed-repository collection, and MacCMS
probing as isolated discovery stages before deduplication:

```bash
python -m ponyo_source_manager.discovery.github_collector \
  --db data/sources.db \
  --watch config/watch-repos.json \
  --report reports/github-discovery-report.json

python -m ponyo_source_manager.discovery.maccms_collector \
  --db data/sources.db \
  --limit 30 \
  --report reports/maccms-discovery-report.json

python -m ponyo_source_manager.probes.maccms_media \
  --db data/sources.db \
  --limit 10 \
  --report reports/maccms-media-report.json
```

GitHub collection advances a repository cursor only after the whole revision is
processed. It records the repository, branch, commit, original URL, effective
Raw/jsDelivr route, and SHA-256. MacCMS quick probing requires all three test
keywords to match a title and expose detail/play candidates. Neither stage
changes `list_state`; MacCMS results explicitly remain `media_verified=false`
until the existing HLS segment or ffprobe gate succeeds.
MacCMS endpoints rotate by oldest probe time, with a default hard budget of 30
endpoints per scheduler run.
GitHub repository files are processed in resumable batches of 20; an in-progress
immutable commit is completed before a newer branch head is started.
Each file is attempted through pinned Raw and jsDelivr routes. A two-route
failure is retained in the entry report but advances the batch offset so a
single unreachable file cannot starve the rest of the repository.

Runtime classification is read-only. After deduplication, the MacCMS media
bridge fairly rotates fingerprints and converts quick search/detail/play-URL
evidence into deep media-byte/segment checks plus ffprobe duration/quality
evidence. It writes scorer-compatible search/detail/episode/playback/ffprobe
rows but never changes `list_state`. A reachable platform webpage is not a
media pass: success requires readable media, ffprobe success, and the
content-type-specific duration gate.
