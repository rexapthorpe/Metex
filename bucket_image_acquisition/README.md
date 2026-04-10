# Metex Bucket Image Acquisition System

A self-contained image acquisition pipeline that searches, downloads, organizes,
and catalogs candidate images for all standard Metex bullion buckets.

This system acts as the **intake layer**. The existing Metex `bucket_image_service`
and admin UI remain the **canonical serving and review system**. Use the export
script to push approved candidates into Metex.

---

## Directory Structure

```
bucket_image_acquisition/
├── README.md                    ← you are here
├── config/
│   ├── settings.py              ← all paths, thresholds, API keys
│   └── source_registry.py       ← adapter registry + sweep/metal/family maps
├── adapters/
│   ├── __init__.py              ← BaseAdapter + build_candidate()
│   ├── wikimedia.py             ← KnownFilesAdapter (curated) + WikimediaAdapter (search)
│   ├── us_mint.py               ← UsMintAdapter (public domain)
│   ├── rcm.py                   ← RcmAdapter (Maple Leaf, licensed)
│   ├── royal_mint.py            ← RoyalMintAdapter (Britannia, licensed)
│   ├── perth_mint.py            ← PerthMintAdapter (Kangaroo/Kookaburra, licensed)
│   ├── refiner.py               ← RefinerAdapter (bars, licensed)
│   ├── open_numismatics.py      ← Historic US silver (public domain)
│   └── pixabay.py               ← PixabayAdapter (free commercial, API key required)
├── matchers/
│   ├── spec_matcher.py          ← Score candidates against bucket specs (0.0–1.0)
│   └── deduper.py               ← SHA-256 + optional perceptual dedup
├── pipeline/
│   ├── orchestrator.py          ← Main sweep engine + CLI entry point
│   ├── downloader.py            ← HTTP download with retry + size guard
│   ├── processor.py             ← Validate, resize, save web/thumb copies
│   ├── manifest.py              ← Read/write per-bucket JSON manifests
│   ├── bucket_loader.py         ← Load bucket specs (DB → cache → seed)
│   └── exporter.py              ← Push manifests into Metex DB
├── reports/
│   └── coverage_report.py       ← Coverage report (by metal/family/source/confidence)
├── scripts/
│   ├── run_sweep.py             ← Full sweep, all buckets + sources
│   ├── run_by_metal.py          ← Sweep one metal
│   ├── run_by_family.py         ← Sweep one product family
│   ├── run_by_source.py         ← Sweep using one source adapter
│   ├── rebuild_manifests.py     ← Rebuild manifests from files on disk
│   ├── export_to_metex.py       ← Push candidates into Metex bucket_image_assets
│   └── sync_buckets.py          ← Cache live bucket defs from Metex DB
├── catalog/                     ← Downloaded + processed images (organized by family)
│   ├── gold/
│   │   ├── eagles/              ← American Eagle coins
│   │   ├── buffalos/            ← American Buffalo coins
│   │   ├── maples/              ← Maple Leaf coins
│   │   ├── britannias/          ← Britannia coins
│   │   ├── kangaroos/           ← Kangaroo/Nugget coins
│   │   ├── philharmonics/       ← Vienna Philharmonic coins
│   │   ├── krugerrands/         ← Krugerrand coins
│   │   ├── pandas/              ← Chinese Panda coins
│   │   ├── libertads/           ← Mexican Libertad coins
│   │   └── bars/                ← Gold bars (all sizes)
│   ├── silver/
│   │   ├── eagles/              ← Silver American Eagle
│   │   ├── maples/              ← Silver Maple Leaf
│   │   ├── britannias/          ← Silver Britannia
│   │   ├── kangaroos/           ← Silver Kangaroo
│   │   ├── kookaburras/         ← Silver Kookaburra
│   │   ├── philharmonics/       ← Silver Philharmonic
│   │   ├── krugerrands/         ← Silver Krugerrand
│   │   ├── libertads/           ← Silver Libertad
│   │   ├── pandas/              ← Silver Panda
│   │   ├── rounds/              ← Generic silver rounds
│   │   ├── bars/                ← Silver bars (all sizes)
│   │   ├── morgan_dollars/      ← Morgan Silver Dollar
│   │   ├── peace_dollars/       ← Peace Silver Dollar
│   │   ├── walking_liberty/     ← Walking Liberty Half Dollar
│   │   ├── franklin_half/       ← Franklin Half Dollar
│   │   ├── mercury_dimes/       ← Mercury Dime
│   │   ├── roosevelt_dimes/     ← Roosevelt Silver Dime
│   │   └── washington_quarters/ ← Washington Silver Quarter
│   ├── platinum/
│   │   ├── eagles/
│   │   ├── maples/
│   │   └── bars/
│   ├── palladium/
│   │   ├── eagles/
│   │   ├── maples/
│   │   └── bars/
│   └── copper/
│       ├── rounds/
│       └── bars/
└── data/
    ├── raw/                     ← Original downloaded image bytes
    ├── processed/               ← (reserved for future batch processing)
    ├── manifests/               ← Per-bucket JSON manifests (one per slug)
    └── logs/                    ← Run logs
```

---

## Quickstart

All commands run from `Metex/bucket_image_acquisition/`:

```bash
cd Metex/bucket_image_acquisition

# 1. (Optional) sync live bucket definitions from the Metex DB
DATABASE_URL=postgresql://... python scripts/sync_buckets.py

# 2. Dry-run to see what would be acquired
python scripts/run_sweep.py --dry-run

# 3. Run acquisition for all buckets
python scripts/run_sweep.py

# 4. Run only for gold buckets
python scripts/run_by_metal.py gold

# 5. Run only for eagle family
python scripts/run_by_family.py eagles

# 6. Run using only the US Mint source
python scripts/run_by_source.py us_mint --metal gold

# 7. View coverage report
python -m reports.coverage_report

# 8. Export candidates to Metex DB (requires DATABASE_URL)
DATABASE_URL=postgresql://... python scripts/export_to_metex.py --all

# 9. Dry-run export (prints plan, no DB writes)
DATABASE_URL=postgresql://... python scripts/export_to_metex.py --all --dry-run
```

