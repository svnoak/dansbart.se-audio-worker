# Beat and Bar Correction Strategy

Three complementary strategies for improving beat/bar accuracy across the platform.

## Problem

Madmom's beat detection often misidentifies meter in Swedish folk music:
- 4/4 detected as 2/4 or vice versa
- 3/4 detected as 6/8
- Polska downbeats missed (rubato/asymmetric phrasing)

Once bars are written to `Track.bars`, there is no correction mechanism. The raw beat data (timestamps, positions, activation functions) is already stored in `AnalysisSource.raw_data` but never used for post-hoc correction.

---

## Strategy 1: Dance Style Configuration with beats_per_bar

### Concept

Create a `dance_style_config` table as the single source of truth for style properties. Each style (and optionally sub-style) defines its expected `beats_per_bar`. After classification, the worker uses this to re-derive bars from stored beat timestamps -- no audio re-processing needed.

### Schema

```sql
CREATE TABLE dance_style_config (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    main_style VARCHAR NOT NULL,
    sub_style VARCHAR,              -- NULL = default for this main_style
    beats_per_bar INTEGER NOT NULL, -- 2, 3, or 4
    -- future: tempo ranges, rhythmic patterns, etc.
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    UNIQUE (main_style, sub_style)
);
```

Initial data:
| main_style    | sub_style | beats_per_bar |
|---------------|-----------|---------------|
| Polska        | NULL      | 3             |
| Hambo         | NULL      | 3             |
| Slangpolska   | NULL      | 3             |
| Vals          | NULL      | 3             |
| Mazurka       | NULL      | 3             |
| Polka         | NULL      | 2             |
| Polka         | Galopp    | 2             |
| Schottis      | NULL      | 4             |
| Snoa          | NULL      | 4             |
| Engelska      | NULL      | 4             |
| Ganglatll     | NULL      | 4             |

### Correction flow

```
1. Worker classifies track -> style = "Polska"
2. Lookup dance_style_config -> beats_per_bar = 3
3. Load beat_times + beat_positions from AnalysisSource.raw_data
4. Regroup beats into bars of 3 (pick every 3rd beat as downbeat)
5. Update Track.bars with corrected bar positions
```

### User feedback correction

When a user changes the dance style of a track (e.g. corrects "Polka" to "Polska"):
1. The style change triggers a bar re-derivation
2. Look up the new style's `beats_per_bar` from `dance_style_config`
3. Regroup the stored beat timestamps using the new meter
4. Update `Track.bars` without re-analyzing audio
5. Mark the style as `is_user_confirmed = true` to protect from future reclassification

This could be triggered from the Java API as a lightweight Celery task (no audio needed, just artifact regrouping) or done directly in the Java API if the beat data is accessible.

### Bulk correction

For existing ~3500 tracks:
1. Run `reclassify_library()` (already exists)
2. After each classification, apply bar correction using the style's `beats_per_bar`
3. All data needed is already in `AnalysisSource.raw_data`

### Changes required

- **Database**: Flyway migration for `dance_style_config` table + seed data
- **Java API**: Admin CRUD endpoints for style config, expose via admin UI
- **Java API**: On style change (user feedback), dispatch bar correction
- **Workers**: Cache `dance_style_config` (like keywords cache), apply bar correction after classification
- **neckenml-core**: Utility function to regroup beats into bars given a target `beats_per_bar`

### Future potential

This table can also absorb the hardcoded `TEMPO_RANGES` from `music_theory.py`, making tempo thresholds admin-configurable too.

---

## Strategy 2: Folkwiki ABC Notation Scraping

### Concept

Scrape ABC notation music sheets from folkwiki.se to build a ground truth dataset of rhythm characteristics per dance style. ABC notation contains explicit time signatures (`M:3/4`), note durations, and rhythmic patterns.

### Data source

