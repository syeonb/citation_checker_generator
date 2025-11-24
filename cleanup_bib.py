#!/usr/bin/env python3
"""
BibTeX Cleanup Script

This script performs comprehensive cleanup on BibTeX files:
1. Removes duplicate entries (based on duplicates.json report)
2. Unifies venue names to @String references
3. Removes unwanted fields (pages, location, publisher, address, abstract)
"""

import re
import json
import os
import sys
from typing import Set

# Mapping of venue patterns to @String references
venue_mapping = {
    # Conferences (order matters - more specific patterns first)
    r'^(?:IEEE\s+)?(?:Conf(?:\.|erence)\s+(?:on\s+)?)?Comput(?:\.|er)\s+Vis(?:\.|ion)\s+(?:and\s+)?Pattern\s+Recog(?:\.|nition)\s+Worksh(?:\.|ops)$': 'CVPRW',
    r'^(?:IEEE\s+)?(?:Conf(?:\.|erence)\s+(?:on\s+)?)?Comput(?:\.|er)\s+Vis(?:\.|ion)\s+(?:and\s+)?Pattern\s+Recog(?:\.|nition)$': 'CVPR',
    r'^(?:Int(?:\.|ernational)\s+)?Conf(?:\.|erence)\s+(?:on\s+)?Comput(?:\.|er)\s+Vis(?:\.|ion)$': 'ICCV',
    r'^(?:Eur(?:\.|opean)\s+)?Conf(?:\.|erence)\s+(?:on\s+)?Comput(?:\.|er)\s+Vis(?:\.|ion)$': 'ECCV',
    r'^(?:Proceedings\s+of\s+the\s+\d+(?:st|nd|rd|th)?\s+)?(?:Adv(?:\.|ances)\s+(?:in\s+)?)?(?:Int(?:\.|ernational)\s+)?(?:Conf(?:\.|erence)\s+(?:on\s+)?)?Neural\s+Inform(?:\.|ation)\s+Process(?:\.|ing)\s+Syst(?:\.|ems)$': 'NeurIPS',
    r'^NIPS$': 'NIPS',
    r'^NeurIPS$': 'NeurIPS',
    r'^(?:Int(?:\.|ernational)\s+)?Conf(?:\.|erence)\s+(?:on\s+)?Pattern\s+Recog(?:\.|nition)$': 'ICPR',
    r'^(?:Brit(?:\.|ish)\s+)?Mach(?:\.|ine)\s+Vis(?:\.|ion)\s+Conf(?:\.|erence)$': 'BMVC',
    r'^ACM\s+Int(?:\.|ernational)\s+Conf(?:\.|erence)\s+(?:on\s+)?Multimedia$': 'ACMMM',
    r'^(?:Int(?:\.|ernational)\s+)?Conf(?:\.|erence)\s+(?:on\s+)?Multimedia\s+and\s+Expo$': 'ICME',
    r'^(?:Int(?:\.|ernational)\s+)?Conf(?:\.|erence)\s+(?:on|on\s+)Acous(?:\.|tics)?\s+Speech\s+(?:and\s+)?Signal\s+Process(?:\.|ing)$': 'ICASSP',
    r'^IEEE\s+Int(?:\.|ernational)\s+Conf(?:\.|erence)\s+(?:on\s+)?Image\s+Process(?:\.|ing)$': 'ICIP',
    r'^(?:Asian\s+)?Conf(?:\.|erence)\s+(?:on\s+)?Comput(?:\.|er)\s+Vis(?:\.|ion)$': 'ACCV',
    r'^(?:The\s+)?(?:First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth|Eleventh|Twelfth|Thirteenth|Fourteenth|Fifteenth|\d+(?:st|nd|rd|th))?\s*(?:Int(?:\.|ernational)\s+)?Conf(?:\.|erence)\s+(?:on\s+)?Learn(?:\.|ing)\s+Represent(?:\.|ations)\s*$': 'ICLR',
    r'^ICLR$': 'ICLR',
    r'^(?:Int(?:\.|ernational)\s+)?Joint\s+Conf(?:\.|erence)\s+(?:on\s+)?Artificial\s+Intell(?:\.|igence)$': 'IJCAI',
    r'^AAAI\s+Conf(?:\.|erence)\s+(?:on\s+)?Artificial\s+Intell(?:\.|igence)$': 'AAAI',
    r'^(?:IEEE\s+)?Winter\s+Conf(?:\.|erence)\s+(?:on\s+)?Appli(?:\.|cations)\s+(?:of\s+)?Comput(?:\.|er)\s+Vis(?:\.|ion)$': 'WACV',
    r'^WACV$': 'WACV',
    r'^ICML$': 'ICML',

    # Journals
    r'^IEEE\s+Trans(?:\.|actions)\s+(?:on\s+)?Pattern\s+Anal(?:\.|ysis)\s+(?:and\s+)?Mach(?:\.|ine)\s+Intell(?:\.|igence)$': 'TPAMI',
    r'^IEEE\s+TPAMI$': 'TPAMI',
    r'^(?:Int(?:\.|ernational)\s+)?J(?:\.|ournal)\s+(?:of\s+)?Comput(?:\.|er)\s+Vis(?:\.|ion)$': 'IJCV',
    r'^ACM\s+Trans(?:\.|actions)\s+(?:on\s+)?Graph(?:\.|ics)$': 'TOG',
    r'^IEEE\s+Trans(?:\.|actions)\s+(?:on\s+)?Image\s+Process(?:\.|ing)$': 'TIP',
    r'^IEEE\s+Trans(?:\.|actions)\s+(?:on\s+)?Vis(?:\.|ualization)\s+(?:and\s+)?Comput(?:\.|er)\s+Graph(?:\.|ics)$': 'TVCG',
    r'^IEEE\s+Trans(?:\.|actions)\s+(?:on\s+)?Multimedia$': 'TMM',
    r'^Pattern\s+Recognition$': 'PR',
    r'^IEEE\s+Trans(?:\.|actions)\s+(?:on\s+)?Circuit(?:s)?\s+(?:and\s+)?Syst(?:\.|ems)\s+(?:for\s+)?Video\s+Technol(?:\.|ogy)$': 'CSVT',
    r'^IEEE\s+Sign(?:\.|al)\s+Process(?:\.|ing)\s+Letters$': 'SPL',
    r'^Vis(?:\.|ion)\s+Res(?:\.|earch)$': 'VR',
    r'^J(?:\.|ournal)\s+(?:of\s+)?Vis(?:\.|ion)$': 'JOV',
    r'^The\s+Vis(?:\.|ual)\s+Comput(?:\.|er)$': 'TVC',
    r'^J(?:\.|ournal)\s+(?:of\s+)?Comput(?:\.|er)\s+Sci(?:\.|ence)\s+Tech(?:\.|nology)$': 'JCST',
    r'^Comput(?:\.|er)\s+Graph(?:\.|ics)\s+Forum$': 'CGF',
    r'^Computational\s+Visual\s+Media$': 'CVM',
    r'^Trans(?:\.|actions)\s+(?:on\s+)?Mach(?:\.|ine)\s+Learn(?:\.|ing)\s+Research$': 'TMLR',

    # Special
    r'^ARXIV$': 'arxiv',
    r'^arxiv$': 'arxiv',
    r'^ArXiv$': 'arxiv',
}

