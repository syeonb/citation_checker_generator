#!/usr/bin/env python3
"""
Citation Checker - Validates BibTeX entries against Semantic Scholar

This script:
1. Parses a BibTeX file
2. Searches Semantic Scholar for each entry
3. Compares and validates metadata (title, authors, year, venue)
4. Reports discrepancies and missing entries
"""

import re
import time
import argparse
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from difflib import SequenceMatcher
import json
import os
import shutil


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPORT_PATH = os.path.join(SCRIPT_DIR, 'result', 'citation_report.json')


@dataclass
class Citation:
    """Represents a parsed BibTeX citation"""
    key: str
    entry_type: str
    title: str
    authors: List[str]
    year: Optional[str]
    venue: Optional[str]
    raw_entry: str
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    url: Optional[str] = None


class BibTeXParser:
    """Parser for BibTeX files"""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.string_defs = {}  # Store @String definitions

    def parse(self) -> List[Citation]:
        """Parse the BibTeX file and return list of citations"""
        with open(self.filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # First pass: extract @String definitions
        self._parse_string_definitions(content)

        citations = []
        for entry_type, key, fields, raw_entry in self._iter_entries(content):
            citation = self._parse_entry(key, entry_type, fields, raw_entry)
            if citation:
                citations.append(citation)

        return citations

    def _parse_string_definitions(self, content: str):
        """Parse @String definitions with balanced brace handling"""
        pattern = re.compile(r'@string\s*(\{|\()', re.IGNORECASE)
        pos = 0

        while True:
            match = pattern.search(content, pos)
            if not match:
                break

            opening = match.group(1)
            closing = '}' if opening == '{' else ')'
            body, end_idx = self._extract_balanced_block(content, match.end(), opening, closing)
            fields = self._parse_fields(body)

            for name, value in fields.items():
                cleaned = self._clean_value(value)
                if cleaned:
                    self.string_defs[name.lower()] = cleaned
            pos = end_idx

    def _iter_entries(self, content: str):
        """Yield all non-String BibTeX entries found in the content"""
        pattern = re.compile(r'@(\w+)\s*(\{|\()', re.IGNORECASE)
        pos = 0

        while True:
            match = pattern.search(content, pos)
            if not match:
                break

            entry_type = match.group(1).lower()
            opening = match.group(2)
            closing = '}' if opening == '{' else ')'
            body, end_idx = self._extract_balanced_block(content, match.end(), opening, closing)
            raw_entry = content[match.start():end_idx]
            pos = end_idx

            if entry_type in {'string', 'comment', 'preamble'}:
                continue

            key, fields = self._split_key_and_fields(body)
            if not key:
                continue

            yield entry_type, key, fields, raw_entry

    def _split_key_and_fields(self, body: str) -> Tuple[Optional[str], str]:
        """Split the entry body into citation key and field string"""
        depth = 0

        for idx, char in enumerate(body):
            if char == '{':
                depth += 1
            elif char == '}':
                if depth > 0:
                    depth -= 1
            elif char == ',' and depth == 0:
                key = body[:idx].strip()
                fields = body[idx + 1:].strip()
                return key, fields

        return body.strip(), ''

    def _parse_fields(self, fields_str: str) -> Dict[str, str]:
        """Parse a BibTeX fields block into a dictionary"""
        fields = {}
        i = 0
        length = len(fields_str)

        while i < length:
            i = self._skip_whitespace(fields_str, i)
            if i >= length:
                break

            name_start = i
            while i < length:
                char = fields_str[i]
                if char in '=\n,' or char.isspace():
                    break
                i += 1
            field_name = fields_str[name_start:i].strip().lower()
            i = self._skip_whitespace(fields_str, i)

            if i >= length or fields_str[i] != '=':
                comma_idx = fields_str.find(',', i)
                if comma_idx == -1:
                    break
                i = comma_idx + 1
                continue

            i += 1  # Skip '='
            i = self._skip_whitespace(fields_str, i)
            value, i = self._consume_value(fields_str, i)

            if field_name:
                fields[field_name] = value.strip()

            i = self._skip_whitespace(fields_str, i)
            if i < length and fields_str[i] == ',':
                i += 1

        return fields

    def _get_field_value(self, field_map: Dict[str, str], name: str) -> Optional[str]:
        """Return cleaned field value from parsed fields"""
        return self._clean_value(field_map.get(name.lower()))

    def _consume_value(self, text: str, index: int) -> Tuple[str, int]:
        """Read a BibTeX value starting at index, handling concatenation"""
        if index >= len(text):
            return '', index

        segments = []
        i = index

        while i < len(text):
            char = text[i]
            if char == '{':
                segment, i = self._consume_braced_value(text, i)
            elif char == '"':
                segment, i = self._consume_quoted_value(text, i)
            else:
                segment, i = self._consume_unquoted_value(text, i)

            segments.append(segment)
            i = self._skip_whitespace(text, i)

            if i < len(text) and text[i] == '#':
                i += 1
                i = self._skip_whitespace(text, i)
                continue
            break

        return ''.join(segments), i

    def _consume_braced_value(self, text: str, index: int) -> Tuple[str, int]:
        depth = 0
        i = index + 1
        start = i

        while i < len(text):
            char = text[i]
            if char == '\\':
                i += 2
                continue
            if char == '{':
                depth += 1
            elif char == '}':
                if depth == 0:
                    return text[start:i], i + 1
                depth -= 1
            i += 1

        return text[start:], i

    def _consume_quoted_value(self, text: str, index: int) -> Tuple[str, int]:
        i = index + 1
        start = i

        while i < len(text):
            char = text[i]
            if char == '"' and (i == 0 or text[i - 1] != '\\'):
                return text[start:i], i + 1
            i += 1

        return text[start:], i

    def _consume_unquoted_value(self, text: str, index: int) -> Tuple[str, int]:
        i = index

        while i < len(text):
            char = text[i]
            if char.isspace() or char in ',#})':
                break
            i += 1

        return text[index:i], i

    def _skip_whitespace(self, text: str, index: int) -> int:
        while index < len(text) and text[index].isspace():
            index += 1
        return index

    def _clean_value(self, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None

        cleaned = value.strip()
        if not cleaned:
            return None

        lookup_key = cleaned.lower()
        if lookup_key in self.string_defs:
            cleaned = self.string_defs[lookup_key]

        cleaned = self._clean_latex(cleaned)
        return cleaned or None

    def _clean_latex(self, value: str) -> str:
        value = value.replace('{', '').replace('}', '')
        value = re.sub(r'\{\\[^}]+\}', '', value)
        value = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', value)
        value = re.sub(r'\\[a-zA-Z]+', '', value)
        value = re.sub(r'\s+', ' ', value).strip()
        return value

    def _extract_balanced_block(self, text: str, start_index: int, open_char: str, close_char: str) -> Tuple[str, int]:
        depth = 0
        i = start_index

        while i < len(text):
            char = text[i]
            if char == '\\':
                i += 2
                continue
            if char == '"':
                i = self._skip_quoted_region(text, i + 1)
                continue
            if char == open_char:
                depth += 1
            elif char == close_char:
                if depth == 0:
                    return text[start_index:i], i + 1
                depth -= 1
            i += 1

        return text[start_index:], len(text)

    def _skip_quoted_region(self, text: str, index: int) -> int:
        i = index
        while i < len(text):
            if text[i] == '"' and (i == 0 or text[i - 1] != '\\'):
                return i + 1
            i += 1
        return i

    def _parse_entry(self, key: str, entry_type: str, fields: str, raw_entry: str) -> Optional[Citation]:
        """Parse individual BibTeX entry fields"""
        field_map = self._parse_fields(fields)

        title = self._get_field_value(field_map, 'title')
        authors = self._extract_authors(self._get_field_value(field_map, 'author'))
        year = self._get_field_value(field_map, 'year')
        venue = (
            self._get_field_value(field_map, 'journal') or
            self._get_field_value(field_map, 'booktitle') or
            self._get_field_value(field_map, 'howpublished')
        )
        doi = self._get_field_value(field_map, 'doi')
        arxiv_id = self._extract_arxiv_id(field_map)
        url = self._get_field_value(field_map, 'url')

        if not title:
            return None

        return Citation(
            key=key,
            entry_type=entry_type,
            title=title,
            authors=authors,
            year=year,
            venue=venue,
            raw_entry=raw_entry,
            doi=doi,
            arxiv_id=arxiv_id,
            url=url
        )

    def _extract_arxiv_id(self, field_map: Dict[str, str]) -> Optional[str]:
        """Extract arXiv ID from various fields"""
        # Check eprint field first
        eprint = self._get_field_value(field_map, 'eprint')
        if eprint:
            return eprint

        # Check URL for arxiv pattern
        url = self._get_field_value(field_map, 'url')
        if url:
            match = re.search(r'arxiv\.org/(?:abs|pdf)/([0-9]+\.[0-9]+(?:v[0-9]+)?)', url, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def _extract_authors(self, author_str: Optional[str]) -> List[str]:
        """Extract and parse author list, returning full names as in BibTeX"""
        if not author_str:
            return []

        authors = [a.strip() for a in re.split(r'\s+and\s+', author_str, flags=re.IGNORECASE)]
        return [a for a in authors if a]


class CitationValidator:
    """Validates citations by comparing with Semantic Scholar results"""

    def __init__(self, use_api: bool = True):
        self.use_api = use_api
        self.base_url = "https://api.semanticscholar.org/graph/v1"
        print("✓ Using Semantic Scholar API for citation validation")

    def validate_citation(self, citation: Citation) -> Dict:
        """
        Validate a single citation against Semantic Scholar
        Returns a dict with validation results
        """
        import requests

        try:
            # Search Semantic Scholar by title
            print(f"  Searching: {citation.title[:60]}...")

            search_url = f"{self.base_url}/paper/search"
            params = {
                'query': citation.title,
                'limit': 1,
                'fields': 'title,authors,year,venue,citationCount,externalIds,url'
            }

            response = requests.get(search_url, params=params, timeout=10)

            if response.status_code != 200:
                return {
                    'citation_key': citation.key,
                    'status': 'error',
                    'message': f'API error: {response.status_code}',
                    'local_data': {
                        'title': citation.title,
                        'authors': citation.authors,
                        'year': citation.year,
                        'venue': citation.venue
                    }
                }

            data = response.json()

            if not data.get('data') or len(data['data']) == 0:
                # Construct Google Scholar URL as fallback
                scholar_url = f"https://scholar.google.com/scholar?q={citation.title.replace(' ', '+')}"
                return {
                    'citation_key': citation.key,
                    'status': 'not_found',
                    'message': 'No results found on Semantic Scholar',
                    'local_data': {
                        'title': citation.title,
                        'authors': citation.authors,
                        'year': citation.year,
                        'venue': citation.venue
                    },
                    'scholar_url': scholar_url
                }

            result = data['data'][0]

            # Extract data from Semantic Scholar result
            s2_title = result.get('title', '')
            s2_authors = [a.get('name', '') for a in result.get('authors', [])]
            s2_year = result.get('year')
            s2_venue = result.get('venue', '')
            s2_citations = result.get('citationCount', 0)

            # Build paper URL
            paper_id = result.get('paperId', '')
            s2_url = f"https://www.semanticscholar.org/paper/{paper_id}" if paper_id else None

            # Also get DOI/ArXiv links if available
            external_ids = result.get('externalIds', {})
            doi_url = f"https://doi.org/{external_ids['DOI']}" if external_ids.get('DOI') else None
            arxiv_url = f"https://arxiv.org/abs/{external_ids['ArXiv']}" if external_ids.get('ArXiv') else None

            # Prefer DOI > ArXiv > S2 for the main URL
            main_url = doi_url or arxiv_url or s2_url

            # Google Scholar search URL as backup
            scholar_url = f"https://scholar.google.com/scholar?q={citation.title.replace(' ', '+')}"


            # Compare fields
            discrepancies = []

            # Title similarity
            title_similarity = self._similarity(citation.title.lower(), s2_title.lower())
            if title_similarity < 0.8:
                discrepancies.append(f"Title mismatch (similarity: {title_similarity:.2f})")

            # Author similarity (compare normalized lists as joined strings)
            local_author_signatures = [self._author_signature(a) for a in citation.authors] if citation.authors else []
            scholar_author_signatures = [self._author_signature(a) for a in s2_authors] if s2_authors else []
            local_author_full = [self._normalize_author(a) for a in citation.authors] if citation.authors else []
            scholar_author_full = [self._normalize_author(a) for a in s2_authors] if s2_authors else []
            local_authors_str = ", ".join(local_author_signatures)
            scholar_authors_str = ", ".join(scholar_author_signatures)
            author_similarity = self._similarity(local_authors_str, scholar_authors_str) if local_author_signatures and scholar_author_signatures else 0.0
            author_signature_match = bool(local_author_signatures and scholar_author_signatures and local_authors_str == scholar_authors_str)
            author_full_match = bool(local_author_full and scholar_author_full and ", ".join(local_author_full) == ", ".join(scholar_author_full))
            author_initial_equivalent = author_signature_match and not author_full_match
            if local_author_signatures and scholar_author_signatures and author_similarity < 1.0:
                discrepancies.append(f"Author: local={citation.authors}, s2={s2_authors} (similarity: {author_similarity:.2f})")


            # Venue normalization: treat 'arxiv' and 'arXiv.org' as equivalent
            local_venue = self._normalize_venue(citation.venue)
            scholar_venue = self._normalize_venue(s2_venue)
            # If both are 'arxiv', treat as perfect match
            if local_venue == "arxiv" and scholar_venue == "arxiv":
                venue_similarity = 1.0
            else:
                venue_similarity = self._similarity(local_venue, scholar_venue) if local_venue and scholar_venue else 0.0
            if local_venue and scholar_venue and venue_similarity < 1.0:
                discrepancies.append(f"Venue: local='{citation.venue}', s2='{s2_venue}' (similarity: {venue_similarity:.2f})")

            # Year difference
            year_difference = None
            if citation.year and s2_year:
                try:
                    year_difference = abs(int(citation.year) - int(s2_year))
                except ValueError:
                    year_difference = citation.year != s2_year

            if year_difference:
                discrepancies.append(f"Year difference: |local: {citation.year} - s2: {s2_year}| = {year_difference}")

            status = 'match' if not discrepancies else 'discrepancy'

            result_payload = {
                'citation_key': citation.key,
                'status': status,
                'discrepancies': discrepancies,
                'local_data': {
                    'title': citation.title,
                    'authors': citation.authors,
                    'year': citation.year,
                    'venue': citation.venue
                },
                'scholar_data': {
                    'title': s2_title,
                    'authors': s2_authors,
                    'year': s2_year,
                    'venue': s2_venue,
                    'citations': s2_citations,
                    'url': main_url,
                    's2_url': s2_url,
                    'doi_url': doi_url,
                    'arxiv_url': arxiv_url,
                    'google_scholar_url': scholar_url
                },
                'similarity': {
                    'title': title_similarity,
                    'authors': author_similarity,
                    'venue': venue_similarity,
                    'year_difference': year_difference
                },
                'author_initial_equivalent': author_initial_equivalent
            }
            return result_payload

        except Exception as e:
            return {
                'citation_key': citation.key,
                'status': 'error',
                'message': str(e),
                'local_data': {
                    'title': citation.title,
                    'authors': citation.authors,
                    'year': citation.year,
                    'venue': citation.venue
                }
            }

    def _normalize_author(self, name: str) -> str:
        """Normalize author names for comparison"""
        if not name:
            return ''
        normalized = name.strip().lower()
        if ',' in normalized:
            parts = [p.strip() for p in normalized.split(',')]
            if len(parts) == 2:
                return f"{parts[1]} {parts[0]}"
        return normalized

    def _author_signature(self, name: str) -> str:
        """Build a comparable author signature using initials and last name"""
        normalized = self._normalize_author(name)
        if not normalized:
            return ''
        cleaned = normalized.replace('.', ' ')
        tokens = [t for t in cleaned.split() if t]
        if not tokens:
            return ''
        if len(tokens) == 1:
            return tokens[0]
        last = tokens[-1]
        initials = ''.join(t[0] for t in tokens[:-1] if t)
        return f"{initials} {last}".strip()

    def _normalize_venue(self, venue: Optional[str]) -> str:
        """Normalize venue names for comparison"""
        if not venue:
            return ''
        v = venue.lower().strip()

        # arXiv
        if v in {"arxiv", "arxiv.org", "arxiv org", "arxiv.org.", "arxiv preprint", "arxiv eprint"}:
            return "arxiv"

        # ICLR
        iclr_variants = {
            "int. conf. learn. represent.",
            "international conference on learning representations",
            "iclr",
            "int conf on learning representations",
            "int conf. on learning representations",
            "int. conf. on learning representations",
            "international conf. on learning representations",
            "international conf on learning representations"
        }
        if v in iclr_variants:
            return "iclr"

        # CVPR (main conference)
        cvpr_main_variants = {
            "ieee conf. comput. vis. pattern recog.",
            "computer vision and pattern recognition",
            "cvpr",
            "ieee conf. on computer vision and pattern recognition",
            "ieee conference on computer vision and pattern recognition",
            "ieee conf. comput. vision and pattern recognition",
            "ieee conf. on comput. vis. pattern recog.",
            "ieee conf. comput. vision & pattern recognition",
            "ieee/cvf conference on computer vision and pattern recognition",
            "ieee/cvf conf. comput. vis. pattern recog.",
            "ieee/cvf conf. on computer vision and pattern recognition",
            "ieee/cvf conf. comput. vision and pattern recognition",
            "ieee/cvf conference on computer vision and pattern recognition",
        }
        if v in cvpr_main_variants:
            return "cvpr"

        # CVPR Workshops (separate from CVPR main)
        cvpr_workshop_variants = {
            "ieee conf. comput. vis. pattern recog. worksh.",
            "ieee conference on computer vision and pattern recognition workshops",
            "ieee conference on computer vision and pattern recognition workshop",
            "cvpr workshops",
            "cvpr workshop",
            "cvprw",
            "ieee conf. on computer vision and pattern recognition workshops",
            "ieee/cvf conference on computer vision and pattern recognition workshops",
            "ieee/cvf conference on computer vision and pattern recognition workshop",
        }
        if v in cvpr_workshop_variants or ("cvpr" in v and "workshop" in v):
            return "cvprw"

        # ECCV
        if v in {
            "eur. conf. comput. vis.",
            "european conference on computer vision",
            "eccv",
            "european conf. on computer vision",
            "european conf. computer vision"
        }:
            return "eccv"

        # NeurIPS / NIPS
        neurips_variants = {
            "adv. neural inform. process. syst.",
            "advances in neural information processing systems",
            "neural information processing systems",
            "neurips",
            "nips"
        }
        if v in neurips_variants or "neurips" in v or "nips" in v:
            return "neurips"

        # ICCV
        iccv_variants = {
            "int. conf. comput. vis.",
            "international conference on computer vision",
            "ieee international conference on computer vision",
            "iccv"
        }
        if v in iccv_variants:
            return "iccv"

        # SIGGRAPH
        siggraph_variants = {
            "acm trans. graph.",
            "acm transactions on graphics",
            "siggraph",
            "acm trans. on graphics",
            "acm transactions on graphics (tog)",
            "acm tog"
        }
        if v in siggraph_variants:
            return "siggraph"

        # IEEE TIP
        ieee_tip_variants = {
            "ieee trans. image process.",
            "ieee transactions on image processing",
            "tip"
        }
        if v in ieee_tip_variants:
            return "ieee_tip"

        # TPAMI
        tpami_variants = {
            "ieee trans. pattern anal. mach. intell.",
            "ieee transactions on pattern analysis and machine intelligence",
            "tpami"
        }
        if v in tpami_variants:
            return "tpami"

        # TMLR
        tmlr_variants = {
            "trans. mach. learn. research",
            "trans. mach. learn. res.",
            "transactions on machine learning research",
            "tmlr"
        }
        if v in tmlr_variants:
            return "tmlr"

        # ACM MM
        acmmm_variants = {
            "acm int. conf. multimedia",
            "acm multimedia",
            "acm mm"
        }
        if v in acmmm_variants:
            return "acmmm"

        # ICML
        icml_variants = {
            "icml",
            "int. conf. mach. learn.",
            "international conference on machine learning"
        }
        if v in icml_variants:
            return "icml"

        # IJCV
        ijcv_variants = {
            "int. j. comput. vis.",
            "international journal of computer vision"
        }
        if v in ijcv_variants:
            return "ijcv"

        return v

    def _similarity(self, a: str, b: str) -> float:
        """Calculate similarity ratio between two strings"""
        return SequenceMatcher(None, a, b).ratio()

    def validate_all(self, citations: List[Citation], delay: float = 2.0,
                      json_output: str = None, failed_output: str = None) -> List[Dict]:
        """
        Validate all citations with rate limiting and continuous output

        Args:
            citations: List of Citation objects
            delay: Delay between requests in seconds (to avoid rate limiting)
            json_output: Path to JSON output file for continuous updates
        """
        results = []
        total = len(citations)

        print(f"\nValidating {total} citations...")
        print("=" * 70)

        for i, citation in enumerate(citations, 1):
            print(f"\n[{i}/{total}] {citation.key}")
            result = self.validate_citation(citation)
            result['index'] = i  # Add sequential numbering
            results.append(result)

            # Write intermediate results after each citation
            if json_output:
                with open(json_output, 'w', encoding='utf-8') as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)

            # Continuously save failed citations as well
            if failed_output:
                failed = [r for r in results if r['status'] == 'error']
                if failed:
                    os.makedirs(os.path.dirname(failed_output), exist_ok=True)
                    with open(failed_output, 'w', encoding='utf-8') as f:
                        json.dump(failed, f, indent=2, ensure_ascii=False)
                else:
                    if os.path.exists(failed_output):
                        os.remove(failed_output)

            # Add delay to avoid rate limiting (except for last item)
            if i < total:
                time.sleep(delay)

        return results


class DuplicateChecker:
    """Detects duplicate and similar entries in BibTeX citations"""

    def __init__(self, title_threshold: float = 0.85, author_threshold: float = 0.8):
        """
        Initialize duplicate checker

        Args:
            title_threshold: Minimum similarity ratio to consider titles as similar (default: 0.85)
            author_threshold: Minimum author overlap ratio to consider similar (default: 0.8)
        """
        self.title_threshold = title_threshold
        self.author_threshold = author_threshold

    def find_duplicates(self, citations: List[Citation]) -> List[Dict]:
        """
        Find all duplicate and similar citations

        Returns a list of duplicate groups, where each group contains similar citations
        """
        duplicates = []
        processed = set()

        for i, citation1 in enumerate(citations):
            if citation1.key in processed:
                continue

            group = []

            for j, citation2 in enumerate(citations):
                if i == j or citation2.key in processed:
                    continue

                similarity_info = self._check_similarity(citation1, citation2)

                if similarity_info['is_duplicate']:
                    if not group:
                        # Start a new group with the first citation
                        group.append({
                            'citation_key': citation1.key,
                            'title': citation1.title,
                            'authors': citation1.authors,
                            'year': citation1.year,
                            'venue': citation1.venue,
                            'doi': citation1.doi,
                            'arxiv_id': citation1.arxiv_id
                        })

                    group.append({
                        'citation_key': citation2.key,
                        'title': citation2.title,
                        'authors': citation2.authors,
                        'year': citation2.year,
                        'venue': citation2.venue,
                        'doi': citation2.doi,
                        'arxiv_id': citation2.arxiv_id
                    })

                    processed.add(citation2.key)

            if group:
                processed.add(citation1.key)
                duplicates.append({
                    'group': group,
                    'reason': similarity_info['reason'],
                    'similarity_score': similarity_info['score']
                })

        return duplicates

    def _check_similarity(self, cit1: Citation, cit2: Citation) -> Dict:
        """
        Check if two citations are duplicates or similar

        Returns a dict with is_duplicate, reason, and similarity score
        """
        reasons = []
        max_score = 0.0

        # 1. Check exact DOI match (strongest indicator)
        if cit1.doi and cit2.doi:
            if cit1.doi.lower() == cit2.doi.lower():
                return {
                    'is_duplicate': True,
                    'reason': 'Same DOI',
                    'score': 1.0
                }

        # 2. Check exact arXiv ID match
        if cit1.arxiv_id and cit2.arxiv_id:
            # Normalize arxiv IDs (remove version numbers for comparison)
            arxiv1 = re.sub(r'v\d+$', '', cit1.arxiv_id)
            arxiv2 = re.sub(r'v\d+$', '', cit2.arxiv_id)
            if arxiv1 == arxiv2:
                return {
                    'is_duplicate': True,
                    'reason': 'Same arXiv ID',
                    'score': 1.0
                }

        # 3. Check title similarity
        title_similarity = self._similarity(
            cit1.title.lower(),
            cit2.title.lower()
        )
        max_score = max(max_score, title_similarity)

        if title_similarity >= self.title_threshold:
            reasons.append(f'Similar title (similarity: {title_similarity:.2f})')

        # 4. Check author overlap
        author_overlap = self._author_overlap(cit1.authors, cit2.authors)

        if author_overlap >= self.author_threshold:
            reasons.append(f'Similar authors (overlap: {author_overlap:.2f})')

        # 5. Combine criteria
        # Consider duplicates if high title similarity AND some author overlap
        # OR very high title similarity alone
        is_duplicate = False
        combined_reason = None

        if title_similarity >= 0.95:
            # Very high title similarity alone
            is_duplicate = True
            combined_reason = f'Very similar title (similarity: {title_similarity:.2f})'
        elif title_similarity >= self.title_threshold and author_overlap >= self.author_threshold:
            # Both title and author similarity
            is_duplicate = True
            combined_reason = f'Similar title ({title_similarity:.2f}) and authors ({author_overlap:.2f})'
        elif title_similarity >= self.title_threshold and author_overlap >= 0.5:
            # Good title similarity with moderate author overlap
            is_duplicate = True
            combined_reason = f'Similar title ({title_similarity:.2f}) with author overlap ({author_overlap:.2f})'

        return {
            'is_duplicate': is_duplicate,
            'reason': combined_reason if combined_reason else '; '.join(reasons),
            'score': title_similarity
        }

    def _similarity(self, a: str, b: str) -> float:
        """Calculate similarity ratio between two strings"""
        return SequenceMatcher(None, a, b).ratio()

    def _author_overlap(self, authors1: List[str], authors2: List[str]) -> float:
        """
        Calculate author overlap ratio using last names
        Returns a value between 0 and 1
        """
        if not authors1 or not authors2:
            return 0.0

        # Extract last names
        last_names1 = {self._get_last_name(a).lower() for a in authors1}
        last_names2 = {self._get_last_name(a).lower() for a in authors2}

        # Calculate Jaccard similarity
        intersection = len(last_names1 & last_names2)
        union = len(last_names1 | last_names2)

        return intersection / union if union > 0 else 0.0

    def _get_last_name(self, author: str) -> str:
        """Extract last name from author string"""
        if ',' in author:
            # Format: "Last, First"
            return author.split(',')[0].strip()
        else:
            # Format: "First Last" - take last token
            tokens = author.strip().split()
            return tokens[-1] if tokens else author


class ReportGenerator:
    """Generates validation reports"""

    @staticmethod
    def print_summary(results: List[Dict]):
        """Print a summary of validation results"""
        print("\n" + "=" * 70)
        print("VALIDATION SUMMARY")
        print("=" * 70)

        status_counts = {}
        for result in results:
            status = result['status']
            status_counts[status] = status_counts.get(status, 0) + 1

        total = len(results)
        print(f"\nTotal citations checked: {total}")
        print(f"  ✓ Matches: {status_counts.get('match', 0)}")
        print(f"  ⚠ Discrepancies: {status_counts.get('discrepancy', 0)}")
        print(f"  ✗ Not found: {status_counts.get('not_found', 0)}")
        print(f"  ? Not checked: {status_counts.get('not_checked', 0)}")
        print(f"  ! Errors: {status_counts.get('error', 0)}")

    @staticmethod
    def print_detailed_report(results: List[Dict]):
        """Print detailed report of all issues"""
        print("\n" + "=" * 70)
        print("DETAILED REPORT")
        print("=" * 70)

        # Group by status
        issues = [r for r in results if r['status'] in ['discrepancy', 'not_found', 'error']]

        if not issues:
            print("\n✓ No issues found! All citations validated successfully.")
            return

        for result in issues:
            index = result.get('index', '?')
            print(f"\n#{index} [{result['citation_key']}] - {result['status'].upper()}")
            print(f"  Local title: {result['local_data']['title']}")

            if result['status'] == 'discrepancy':
                print(f"  Scholar title: {result['scholar_data']['title']}")
                similarity = result.get('similarity', 0)
                if isinstance(similarity, dict):
                    print("  Similarity:")
                    for k, v in similarity.items():
                        if k == 'year_difference':
                            if v is not None:
                                print(f"    year_difference: {v}")
                        else:
                            print(f"    {k}: {v:.2f}")
                else:
                    print(f"  Similarity: {similarity:.2f}")
                if result['scholar_data'].get('url'):
                    print(f"  Google Scholar: {result['scholar_data']['url']}")
                print(f"  Issues:")
                for disc in result['discrepancies']:
                    print(f"    - {disc}")
            elif result['status'] == 'not_found':
                print(f"  ⚠ {result['message']}")
            elif result['status'] == 'error':
                print(f"  ! Error: {result['message']}")

    @staticmethod
    def save_json_report(results: List[Dict], output_file: str):
        """Save results to JSON file"""
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n✓ Full report saved to: {output_file}")

    def save_discrepancies_report(self, results: List[Dict], output_file: str):
        """Write human-readable discrepancies report to a text file"""
        report = self._build_discrepancy_summary(results)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("DISCREPANCIES REPORT\n")
            f.write("=" * 100 + "\n\n")
            f.write(f"Total discrepancies: {report['total_issues']}\n")
            f.write(f"  - Title mismatches: {len(report['title_mismatches'])}\n")
            f.write(f"  - Author mismatches: {len(report['author_mismatches'])}\n")
            f.write(f"  - Venue mismatches: {len(report['venue_mismatches'])}\n")
            f.write(f"  - Year mismatches: {len(report['year_mismatches'])}\n")
            f.write(f"  - Not found: {len(report['not_found'])}\n\n")

            if report['not_found']:
                f.write("NOT FOUND\n")
                f.write("-" * 100 + "\n\n")
                for i, entry in enumerate(report['not_found'], 1):
                    f.write(f"{i}. [#{entry['index']} {entry['citation_key']}]\n")
                    f.write(f"   Title: {entry['title']}\n")
                    f.write(f"   Google Scholar Search: {entry['scholar_url']}\n\n")

            combined_entries = self._combine_discrepancies(report)
            if combined_entries:
                f.write("DETAILED ENTRIES\n")
                f.write("-" * 100 + "\n\n")
                for i, entry in enumerate(combined_entries, 1):
                    f.write(f"{i}. [#{entry['index']} {entry['citation_key']}]\n")
                    f.write(f"   Title: {entry['local_title']}\n")
                    if entry['scholar_title']:
                        f.write(f"   Scholar Title: {entry['scholar_title']}\n")
                    if entry['url']:
                        f.write(f"   URL: {entry['url']}\n")
                    f.write(f"   Issues:\n")
                    for issue in entry['issues']:
                        f.write(f"     - {issue}\n")
                    f.write("\n")

        if report['total_issues'] > 0:
            print(f"✓ Discrepancies report saved to: {output_file}")
        else:
            print("✓ No discrepancies found")

    @staticmethod
    def _title_similarity_value(entry: Dict) -> float:
        """Return title similarity score for sorting"""
        sim = entry.get('similarity', 0)
        if isinstance(sim, dict):
            return sim.get('title', 0)
        return sim

    @staticmethod
    def _build_discrepancy_summary(results: List[Dict]) -> Dict:
        """Build structured discrepancy report"""
        title_discrepancies = []
        author_discrepancies = []
        venue_discrepancies = []
        year_discrepancies = []
        not_found_entries = []

        for result in results:
            if result['status'] == 'discrepancy' and 'scholar_data' in result:
                entry = ReportGenerator._build_discrepancy_entry(result)

                if entry['similarity']['title'] < 1.0:
                    title_discrepancies.append(entry)
                if entry['similarity']['authors'] < 1.0:
                    author_discrepancies.append(entry)
                if entry['similarity']['venue'] < 1.0:
                    venue_discrepancies.append(entry)
                if entry['similarity']['year_difference']:
                    year_discrepancies.append(entry)

            elif result['status'] == 'not_found':
                not_found_entries.append({
                    'index': result.get('index', '?'),
                    'citation_key': result['citation_key'],
                    'title': result['local_data']['title'],
                    'scholar_url': result.get('scholar_url', 'N/A')
                })

        title_discrepancies.sort(key=ReportGenerator._title_similarity_value)

        issue_keys = set()
        for collection in (title_discrepancies, author_discrepancies, venue_discrepancies, year_discrepancies):
            issue_keys.update(entry['citation_key'] for entry in collection)
        issue_keys.update(entry['citation_key'] for entry in not_found_entries)

        return {
            'total_issues': len(issue_keys),
            'title_mismatches': title_discrepancies,
            'author_mismatches': author_discrepancies,
            'venue_mismatches': venue_discrepancies,
            'year_mismatches': year_discrepancies,
            'not_found': not_found_entries
        }

    @staticmethod
    def _combine_discrepancies(report: Dict) -> List[Dict]:
        """Combine discrepancy categories into a single entry list"""
        combined = {}

        def ensure_entry(source):
            key = source['citation_key']
            if key not in combined:
                combined[key] = {
                    'index': source.get('index', '?'),
                    'citation_key': key,
                    'local_title': source['local_title'],
                    'scholar_title': source.get('scholar_title'),
                    'url': source.get('url'),
                    'issues': []
                }
            return combined[key]

        for entry in report['title_mismatches']:
            record = ensure_entry(entry)
            for disc in entry.get('discrepancies', []):
                if disc.strip().startswith('Title'):
                    record['issues'].append(disc)

        for entry in report['author_mismatches']:
            record = ensure_entry(entry)
            for disc in entry.get('discrepancies', []):
                if disc.strip().startswith('Author:'):
                    record['issues'].append(disc)

        for entry in report['venue_mismatches']:
            record = ensure_entry(entry)
            for disc in entry.get('discrepancies', []):
                if 'Venue:' in disc:
                    record['issues'].append(disc)

        for entry in report['year_mismatches']:
            record = ensure_entry(entry)
            for disc in entry.get('discrepancies', []):
                if 'Year difference' in disc:
                    record['issues'].append(disc)

        combined_list = list(combined.values())
        combined_list.sort(key=lambda e: e['index'] if isinstance(e['index'], int) else float('inf'))
        return combined_list

    @staticmethod
    def _build_discrepancy_entry(result: Dict) -> Dict:
        """Normalize discrepancy entry for JSON serialization"""
        local_title = result['local_data']['title']
        scholar_title = result['scholar_data']['title']
        similarity = result.get('similarity', 0)
        scholar_url = result['scholar_data'].get('url', 'N/A')
        discrepancies = result.get('discrepancies', [])

        if isinstance(similarity, dict):
            title_similarity = similarity.get('title', 0)
            author_similarity = similarity.get('authors', 0)
            venue_similarity = similarity.get('venue', 0)
            year_difference = similarity.get('year_difference')
        else:
            title_similarity = similarity
            author_similarity = 0
            venue_similarity = 0
            year_difference = None

        return {
            'index': result.get('index', '?'),
            'citation_key': result['citation_key'],
            'local_title': local_title,
            'scholar_title': scholar_title,
            'similarity': {
                'title': title_similarity,
                'authors': author_similarity,
                'venue': venue_similarity,
                'year_difference': year_difference
            },
            'url': scholar_url,
            'discrepancies': discrepancies
        }



def _save_failed_report(failed: List[Dict]):
    """Save a report of failed citations as JSON in /result folder"""
    result_dir = os.path.join(SCRIPT_DIR, 'result')
    os.makedirs(result_dir, exist_ok=True)
    failed_path = os.path.join(result_dir, 'failed_citations.json')
    with open(failed_path, 'w', encoding='utf-8') as f:
        json.dump(failed, f, indent=2, ensure_ascii=False)


def _is_arxiv_venue(venue: Optional[str]) -> bool:
    """Return True if the venue string refers to arXiv"""
    return bool(venue and 'arxiv' in venue.lower())


def _save_arxiv_citations(results: List[Dict], output_file: str):
    """Persist citations associated with arXiv"""
    arxiv_citations = []
    for r in results:
        scholar_data = r.get('scholar_data', {})
        local_arxiv = _is_arxiv_venue(r.get('local_data', {}).get('venue'))
        scholar_arxiv = _is_arxiv_venue(scholar_data.get('venue'))
        if local_arxiv or scholar_arxiv:
            arxiv_citations.append(r)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(arxiv_citations, f, indent=2, ensure_ascii=False)

    if arxiv_citations:
        print(f"✓ ArXiv citations saved to: {output_file}")
    else:
        print("✓ No ArXiv citations found.")


def _save_author_initial_matches(results: List[Dict], output_file: str):
    """Persist citations whose authors matched via initials"""
    initial_matches = [r for r in results if r.get('author_initial_equivalent')]
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(initial_matches, f, indent=2, ensure_ascii=False)

    if initial_matches:
        print(f"✓ Author-initial matches saved to: {output_file}")
    else:
        print("✓ No author-initial matches found.")


def _clean_result_dir(result_dir: str):
    """Remove all files/directories inside the result folder"""
    if not os.path.exists(result_dir):
        return
    for entry in os.listdir(result_dir):
        path = os.path.join(result_dir, entry)
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        except OSError as exc:
            print(f"⚠ Unable to remove {path}: {exc}")


def main():
    parser = argparse.ArgumentParser(
        description='Citation Checker - Validate BibTeX entries against Google Scholar'
    )
    parser.add_argument(
        'bibfile',
        help='Path to BibTeX file'
    )
    parser.add_argument(
        '--output', '-o',
        default=DEFAULT_REPORT_PATH,
        help='Output JSON file for detailed report (default: result/citation_report.json)'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=1.5,
        help='Delay between Scholar queries in seconds (default: 1.5)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of citations to check (for testing)'
    )
    parser.add_argument(
        '--retry',
        action='store_true',
        help='Retry only failed citations from previous run'
    )

    args = parser.parse_args()
    args.output = os.path.abspath(args.output)
    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    result_dir = os.path.join(SCRIPT_DIR, 'result')
    os.makedirs(result_dir, exist_ok=True)
    if not args.retry:
        _clean_result_dir(result_dir)
    failed_json_path = os.path.join(result_dir, 'failed_citations.json')
    arxiv_json_path = os.path.join(result_dir, 'arxiv_citations.json')
    author_initial_json_path = os.path.join(result_dir, 'author_initial_matches.json')

    print("Citation Checker")
    print("=" * 70)

    # Parse BibTeX file
    print(f"\nParsing BibTeX file: {args.bibfile}")
    bib_parser = BibTeXParser(args.bibfile)
    all_citations = bib_parser.parse()
    print(f"✓ Parsed {len(all_citations)} citations")

    # Check for duplicates
    duplicates_json_path = os.path.join(result_dir, 'duplicates.json')
    duplicates_txt_path = os.path.join(result_dir, 'duplicates.txt')

    print("\n" + "=" * 70)
    print("CHECKING FOR DUPLICATES")
    print("=" * 70)

    duplicate_checker = DuplicateChecker(title_threshold=0.85, author_threshold=0.8)
    duplicate_groups = duplicate_checker.find_duplicates(all_citations)

    if duplicate_groups:
        print(f"\n⚠ Found {len(duplicate_groups)} groups of duplicate/similar entries:")

        # Save JSON report
        with open(duplicates_json_path, 'w', encoding='utf-8') as f:
            json.dump(duplicate_groups, f, indent=2, ensure_ascii=False)

        # Save text report
        with open(duplicates_txt_path, 'w', encoding='utf-8') as f:
            f.write("DUPLICATE ENTRIES REPORT\n")
            f.write("=" * 100 + "\n\n")
            f.write(f"Found {len(duplicate_groups)} groups of duplicate/similar entries\n\n")

            for i, dup_group in enumerate(duplicate_groups, 1):
                print(f"\n  Group {i}: {len(dup_group['group'])} similar entries")
                print(f"    Reason: {dup_group['reason']}")

                f.write(f"GROUP {i}\n")
                f.write("-" * 100 + "\n")
                f.write(f"Reason: {dup_group['reason']}\n")
                f.write(f"Similarity Score: {dup_group['similarity_score']:.2f}\n\n")

                for j, entry in enumerate(dup_group['group'], 1):
                    print(f"      {j}. [{entry['citation_key']}] {entry['title'][:60]}...")

                    f.write(f"  {j}. Citation Key: {entry['citation_key']}\n")
                    f.write(f"     Title: {entry['title']}\n")
                    f.write(f"     Authors: {', '.join(entry['authors']) if entry['authors'] else 'N/A'}\n")
                    f.write(f"     Year: {entry['year'] or 'N/A'}\n")
                    f.write(f"     Venue: {entry['venue'] or 'N/A'}\n")
                    if entry['doi']:
                        f.write(f"     DOI: {entry['doi']}\n")
                    if entry['arxiv_id']:
                        f.write(f"     arXiv: {entry['arxiv_id']}\n")
                    f.write("\n")

                f.write("\n")

        print(f"\n✓ Duplicate report saved to: {duplicates_txt_path}")
        print(f"✓ Duplicate JSON report saved to: {duplicates_json_path}")
    else:
        print("\n✓ No duplicates found!")
        # Remove duplicate files if they exist
        if os.path.exists(duplicates_json_path):
            os.remove(duplicates_json_path)
        if os.path.exists(duplicates_txt_path):
            os.remove(duplicates_txt_path)

    # Handle retry mode
    key_to_index = None
    previous_results_data = None
    if args.retry:
        if not os.path.exists(args.output):
            print(f"✗ No previous report found at {args.output}")
            print("  Run without --retry first to generate initial report")
            return
        if not os.path.exists(failed_json_path):
            print(f"✗ No failed citations report found at {failed_json_path}")
            print("  Run without --retry first to generate failed_citations.json")
            return

        with open(args.output, 'r') as f:
            previous_results_data = json.load(f)

        with open(failed_json_path, 'r', encoding='utf-8') as f:
            failed_results = json.load(f)

        failed_entries = [(r['citation_key'], r.get('index', '?')) for r in failed_results]
        if not failed_entries:
            print("\n✓ No failed citations to retry!")
            return

        failed_keys = [entry[0] for entry in failed_entries]
        key_to_index = {key: idx for key, idx in failed_entries}

        print(f"\n✓ Found {len(failed_keys)} failed citations to retry:")
        for i, (key, idx) in enumerate(failed_entries, 1):
            print(f"  {i}. [#{idx}] {key}")

        # Filter to only failed ones
        citations = [c for c in all_citations if c.key in failed_keys]

        if not citations:
            print("\n✓ No failed citations to retry!")
            return
    else:
        citations = all_citations
        if args.limit:
            citations = citations[:args.limit]

    print(f"\n✓ Processing {len(citations)} citations")

    validator = CitationValidator(use_api=True)
    results = validator.validate_all(
        citations,
        delay=args.delay,
        json_output=args.output if not args.retry else None,
        failed_output=failed_json_path if not args.retry else None
    )

    # In retry mode, restore original indices and merge with previous results
    if args.retry and key_to_index:
        for result in results:
            if result['citation_key'] in key_to_index:
                result['index'] = key_to_index[result['citation_key']]

        # Merge with previous results
        if previous_results_data is None:
            with open(args.output, 'r', encoding='utf-8') as f:
                previous_results = json.load(f)
        else:
            previous_results = previous_results_data

        # Create a mapping of citation_key to new result
        new_results_map = {r['citation_key']: r for r in results}

        # Update previous results
        for i, prev_result in enumerate(previous_results):
            key = prev_result['citation_key']
            if key in new_results_map:
                previous_results[i] = new_results_map[key]

        # Save merged results
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(previous_results, f, indent=2, ensure_ascii=False)

        print(f"\n✓ Updated report saved to: {args.output}")

        # Update failed_citations.json in /result
        failed = [r for r in previous_results if r['status'] == 'error']
        if failed:
            _save_failed_report(failed)
            print(f"✓ Updated failed_citations.json ({len(failed)} still failing)")
        else:
            # Remove failed_citations.json if no more failures
            if os.path.exists(failed_json_path):
                os.remove(failed_json_path)
            print("✓ All citations validated successfully!")

        results = previous_results

    _save_arxiv_citations(results, arxiv_json_path)
    _save_author_initial_matches(results, author_initial_json_path)

    # Generate final summary reports
    reporter = ReportGenerator()
    reporter.print_summary(results)
    reporter.print_detailed_report(results)

    if not args.retry:
        print(f"\n✓ Full report saved to: {args.output}")

        # Create initial failed_citations.json in /result
        failed = [r for r in results if r['status'] == 'error']
        if failed:
            _save_failed_report(failed)
            print(f"✓ Failed citations report saved to: {failed_json_path}")

    # Always generate discrepancies report in /result/discrepancies.txt
    discrepancies_file = os.path.join(result_dir, 'discrepancies.txt')
    reporter.save_discrepancies_report(results, discrepancies_file)

    print("\n" + "=" * 70)

    # Check if there are failed citations and retry if needed
    failed = [r for r in results if r['status'] == 'error']
    if failed and not args.retry:
        print(f"\nFound {len(failed)} failed citations. Starting auto-retry loop...")
        retry_count = 0

        while failed:
            retry_count += 1

            print("\n" + "=" * 70)
            print(f"RETRY ATTEMPT {retry_count}")
            print(f"Using delay: {args.delay:.1f}s between requests")
            print("=" * 70)

            # Get failed citation keys and their indices
            failed_keys = {r['citation_key']: r.get('index', '?') for r in failed}
            failed_citations = [c for c in all_citations if c.key in failed_keys]

            if not failed_citations:
                break

            print(f"\nRetrying {len(failed_citations)} failed citations...")

            # Retry the failed citations
            retry_results = validator.validate_all(
                failed_citations,
                delay=args.delay,
                json_output=None,
                failed_output=None
            )

            # Restore original indices
            for result in retry_results:
                if result['citation_key'] in failed_keys:
                    result['index'] = failed_keys[result['citation_key']]

            # Merge with previous results
            new_results_map = {r['citation_key']: r for r in retry_results}
            for i, prev_result in enumerate(results):
                key = prev_result['citation_key']
                if key in new_results_map:
                    results[i] = new_results_map[key]

            # Save updated results
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)

            # Update failed list
            failed = [r for r in results if r['status'] == 'error']

            # Update failed_citations.json
            if failed:
                _save_failed_report(failed)
                print(f"\n✓ Updated results. {len(failed)} citations still failing.")
            else:
                if os.path.exists(failed_json_path):
                    os.remove(failed_json_path)
                print("\n✓ All citations validated successfully!")
                break

        # Update arxiv and author initial matches
        _save_arxiv_citations(results, arxiv_json_path)
        _save_author_initial_matches(results, author_initial_json_path)

        # Generate final summary reports
        reporter.print_summary(results)
        reporter.print_detailed_report(results)

        # Update discrepancies report
        reporter.save_discrepancies_report(results, discrepancies_file)

    print("\n" + "=" * 70)
    print("Done!")


if __name__ == '__main__':
    main()