---

## Sources

| Name                 | Key                 | Source Type    | Auto-Activate? | Coverage                     |
|----------------------|---------------------|----------------|----------------|------------------------------|
| Wikimedia (curated)  | `known_files`       | public_domain  | Yes (conf≥0.75) | ~30 curated high-quality files |
| US Mint              | `us_mint`           | public_domain  | Yes (conf≥0.75) | Eagle, Buffalo, Platinum, Palladium |
| Royal Canadian Mint  | `rcm`               | licensed       | No (review)    | Maple Leaf (all metals)      |
| Royal Mint           | `royal_mint`        | licensed       | No (review)    | Britannia (gold, silver)     |
| Perth Mint           | `perth_mint`        | licensed       | No (review)    | Kangaroo, Kookaburra, Koala  |
| Refiner              | `refiner`           | licensed       | No (review)    | Bars (all metals)            |
| Open Numismatics     | `open_numismatics`  | public_domain  | Yes (conf≥0.75) | Historic US silver coins     |
| Wikimedia (search)   | `wikimedia`         | mixed          | PD only        | All products (broad search)  |
| Pixabay              | `pixabay`           | approved_db    | No (review)    | General (API key required)   |

**Sweep order** (highest quality → broadest coverage):
`known_files → us_mint → rcm → royal_mint → perth_mint → refiner → open_numismatics → wikimedia → pixabay`

---

## Manifests

Each bucket has a manifest at `data/manifests/<slug>.json`:

```json
{
  "bucket_slug": "gold-american-eagle-1oz",
  "bucket_id": 1,
  "metal": "gold",
  "family": "gold/eagles",
  "last_updated": "2024-01-01T12:00:00Z",
  "candidates": [
    {
      "id": "uuid",
      "source": "known_files",
      "source_type": "public_domain",
      "source_page_url": "https://commons.wikimedia.org/wiki/File:...",
      "original_image_url": "https://upload.wikimedia.org/...",
      "raw_source_title": "American Gold Eagle coin",
      "license_type": "public_domain",
      "attribution_text": "United States Mint",
      "confidence_score": 0.85,
      "warnings": [],
      "status": "candidate",
      "acquired_at": "2024-01-01T12:00:00Z",
      "checksum": "sha256hex",
      "width": 1200, "height": 1200,
      "file_size": 245678,
      "local_web_path": "catalog/gold/eagles/gold-american-eagle-1oz_known_files_abc123.jpg",
      "local_thumb_path": "catalog/gold/eagles/thumbs/..._thumb.jpg",
      "local_raw_path": "data/raw/abc123full.jpg"
    }
  ]
}
```

---

## Confidence Scoring

Each candidate is scored against its bucket's specs:

| Field           | Weight | Notes                                            |
|-----------------|--------|--------------------------------------------------|
| Metal           | +0.20  | "gold", "silver", etc. in title                  |
| Weight          | +0.20  | With synonyms: "1oz" = "one troy ounce" = "1 oz" |
| Mint/Refiner    | +0.20  | Fuzzy match, common variants                     |
| Product Family  | +0.20  | "eagle", "maple leaf", "britannia", etc.          |
| Product Series  | +0.10  | Exact series name match                          |
| Denomination    | +0.05  | "$50", "$1", etc.                                |
| Year            | +0.05  | Fixed-year buckets only                          |

**Warning caps** (reduce max score):
- `size_mismatch`: caps at 0.55
- `example_image`: caps at 0.50
- `generic_image`: caps at 0.40
- `lot_image`: caps at 0.55
- `retailer` source: caps at 0.75

---

## Adding a New Source

1. Create `adapters/my_source.py` subclassing `BaseAdapter`:

```python
from adapters import BaseAdapter, build_candidate

class MySourceAdapter(BaseAdapter):
    name = "My Source"
    source_type = "licensed"  # or public_domain, approved_db, retailer
    source_priority = 5

    def find_candidates(self, bucket):
        candidates = []
        # ... your search logic ...
        candidates.append(build_candidate(
            url="https://...",
            raw_source_title="Product name from source",
            source_name=self.name,
            source_type=self.source_type,
            source_page_url="https://...",
            license_type="CC-BY-SA",
            attribution_text="Author name",
        ))
        return candidates[:self.max_results]
```

2. Register it in `config/source_registry.py`:

```python
from adapters.my_source import MySourceAdapter
# Add to _load_registry():
"my_source": MySourceAdapter,
# Add to SWEEP_ORDER, METAL_SOURCES, FAMILY_SOURCES as appropriate
```

3. Run it:
```bash
python scripts/run_by_source.py my_source --all
```

---

## Export to Metex

The export script reads manifests and calls `BucketImageService` to ingest
candidates into the Metex `bucket_image_assets` table:

```bash
DATABASE_URL=postgresql://... python scripts/export_to_metex.py --all
```

After export, candidates appear in the Metex admin dashboard under:
**Admin → Bucket Images → [bucket] → Assets**

Auto-activation rules (from Metex):
- `public_domain` + confidence ≥ 0.75 + no warnings → **auto-active**
- Everything else → **pending** (admin reviews and activates manually)

---

## Requirements

```
requests>=2.28
Pillow>=9.0      # image processing (strongly recommended)
imagehash>=4.3   # perceptual dedup (optional)
```

Install:
```bash
pip install requests Pillow imagehash
```