# Fields to remove from BibTeX entries
FIELDS_TO_REMOVE = ['pages', 'location', 'publisher', 'address', 'abstract', 'url', 'accessed']


def parse_duplicates_report(duplicates_json_path: str) -> Set[str]:
    """Parse the duplicates.json report and return a set of citation keys to remove."""
    if not os.path.exists(duplicates_json_path):
        return set()

    with open(duplicates_json_path, 'r', encoding='utf-8') as f:
        duplicate_groups = json.load(f)

    keys_to_remove = set()
    for group in duplicate_groups:
        entries = group['group']
        # Keep the first entry, remove the rest
        for entry in entries[1:]:
            keys_to_remove.add(entry['citation_key'])

    return keys_to_remove


def extract_balanced_block(text: str, start_index: int, open_char: str, close_char: str) -> tuple:
    """Extract a balanced block of braces/parentheses"""
    depth = 0
    i = start_index

    while i < len(text):
        char = text[i]
        if char == '\\':
            i += 2
            continue
        if char == '"':
            i = skip_quoted_region(text, i + 1)
            continue
        if char == open_char:
            depth += 1
        elif char == close_char:
            if depth == 0:
                return text[start_index:i], i + 1
            depth -= 1
        i += 1

    return text[start_index:], len(text)


def skip_quoted_region(text: str, index: int) -> int:
    """Skip over a quoted string"""
    i = index
    while i < len(text):
        if text[i] == '"' and (i == 0 or text[i - 1] != '\\'):
            return i + 1
        i += 1
    return i


def extract_citation_key(body: str) -> str:
    """Extract the citation key from the entry body"""
    depth = 0
    for idx, char in enumerate(body):
        if char == '{':
            depth += 1
        elif char == '}':
            if depth > 0:
                depth -= 1
        elif char == ',' and depth == 0:
            key = body[:idx].strip()
            return key
    return body.strip()


def normalize_whitespace(text):
    """Normalize whitespace in venue names"""
    return re.sub(r'\s+', ' ', text.strip())


def find_venue_reference(venue_text):
    """Find the appropriate @String reference for a venue name"""
    normalized = normalize_whitespace(venue_text)

    for pattern, string_ref in venue_mapping.items():
        if re.match(pattern, normalized, re.IGNORECASE):
            return string_ref

    return None