- URL: http://www.folkwiki.se/L%c3%a5ttyper/L%c3%a5ttyper
- Contains categorized tunes with ABC notation for many Swedish folk dance types
- Each tune page has structured metadata (dance type, region, key) plus the ABC score

### What we can extract

- **Time signatures per style**: Confirm/refine the beats_per_bar mapping. Is Galopp always 2/4? What about Springlek? Are there polska sub-types in 4/4?
- **Rhythmic patterns**: Typical note duration sequences per style. Polska might show dotted-quarter + eighth patterns, vals might show even quarter notes.
- **Beat emphasis**: Which beats are stressed in each dance style (from note accents, chord placement).
- **Tempo markings**: Where present, correlate with our tempo ranges.

### Use cases

1. **Validate Strategy 1**: Ground-truth the dance_style_config beats_per_bar values with actual sheet music data rather than assumptions.
2. **Training data for ML model**: Feed rhythmic patterns as features to improve the style classifier.
3. **Sub-style differentiation**: Distinguish between e.g. different polska types based on rhythmic fingerprints.
4. **Meter confidence**: If 95% of scraped polskas are 3/4, we can weight bar correction more aggressively for that style.

### Implementation sketch

1. Scraper script to crawl folkwiki tune pages
2. ABC parser to extract: time signature, note sequences, key, dance type label
3. Aggregate statistics: per-style meter distribution, common rhythmic patterns
4. Store as a dataset (CSV/JSON) for analysis and potential model training
5. Feed findings back into `dance_style_config` and classifier tuning

### Considerations

- Respect folkwiki's robots.txt and rate-limit scraping
- ABC notation represents composed/notated music -- actual performance may differ (especially for polska with its rubato)
- Some tunes may be multi-section with different meters

---

## Strategy 3: Beat-Level Data on Track

### Concept

Currently `Track` only stores `bars` (downbeat positions). Adding `beat_times` and `beat_positions` would make the full beat grid directly accessible without digging into `AnalysisSource.raw_data`.

### Do we actually need this?

Maybe not as a separate Track field. Consider:

- **beats_per_bar on the style** (Strategy 1) means you can always derive the beat grid from `bars` + the style's meter. If a polska has bars at [0.0, 1.5, 3.0] and beats_per_bar = 3, the beats are implied.
- **Raw beat data** is already in `AnalysisSource.raw_data.rhythm_extractor.beat_info` as `[[time, beat_num], ...]`. This is the full resolution data.
- The main use case for beat-level data on Track would be if the frontend needs direct access for visualization (e.g. a beat grid editor) without joining to AnalysisSource.

### When it would be needed

- **Frontend beat grid visualization**: If building a UI where users can see and adjust individual beats, having `beat_times` directly on Track avoids a heavy join.
- **Beat-level playback features**: Click-track, metronome overlay, beat-synced animations.
- **Cross-track beat alignment**: Comparing beat patterns across tracks for similarity.

### Alternative: derive on demand

Instead of storing on Track, expose beat data through an API endpoint that reads from `AnalysisSource.raw_data` and returns structured beat info. This keeps the Track model lean and avoids data duplication.

### If we do add it

```sql
ALTER TABLE tracks ADD COLUMN beat_times JSONB;      -- [0.0, 0.5, 1.0, 1.5, ...]
ALTER TABLE tracks ADD COLUMN beat_positions JSONB;   -- [1, 2, 3, 1, 2, 3, ...]
```

But this duplicates what's in AnalysisSource and creates a sync problem. Recommendation: defer this until there's a concrete frontend need, and use the AnalysisSource data via an API endpoint in the meantime.

---

## Recommended Priority

1. **Strategy 1** (dance_style_config + bar correction) -- highest impact, fixes existing tracks immediately
2. **Strategy 2** (folkwiki scraping) -- validates assumptions, builds training data
3. **Strategy 3** (beat-level on Track) -- defer until frontend needs arise; derive from AnalysisSource on demand
