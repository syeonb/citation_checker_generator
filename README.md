# Citation Checker

Validate BibTeX entries against Semantic Scholar and generate structured reports about metadata discrepancies.

## Features
- **BibTeX Parsing**: Handles complex BibTeX syntax including nested braces, quoted values, and `@string` macros
- **API Validation**: Queries the Semantic Scholar Graph API to compare title, authors, venue, and year
- **Streaming Output**: Writes results to `result/citation_report.json` continuously as citations are processed
- **Smart Retry**: Automatically retries failed citations and saves them to `result/failed_citations.json` for manual retry via `--retry` flag
- **Auto-Retry Loop**: Automatically retries all failed citations after initial run completes
- **Supplemental Reports**:
  - `result/arxiv_citations.json` - Citations associated with arXiv (by venue or Semantic Scholar external IDs)
  - `result/author_initial_matches.json` - Citations whose authors matched only after normalizing to initials
  - `result/discrepancies.txt` - Human-readable summary of all mismatches and not-found entries

## Requirements
- Python 3.9+
- `requests` library (install in virtual environment: `python3 -m venv .venv && . .venv/bin/activate && pip install requests`)

## Usage
Run the checker against a BibTeX file:

```bash
. .venv/bin/activate
python citation_checker.py main.bib
```

Useful flags:
- `--limit N` Process only the first `N` citations (handy for smoke tests).
- `--delay SECONDS` Control delay between API requests (default `1.0` seconds).
- `--output PATH` Choose a custom JSON report location (defaults to `result/citation_report.json`).
- `--retry` Re-run only the citations that previously failed (requires both the main report and `result/failed_citations.json` from an earlier run).

## Output Overview
All ancillary files live in the `result/` directory:

| File | Description |
| --- | --- |
| `citation_report.json` | Full per-citation validation results (written continuously during non-retry runs). |
| `failed_citations.json` | List of citations that hit API errors; automatically maintained and cleared when all errors resolve. |
| `arxiv_citations.json` | Subset of citations associated with arXiv (local venue, Semantic Scholar venue, or arXiv external ID). |
| `author_initial_matches.json` | Citations whose author lists matched only after normalizing to initials (e.g., "P. Smith" vs "Peter Smith"). |
| `discrepancies.txt` | Human-readable summary of title/author/venue/year mismatches and entries not found on Semantic Scholar. |

## Retrying Failed Citations
1. Run the checker normally to create the base report: `python citation_checker.py main.bib`.
2. After addressing rate limits/network issues, run `python citation_checker.py main.bib --retry`.  
   The tool reads `result/failed_citations.json`, reprocesses only those citations, and merges the new results into `citation_report.json`.

## Notes
- The Semantic Scholar API enforces rate limits; keep an adequate `--delay`.
- Network access is required for the API and for installing dependencies (if pip cannot reach the internet, download wheels ahead of time).
- Author comparison treats initials and full first names as equivalent; venue normalization covers common abbreviations (ICCV, NeurIPS, TPAMI, ACM MM, ICML, IJCV, etc.). Update `CitationValidator._normalize_venue` if more aliases are needed.

## TODO
- If paper was eventually published, we should list the publication year rather than arxiv upload year
- For arxiv only upload, refer to the earliest year it was uploaded