def process_bib_file(input_file, output_file, keys_to_remove=None):
    """Process BibTeX file: remove duplicates, unify venues, remove unwanted fields"""
    if keys_to_remove is None:
        keys_to_remove = set()

    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # First pass: remove duplicate entries
    entries_removed = []
    if keys_to_remove:
        pattern = re.compile(r'@(\w+)\s*(\{|\()', re.IGNORECASE)
        output_parts = []
        pos = 0

        while True:
            match = pattern.search(content, pos)
            if not match:
                output_parts.append(content[pos:])
                break

            entry_type = match.group(1).lower()
            opening = match.group(2)
            closing = '}' if opening == '{' else ')'

            body, end_idx = extract_balanced_block(content, match.end(), opening, closing)
            key = extract_citation_key(body)

            output_parts.append(content[pos:match.start()])

            if key and key in keys_to_remove:
                entries_removed.append(key)
            else:
                entry_text = content[match.start():end_idx]
                output_parts.append(entry_text)

            pos = end_idx

        content = ''.join(output_parts)

    # Second pass: process line by line for venue unification and field removal
    lines = content.split('\n')
    output_lines = []
    venue_changes = []
    removed_fields = []

    i = 0
    while i < len(lines):
        line = lines[i]
        previous_line = lines[i-1] if i > 0 else ''
        modified_line = line

        # Remove unwanted fields from the line
        # Pattern matches: field_name = value, or field_name = {value},
        for field in FIELDS_TO_REMOVE:
            # Skip URL if it's part of howpublished
            if field == 'url' and re.search(r'howpublished\s*=.*\\url', previous_line, re.IGNORECASE):
                continue

            # Pattern to match field with various formats
            # Handles: field={...}, field="...", field=value, with optional comma
            field_pattern = r',?\s*' + field + r'\s*=\s*(\{[^}]*\}|"[^"]*"|[^,}\s]+)\s*,?'
            if re.search(field_pattern, modified_line, re.IGNORECASE):
                removed_fields.append(f'  Removed {field} field')
                modified_line = re.sub(field_pattern, '', modified_line, flags=re.IGNORECASE)
                # Clean up double commas or trailing commas before closing brace
                modified_line = re.sub(r',\s*,', ',', modified_line)
                modified_line = re.sub(r',\s*}', '}', modified_line)

        # If line was completely removed or is now just whitespace, skip it
        if modified_line.strip() == '':
            i += 1
            continue

        # Check if this is a journal or booktitle field for venue unification
        match = re.match(r'(\s*)(journal|booktitle)(\s*=\s*)(\{?)([^,}]+?)(\}?)(,?\s*)$', modified_line, re.IGNORECASE)

        if match:
            indent = match.group(1)
            field_name = match.group(2)
            equals_part = match.group(3)
            open_brace = match.group(4)
            venue_text = match.group(5)
            close_brace = match.group(6)
            comma_part = match.group(7)

            if open_brace == '{' and close_brace == '}':
                string_ref = find_venue_reference(venue_text)

                if string_ref:
                    new_line = f'{indent}{field_name}{equals_part}{string_ref}{comma_part}'
                    output_lines.append(new_line)
                    venue_changes.append(f'  {venue_text} → {string_ref}')
                    i += 1
                    continue

        output_lines.append(modified_line)
        i += 1

    # Write output
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines))

    return entries_removed, venue_changes, removed_fields


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    duplicates_json = os.path.join(script_dir, 'validation_result', 'duplicates.json')
    input_bib = os.path.join(script_dir, 'main.bib')

    print("=" * 60)
    print("BibTeX Cleanup Script")
    print("=" * 60)

    # Load duplicates to remove
    keys_to_remove = parse_duplicates_report(duplicates_json)

    if keys_to_remove:
        print(f"\n[1] Duplicate Removal")
        print(f"Found {len(keys_to_remove)} duplicate entries to remove")
    else:
        print(f"\n[1] Duplicate Removal")
        print("No duplicates.json found or no duplicates to remove")

    # Process the file
    entries_removed, venue_changes, removed_fields = process_bib_file(
        input_bib, input_bib, keys_to_remove
    )

    # Report results
    if entries_removed:
        print(f"✓ Removed {len(entries_removed)} duplicate entries:")
        for key in entries_removed[:10]:
            print(f"    - {key}")
        if len(entries_removed) > 10:
            print(f"    ... and {len(entries_removed) - 10} more")

    print(f"\n[2] Venue Unification")
    print(f"Unified {len(venue_changes)} venue names")
    if venue_changes:
        for change in venue_changes[:10]:
            print(change)
        if len(venue_changes) > 10:
            print(f"  ... and {len(venue_changes) - 10} more")

    print(f"\n[3] Field Removal")
    print(f"Removed {len(removed_fields)} unwanted fields")
    if removed_fields:
        for change in removed_fields[:10]:
            print(change)
        if len(removed_fields) > 10:
            print(f"  ... and {len(removed_fields) - 10} more")

    print(f"\n{'=' * 60}")
    print("✓ Cleanup complete! main.bib has been updated.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
