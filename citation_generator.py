#!/usr/bin/env python3
"""
Citation Generator - Generates BibTeX entries from paper titles using Semantic Scholar

This script:
1. Takes a list of paper titles (from a text file, one per line)
2. Queries Semantic Scholar API for each title
3. Generates BibTeX entries for high-confidence matches
4. Saves unmatched titles to a separate file
"""

import re
import time
import argparse
import json
import os
import shutil
from typing import List, Dict, Optional, Tuple
from difflib import SequenceMatcher
from dataclasses import dataclass


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'generation_result')


@dataclass
class PaperResult:
    """Represents a paper search result"""
    query_title: str
    found: bool
    match_score: float
    s2_data: Optional[Dict] = None
    bibtex: Optional[str] = None
    error: Optional[str] = None


class CitationGenerator:
    """Generates BibTeX citations from paper titles using Semantic Scholar API"""

    def __init__(self, similarity_threshold: float = 0.95):
        """
        Initialize citation generator

        Args:
            similarity_threshold: Minimum title similarity to accept a match (default: 0.95)
        """
        self.base_url = "https://api.semanticscholar.org/graph/v1"
        self.similarity_threshold = similarity_threshold
        print(f"✓ Citation Generator initialized (similarity threshold: {similarity_threshold})")

    def search_paper(self, title: str) -> PaperResult:
        """
        Search for a paper by title and return results

        Args:
            title: Paper title to search for

        Returns:
            PaperResult object with search results
        """
        import requests

        try:
            print(f"  Searching: {title[:80]}...")

            search_url = f"{self.base_url}/paper/search"
            params = {
                'query': title,
                'limit': 1,
                'fields': 'title,authors,year,venue,publicationVenue,externalIds,publicationTypes,journal,url'
            }

            response = requests.get(search_url, params=params, timeout=10)

            if response.status_code != 200:
                return PaperResult(
                    query_title=title,
                    found=False,
                    match_score=0.0,
                    error=f'API error: {response.status_code}'
                )

            data = response.json()

            if not data.get('data') or len(data['data']) == 0:
                return PaperResult(
                    query_title=title,
                    found=False,
                    match_score=0.0,
                    error='No results found'
                )

            result = data['data'][0]
            s2_title = result.get('title', '')

            # Calculate title similarity
            similarity = self._similarity(title.lower(), s2_title.lower())

            if similarity < self.similarity_threshold:
                return PaperResult(
                    query_title=title,
                    found=False,
                    match_score=similarity,
                    s2_data=result,
                    error=f'Low similarity: {similarity:.2f} (threshold: {self.similarity_threshold})'
                )

            # High confidence match
            print(f"    ✓ Match found (similarity: {similarity:.2f}): {s2_title}")

            # Generate BibTeX entry
            bibtex = self._generate_bibtex(result)

            return PaperResult(
                query_title=title,
                found=True,
                match_score=similarity,
                s2_data=result,
                bibtex=bibtex
            )

        except Exception as e:
            return PaperResult(
                query_title=title,
                found=False,
                match_score=0.0,
                error=str(e)
            )

    def _similarity(self, a: str, b: str) -> float:
        """Calculate similarity ratio between two strings"""
        return SequenceMatcher(None, a, b).ratio()

    def _generate_bibtex(self, s2_result: Dict) -> str:
        """
        Generate BibTeX entry from Semantic Scholar result

        Args:
            s2_result: Semantic Scholar API result

        Returns:
            BibTeX entry as string
        """
        # Extract data
        title = s2_result.get('title', '')
        authors = s2_result.get('authors', [])
        year = s2_result.get('year')
        venue = s2_result.get('venue', '')
        external_ids = s2_result.get('externalIds', {})
        publication_types = s2_result.get('publicationTypes', [])
        journal_info = s2_result.get('journal', {})
        publication_venue = s2_result.get('publicationVenue', {})

        # Generate citation key
        citation_key = self._generate_citation_key(title, authors, year)

        # Determine entry type
        entry_type = self._determine_entry_type(publication_types, venue, journal_info)

        # Format authors
        author_str = self._format_authors(authors)

        # Build BibTeX entry
        bibtex_lines = [f"@{entry_type}{{{citation_key},"]

        # Add title
        bibtex_lines.append(f"  title={{{title}}},")

        # Add authors
        if author_str:
            bibtex_lines.append(f"  author={{{author_str}}},")

        # Add year
        if year:
            bibtex_lines.append(f"  year={{{year}}},")

        # Add venue (booktitle for conference, journal for article)
        if entry_type == 'inproceedings' and venue:
            bibtex_lines.append(f"  booktitle={{{venue}}},")
        elif entry_type == 'article':
            if journal_info and journal_info.get('name'):
                bibtex_lines.append(f"  journal={{{journal_info['name']}}},")
            elif venue:
                bibtex_lines.append(f"  journal={{{venue}}},")

        # Add DOI if available
        if external_ids.get('DOI'):
            bibtex_lines.append(f"  doi={{{external_ids['DOI']}}},")

        # Add arXiv ID if available
        if external_ids.get('ArXiv'):
            bibtex_lines.append(f"  eprint={{{external_ids['ArXiv']}}},")
            bibtex_lines.append(f"  archivePrefix={{arXiv}},")

        # Add URL
        if external_ids.get('DOI'):
            bibtex_lines.append(f"  url={{https://doi.org/{external_ids['DOI']}}},")
        elif s2_result.get('url'):
            bibtex_lines.append(f"  url={{{s2_result['url']}}},")

        bibtex_lines.append("}")

        return '\n'.join(bibtex_lines)

    def _generate_citation_key(self, title: str, authors: List[Dict], year: Optional[int]) -> str:
        """
        Generate a citation key in the format: FirstAuthorLastName_Year_FirstWord

        Args:
            title: Paper title
            authors: List of author dictionaries
            year: Publication year

        Returns:
            Citation key string
        """
        # Get first author's last name
        first_author = "Unknown"
        if authors and len(authors) > 0:
            author_name = authors[0].get('name', '')
            # Extract last name (assumes "First Last" format)
            parts = author_name.split()
            if parts:
                first_author = parts[-1]

        # Clean author name (remove special characters)
        first_author = re.sub(r'[^a-zA-Z]', '', first_author)

        # Get first significant word from title (skip common words)
        skip_words = {'a', 'an', 'the', 'on', 'in', 'for', 'of', 'and', 'to', 'with'}
        title_words = re.findall(r'\w+', title.lower())
        first_word = "Paper"
        for word in title_words:
            if word not in skip_words and len(word) > 2:
                first_word = word.capitalize()
                break

        # Construct key
        year_str = str(year) if year else "XXXX"
        citation_key = f"{first_author}{year_str}{first_word}"

        return citation_key

    def _determine_entry_type(self, publication_types: List[str], venue: str, journal_info: Dict) -> str:
        """
        Determine BibTeX entry type based on publication information

        Args:
            publication_types: List of publication types from S2
            venue: Venue name
            journal_info: Journal information dictionary

        Returns:
            BibTeX entry type (e.g., 'inproceedings', 'article')
        """
        # Check publication types
        if publication_types:
            for pub_type in publication_types:
                pub_type_lower = pub_type.lower()
                if 'conference' in pub_type_lower:
                    return 'inproceedings'
                elif 'journal' in pub_type_lower:
                    return 'article'

        # Check venue name for common patterns
        venue_lower = venue.lower() if venue else ''

        # Conference indicators
        conf_keywords = ['conference', 'symposium', 'workshop', 'proceedings', 'cvpr', 'iccv', 'eccv',
                         'neurips', 'nips', 'icml', 'iclr', 'aaai', 'ijcai', 'acl', 'emnlp', 'naacl']
        if any(keyword in venue_lower for keyword in conf_keywords):
            return 'inproceedings'

        # Journal indicators
        journal_keywords = ['journal', 'transactions', 'letters', 'magazine', 'review']
        if any(keyword in venue_lower for keyword in journal_keywords):
            return 'article'

        # Check if journal info exists
        if journal_info and journal_info.get('name'):
            return 'article'

        # ArXiv papers
        if 'arxiv' in venue_lower:
            return 'article'

        # Default to article
        return 'article'

    def _format_authors(self, authors: List[Dict]) -> str:
        """
        Format author list for BibTeX

        Args:
            authors: List of author dictionaries from S2

        Returns:
            Formatted author string
        """
        if not authors:
            return ''

        author_names = []
        for author in authors:
            name = author.get('name', '')
            if name:
                author_names.append(name)

        return ' and '.join(author_names)

    def generate_from_titles(self, titles: List[str], delay: float = 1.5,
                           json_output: str = None, failed_output: str = None,
                           unmatched_output: str = None) -> Tuple[List[PaperResult], List[PaperResult], List[PaperResult]]:
        """
        Generate citations for multiple titles with continuous output

        Args:
            titles: List of paper titles
            delay: Delay between API requests in seconds
            json_output: Path to save continuous JSON updates
            failed_output: Path to save failed queries (errors)
            unmatched_output: Path to save unmatched titles (low similarity)

        Returns:
            Tuple of (matched_results, unmatched_results, failed_results)
        """
        matched = []
        unmatched = []
        failed = []
        total = len(titles)

        print(f"\nProcessing {total} titles...")
        print("=" * 70)

        for i, title in enumerate(titles, 1):
            print(f"\n[{i}/{total}]")
            result = self.search_paper(title)
            result.index = i  # Track original position

            if result.found:
                matched.append(result)
            elif result.error and ('API error' in result.error or 'timeout' in result.error.lower() or 'connection' in result.error.lower()):
                # These are errors we should retry
                failed.append(result)
                print(f"    ! Failed: {result.error}")
            else:
                # Low similarity or not found - don't retry
                unmatched.append(result)
                if result.error:
                    print(f"    ✗ Not matched: {result.error}")

            # Save intermediate results
            if json_output:
                self._save_intermediate_json(matched, unmatched, failed, json_output)

            if failed_output and failed:
                self._save_failed_titles(failed, failed_output)
            elif failed_output and not failed:
                # Remove failed file if no failures
                if os.path.exists(failed_output):
                    os.remove(failed_output)

            if unmatched_output and unmatched:
                save_unmatched_file(unmatched, unmatched_output)

            # Rate limiting
            if i < total:
                time.sleep(delay)

        return matched, unmatched, failed

    def _save_intermediate_json(self, matched: List[PaperResult], unmatched: List[PaperResult],
                               failed: List[PaperResult], output_path: str):
        """Save intermediate JSON results"""
        report = {
            'summary': {
                'total': len(matched) + len(unmatched) + len(failed),
                'matched': len(matched),
                'unmatched': len(unmatched),
                'failed': len(failed)
            },
            'matched': [self._result_to_dict(r) for r in matched],
            'unmatched': [self._result_to_dict(r) for r in unmatched],
            'failed': [self._result_to_dict(r) for r in failed]
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

    def _result_to_dict(self, result: PaperResult) -> Dict:
        """Convert PaperResult to dictionary for JSON serialization"""
        return {
            'index': getattr(result, 'index', None),
            'query_title': result.query_title,
            'found': result.found,
            'match_score': result.match_score,
            'error': result.error,
            's2_title': result.s2_data.get('title') if result.s2_data else None,
            'authors': [a.get('name') for a in result.s2_data.get('authors', [])] if result.s2_data else [],
            'year': result.s2_data.get('year') if result.s2_data else None,
            'venue': result.s2_data.get('venue') if result.s2_data else None,
        }

    def _save_failed_titles(self, failed: List[PaperResult], output_path: str):
        """Save failed titles to JSON file"""
        failed_data = [self._result_to_dict(r) for r in failed]
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(failed_data, f, indent=2, ensure_ascii=False)


def load_titles_from_file(filepath: str) -> List[str]:
    """
    Load paper titles from a text file (one title per line)

    Args:
        filepath: Path to text file

    Returns:
        List of titles
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        titles = [line.strip() for line in f if line.strip()]
    return titles


def save_bibtex_file(results: List[PaperResult], output_path: str):
    """
    Save matched results to a BibTeX file

    Args:
        results: List of matched PaperResult objects
        output_path: Path to output .bib file
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, result in enumerate(results):
            if i > 0:
                f.write('\n\n')
            f.write(result.bibtex)

    print(f"\n✓ Generated {len(results)} BibTeX entries: {output_path}")


def save_unmatched_file(results: List[PaperResult], output_path: str):
    """
    Save unmatched titles to a text file

    Args:
        results: List of unmatched PaperResult objects
        output_path: Path to output text file
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("UNMATCHED TITLES\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Total unmatched: {len(results)}\n\n")

        for i, result in enumerate(results, 1):
            f.write(f"{i}. {result.query_title}\n")
            if result.error:
                f.write(f"   Reason: {result.error}\n")
            if result.s2_data:
                f.write(f"   Best match: {result.s2_data.get('title', 'N/A')}\n")
                f.write(f"   Similarity: {result.match_score:.2f}\n")
            f.write("\n")

    print(f"✓ Saved {len(results)} unmatched titles: {output_path}")


def save_json_report(matched: List[PaperResult], unmatched: List[PaperResult], failed: List[PaperResult], output_path: str):
    """
    Save detailed JSON report of generation results

    Args:
        matched: List of matched results
        unmatched: List of unmatched results
        failed: List of failed results
        output_path: Path to output JSON file
    """
    report = {
        'summary': {
            'total': len(matched) + len(unmatched) + len(failed),
            'matched': len(matched),
            'unmatched': len(unmatched),
            'failed': len(failed)
        },
        'matched': [
            {
                'index': getattr(r, 'index', None),
                'query_title': r.query_title,
                'match_score': r.match_score,
                's2_title': r.s2_data.get('title') if r.s2_data else None,
                'authors': [a.get('name') for a in r.s2_data.get('authors', [])] if r.s2_data else [],
                'year': r.s2_data.get('year') if r.s2_data else None,
                'venue': r.s2_data.get('venue') if r.s2_data else None,
            }
            for r in matched
        ],
        'unmatched': [
            {
                'index': getattr(r, 'index', None),
                'query_title': r.query_title,
                'error': r.error,
                'match_score': r.match_score,
                'best_match': r.s2_data.get('title') if r.s2_data else None
            }
            for r in unmatched
        ],
        'failed': [
            {
                'index': getattr(r, 'index', None),
                'query_title': r.query_title,
                'error': r.error
            }
            for r in failed
        ]
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"✓ Saved detailed report: {output_path}")


def clean_output_dir(output_dir: str):
    """Remove all files/directories inside the output folder"""
    if not os.path.exists(output_dir):
        return
    for entry in os.listdir(output_dir):
        path = os.path.join(output_dir, entry)
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        except OSError as exc:
            print(f"⚠ Unable to remove {path}: {exc}")


def main():
    parser = argparse.ArgumentParser(
        description='Citation Generator - Generate BibTeX entries from paper titles'
    )
    parser.add_argument(
        'input',
        help='Path to text file containing paper titles (one per line)'
    )
    parser.add_argument(
        '--output-dir', '-o',
        default=DEFAULT_OUTPUT_DIR,
        help='Output directory for results (default: generation_result/)'
    )
    parser.add_argument(
        '--threshold', '-t',
        type=float,
        default=0.95,
        help='Minimum title similarity threshold (default: 0.95)'
    )
    parser.add_argument(
        '--delay', '-d',
        type=float,
        default=1.5,
        help='Delay between API requests in seconds (default: 1.5)'
    )

    args = parser.parse_args()

    # Create output directory and clean it
    os.makedirs(args.output_dir, exist_ok=True)
    clean_output_dir(args.output_dir)

    print("Citation Generator")
    print("=" * 70)
    print(f"Input file: {args.input}")
    print(f"Output directory: {args.output_dir}")
    print(f"Similarity threshold: {args.threshold}")
    print(f"API delay: {args.delay}s")

    # Setup output paths
    json_path = os.path.join(args.output_dir, 'generation_report.json')
    failed_json_path = os.path.join(args.output_dir, 'failed_queries.json')
    unmatched_path = os.path.join(args.output_dir, 'unmatched_titles.txt')
    bib_path = os.path.join(args.output_dir, 'generated_citations.bib')

    # Load titles
    print(f"\nLoading titles from: {args.input}")
    all_titles = load_titles_from_file(args.input)
    print(f"✓ Loaded {len(all_titles)} titles")

    # Generate citations
    generator = CitationGenerator(similarity_threshold=args.threshold)
    matched, unmatched, failed = generator.generate_from_titles(
        all_titles,
        delay=args.delay,
        json_output=json_path,
        failed_output=failed_json_path,
        unmatched_output=unmatched_path
    )

    # Print summary
    print("\n" + "=" * 70)
    print("GENERATION SUMMARY")
    print("=" * 70)
    print(f"Total titles: {len(all_titles)}")
    print(f"  ✓ Matched: {len(matched)}")
    print(f"  ✗ Unmatched: {len(unmatched)}")
    print(f"  ! Failed: {len(failed)}")

    # Save results
    if matched:
        save_bibtex_file(matched, bib_path)

    if unmatched:
        save_unmatched_file(unmatched, unmatched_path)

    # Save JSON report
    save_json_report(matched, unmatched, failed, json_path)

    print("\n" + "=" * 70)

    # Auto-retry loop for failed queries
    if failed:
        print(f"\nFound {len(failed)} failed queries. Starting auto-retry loop...")
        retry_count = 0

        # Store all results for merging
        all_results = {
            'matched': matched,
            'unmatched': unmatched,
            'failed': failed
        }

        while all_results['failed']:
            retry_count += 1

            print("\n" + "=" * 70)
            print(f"RETRY ATTEMPT {retry_count}")
            print(f"Using delay: {args.delay:.1f}s between requests")
            print("=" * 70)

            # Get failed titles
            failed_titles = [r.query_title for r in all_results['failed']]
            title_to_index = {r.query_title: getattr(r, 'index', None) for r in all_results['failed']}

            print(f"\nRetrying {len(failed_titles)} failed queries...")

            # Retry
            retry_matched, retry_unmatched, retry_failed = generator.generate_from_titles(
                failed_titles,
                delay=args.delay,
                json_output=None,
                failed_output=None,
                unmatched_output=None
            )

            # Restore original indices
            for r in retry_matched + retry_unmatched + retry_failed:
                if r.query_title in title_to_index:
                    r.index = title_to_index[r.query_title]

            # Merge results
            # Remove old failed entries and add new results
            all_results['failed'] = []

            for r in retry_matched:
                all_results['matched'].append(r)
            for r in retry_unmatched:
                all_results['unmatched'].append(r)
            for r in retry_failed:
                all_results['failed'].append(r)

            # Save updated results
            if all_results['matched']:
                save_bibtex_file(all_results['matched'], bib_path)

            if all_results['unmatched']:
                save_unmatched_file(all_results['unmatched'], unmatched_path)

            save_json_report(all_results['matched'], all_results['unmatched'], all_results['failed'], json_path)

            # Update failed queries file
            if all_results['failed']:
                generator._save_failed_titles(all_results['failed'], failed_json_path)
                print(f"\n✓ Updated results. {len(all_results['failed'])} queries still failing.")
            else:
                if os.path.exists(failed_json_path):
                    os.remove(failed_json_path)
                print("\n✓ All queries completed successfully!")
                break

        # Final summary
        print("\n" + "=" * 70)
        print("FINAL SUMMARY")
        print("=" * 70)
        print(f"Total titles: {len(all_titles)}")
        print(f"  ✓ Matched: {len(all_results['matched'])}")
        print(f"  ✗ Unmatched: {len(all_results['unmatched'])}")
        print(f"  ! Failed: {len(all_results['failed'])}")

    print("\n" + "=" * 70)
    print("Done!")


if __name__ == '__main__':
    main()
