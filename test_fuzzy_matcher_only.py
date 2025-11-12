#!/usr/bin/env python3
"""
Test script for FuzzyMatcher country code filtering (without Django dependencies)
"""

import sys
import os

# Add the EPG-Janitor directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'EPG-Janitor'))

from fuzzy_matcher import FuzzyMatcher
from glob import glob
import json

def test_get_available_databases():
    """Test scanning for available database files"""
    print("=" * 60)
    print("TEST 1: Scan for Available Channel Databases")
    print("=" * 60)

    plugin_dir = os.path.join(os.path.dirname(__file__), 'EPG-Janitor')
    pattern = os.path.join(plugin_dir, "*_channels.json")
    channel_files = glob(pattern)

    print(f"\nFound {len(channel_files)} channel database files:")
    databases = []
    for channel_file in sorted(channel_files):
        filename = os.path.basename(channel_file)
        country_code = filename.replace('_channels.json', '')

        # Read the JSON file to get country name
        with open(channel_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            country_name = data.get('country_name', country_code)

        databases.append({
            'id': country_code,
            'label': f"{country_code} - {country_name}",
            'filename': filename
        })
        print(f"  - {country_code} - {country_name} ({filename})")

    assert len(databases) > 0, "No databases found!"
    print(f"\n✅ TEST 1 PASSED: Found {len(databases)} channel databases\n")
    return databases

def test_fuzzy_matcher_country_filter(databases):
    """Test FuzzyMatcher with country code filtering"""
    print("=" * 60)
    print("TEST 2: FuzzyMatcher Country Code Filtering")
    print("=" * 60)

    plugin_dir = os.path.join(os.path.dirname(__file__), 'EPG-Janitor')

    # Test loading first database only
    first_db = databases[0]['id']
    print(f"\n2a. Loading {first_db} database only...")
    matcher_single = FuzzyMatcher(plugin_dir=plugin_dir, country_codes=[first_db])
    single_total = len(matcher_single.broadcast_channels) + len(matcher_single.premium_channels)
    print(f"   {first_db} Database: {len(matcher_single.broadcast_channels)} broadcast + {len(matcher_single.premium_channels)} premium = {single_total} total channels")
    assert single_total > 0, f"No channels loaded from {first_db} database!"

    # Test loading second database (if available)
    if len(databases) > 1:
        second_db = databases[1]['id']
        print(f"\n2b. Loading {second_db} database only...")
        matcher_second = FuzzyMatcher(plugin_dir=plugin_dir, country_codes=[second_db])
        second_total = len(matcher_second.broadcast_channels) + len(matcher_second.premium_channels)
        print(f"   {second_db} Database: {len(matcher_second.broadcast_channels)} broadcast + {len(matcher_second.premium_channels)} premium = {second_total} total channels")
        assert second_total > 0, f"No channels loaded from {second_db} database!"

    # Test loading all databases
    print("\n2c. Loading all databases (no filter)...")
    matcher_all = FuzzyMatcher(plugin_dir=plugin_dir, country_codes=None)
    all_total = len(matcher_all.broadcast_channels) + len(matcher_all.premium_channels)
    print(f"   All Databases: {len(matcher_all.broadcast_channels)} broadcast + {len(matcher_all.premium_channels)} premium = {all_total} total channels")

    # Verify that ALL is greater than or equal to individual databases
    assert all_total >= single_total, "All databases should have at least as many channels as a single database!"
    print(f"\n   ✓ All databases ({all_total}) >= Single database ({single_total})")

    print("\n✅ TEST 2 PASSED: Country code filtering works correctly\n")

def test_reload_databases(databases):
    """Test reloading databases with different country codes"""
    print("=" * 60)
    print("TEST 3: Reload Databases Functionality")
    print("=" * 60)

    plugin_dir = os.path.join(os.path.dirname(__file__), 'EPG-Janitor')

    # Start with first database
    first_db = databases[0]['id']
    print(f"\n3a. Initial load with {first_db} database...")
    matcher = FuzzyMatcher(plugin_dir=plugin_dir, country_codes=[first_db])
    first_total = len(matcher.broadcast_channels) + len(matcher.premium_channels)
    print(f"   {first_db} Database: {first_total} total channels")
    print(f"   Current country_codes: {matcher.country_codes}")

    if len(databases) > 1:
        # Reload with second database
        second_db = databases[1]['id']
        print(f"\n3b. Reloading with {second_db} database...")
        success = matcher.reload_databases(country_codes=[second_db])
        assert success, f"Failed to reload {second_db} database!"
        second_total = len(matcher.broadcast_channels) + len(matcher.premium_channels)
        print(f"   {second_db} Database: {second_total} total channels")
        print(f"   Current country_codes: {matcher.country_codes}")

    # Reload with all databases
    print("\n3c. Reloading with all databases...")
    success = matcher.reload_databases(country_codes=None)
    assert success, "Failed to reload all databases!"
    all_total = len(matcher.broadcast_channels) + len(matcher.premium_channels)
    print(f"   All Databases: {all_total} total channels")
    print(f"   Current country_codes: {matcher.country_codes}")

    assert all_total >= first_total, "All databases should have at least as many channels as a single database!"

    print("\n✅ TEST 3 PASSED: Reload functionality works correctly\n")

def test_invalid_country_code():
    """Test handling of invalid country code"""
    print("=" * 60)
    print("TEST 4: Invalid Country Code Handling")
    print("=" * 60)

    plugin_dir = os.path.join(os.path.dirname(__file__), 'EPG-Janitor')

    print("\n4a. Attempting to load invalid country code 'INVALID'...")
    matcher = FuzzyMatcher(plugin_dir=plugin_dir, country_codes=['INVALID'])
    total = len(matcher.broadcast_channels) + len(matcher.premium_channels)
    print(f"   Total channels loaded: {total}")
    assert total == 0, "Should have 0 channels for invalid country code!"

    print("\n✅ TEST 4 PASSED: Invalid country codes handled correctly\n")

def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("TESTING DYNAMIC CHANNEL DATABASE SELECTOR")
    print("FuzzyMatcher Component Tests")
    print("=" * 60 + "\n")

    try:
        databases = test_get_available_databases()
        test_fuzzy_matcher_country_filter(databases)
        test_reload_databases(databases)
        test_invalid_country_code()

        print("=" * 60)
        print("ALL TESTS PASSED! ✅")
        print("=" * 60)
        print("\nSummary:")
        print(f"  - {len(databases)} channel databases available")
        print(f"  - Available databases: {', '.join([db['id'] for db in databases])}")
        print("\nThe FuzzyMatcher country code filtering is working correctly!")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
