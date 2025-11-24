# Citation Checker & Generator

A comprehensive toolkit for validating and generating BibTeX citations using the Semantic Scholar API.

## Tools

### 1. Citation Checker (`citation_checker.py`)
Validate existing BibTeX entries against Semantic Scholar and generate structured reports about metadata discrepancies.

### 2. Citation Generator (`citation_generator.py`)
Generate BibTeX entries from paper titles by querying Semantic Scholar with high-confidence matching.

---

## Citation Checker

### Features
- **BibTeX Parsing**: Handles complex BibTeX syntax including nested braces, quoted values, and `@string` macros
- **API Validation**: Queries the Semantic Scholar Graph API to compare title, authors, venue, and year
- **Duplicate Detection** (automatic): Finds duplicate and similar entries within the BibTeX file based on:
  - Exact DOI or arXiv ID matches
  - High title similarity (configurable threshold, default: 0.85)
  - Author overlap using last name comparison (configurable threshold, default: 0.8)
  - Combined scoring for intelligent duplicate detection
- **Streaming Output**: Writes results to `validation_result/citation_report.json` continuously as citations are processed
- **Auto-Retry Loop**: Automatically retries all failed citations after initial run completes until all succeed
- **Supplemental Reports**:
  - `validation_result/arxiv_citations.json` - Citations associated with arXiv (by venue or Semantic Scholar external IDs)
  - `validation_result/author_initial_matches.json` - Citations whose authors matched only after normalizing to initials
  - `validation_result/discrepancies.txt` - Human-readable summary of all mismatches and not-found entries
  - `validation_result/duplicates.txt` - Human-readable report of duplicate/similar entries
  - `validation_result/duplicates.json` - JSON format duplicate groups with similarity scores

### Usage

Run the checker against a BibTeX file:

```bash
. .venv/bin/activate
python citation_checker.py main.bib
```

Useful flags:
- `--limit N` Process only the first `N` citations (handy for smoke tests).
- `--delay SECONDS` Control delay between API requests (default `1.5` seconds).
- `--output PATH` Choose a custom JSON report location (defaults to `validation_result/citation_report.json`).

### Duplicate Detection

The tool automatically checks for duplicates at the start of every run. It will identify:
- **Exact matches**: Same DOI or arXiv ID
- **Very similar titles**: Title similarity ≥ 95%
- **Likely duplicates**: Title similarity ≥ 85% with author overlap ≥ 80%
- **Possible duplicates**: Title similarity ≥ 85% with author overlap ≥ 50%

Results are saved to `validation_result/duplicates.txt` and `validation_result/duplicates.json`.

### Output Overview

All output files live in the `validation_result/` directory:

| File | Description |
| --- | --- |
| `citation_report.json` | Full per-citation validation results (written continuously). |
| `failed_citations.json` | List of citations that hit API errors; automatically maintained and cleared when all errors resolve. |
| `arxiv_citations.json` | Subset of citations associated with arXiv (local venue, Semantic Scholar venue, or arXiv external ID). |
| `author_initial_matches.json` | Citations whose author lists matched only after normalizing to initials (e.g., "P. Smith" vs "Peter Smith"). |
| `discrepancies.txt` | Human-readable summary of title/author/venue/year mismatches and entries not found on Semantic Scholar. |
| `duplicates.txt` | Human-readable report of duplicate/similar citation entries found within the BibTeX file. |
| `duplicates.json` | JSON format duplicate groups with similarity scores and reasons. |

---

## Citation Generator

### Features
- **Semantic Scholar API Integration**: Queries papers by title with intelligent matching
- **High-Confidence Matching**: Only generates BibTeX for titles with ≥95% similarity (configurable)
- **Automatic BibTeX Generation**: Creates properly formatted entries with:
  - Auto-generated citation keys (FirstAuthorLastNameYearKeyword format)
  - Smart entry type detection (inproceedings vs article)
  - DOI and arXiv links when available
  - Proper author formatting
- **Result Categorization**:
  - **Matched**: High-confidence matches → `generated_citations.bib`
  - **Unmatched**: Low similarity or not found → `unmatched_titles.txt`
  - **Failed**: API errors (automatically retried) → `failed_queries.json`
- **Infinite Auto-Retry Loop**: Automatically retries failed queries until all complete
- **Streaming Output**: Results saved continuously during processing
- **Clean Start**: Automatically clears `generation_result/` directory before each run

### Usage

Create a text file with paper titles (one per line):

```text
Attention Is All You Need
Deep Residual Learning for Image Recognition
BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding
```

Run the generator:

```bash
. .venv/bin/activate
python citation_generator.py titles.txt
```

Useful flags:
- `--threshold 0.90` Set minimum title similarity (default: 0.95)
- `--delay 2.0` Control delay between API requests (default: 1.5 seconds)
- `--output-dir PATH` Choose output directory (default: `generation_result/`)

### Output Overview

All output files live in the `generation_result/` directory:

| File | Description |
| --- | --- |
| `generated_citations.bib` | BibTeX entries for all matched papers (ready to use). |
| `unmatched_titles.txt` | Human-readable list of titles that weren't found or had low similarity matches. |
| `generation_report.json` | Detailed JSON report with all results including match scores and metadata. |
| `failed_queries.json` | Temporarily stores failed queries; automatically removed when all queries complete. |

### Example Output

Input title:
```
Attention Is All You Need
```

Generated BibTeX:
```bibtex
@inproceedings{Vaswani2017Attention,
  title={Attention Is All You Need},
  author={Ashish Vaswani and Noam Shazeer and Niki Parmar and Jakob Uszkoreit and Llion Jones and Aidan N. Gomez and Lukasz Kaiser and Illia Polosukhin},
  year={2017},
  booktitle={Neural Information Processing Systems},
  url={https://www.semanticscholar.org/paper/...},
}
```

---

## Requirements
- Python 3.9+
- `requests` library (install in virtual environment: `python3 -m venv .venv && . .venv/bin/activate && pip install requests`)

## Installation

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
. .venv/bin/activate

# Install dependencies
pip install requests
```

## Directory Structure

```
citation_checker/
├── citation_checker.py       # Validation tool
├── citation_generator.py     # Generation tool
├── validation_result/        # Checker output directory
│   ├── citation_report.json
│   ├── discrepancies.txt
│   ├── duplicates.txt
│   └── ...
├── generation_result/        # Generator output directory
│   ├── generated_citations.bib
│   ├── unmatched_titles.txt
│   └── generation_report.json
└── .gitignore
```

## Notes
- The Semantic Scholar API enforces rate limits; keep an adequate `--delay`.
- Network access is required for the API and for installing dependencies.
- Author comparison treats initials and full first names as equivalent.
- Venue normalization covers common abbreviations (ICCV, NeurIPS, TPAMI, CVPR, ECCV, ICLR, ACM MM, ICML, IJCV, etc.).
  - **Important**: Distinguishes between main conferences and workshops (e.g., CVPR vs CVPRW)
  - Update `CitationValidator._normalize_venue` in the checker or `VenueUnifier._categorize_venue` if more aliases are needed.
- Duplicate detection uses configurable thresholds (see `DuplicateChecker` class). Lower thresholds will find more potential duplicates but may have false positives.
- Both tools automatically retry failed API requests in an infinite loop until completion.

## TODO
- If paper was eventually published, we should list the publication year rather than arxiv upload year
- For arxiv only upload, refer to the earliest year it was uploaded
- Add venue unification feature to replace similar venue names with @String definitions
