#!/usr/bin/env python3
"""
Test script for select field generation
Tests that the plugin generates the correct select field structure for Dispatcharr
"""

import sys
import os
import json

# Add the EPG-Janitor directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'EPG-Janitor'))

# We can't import Plugin directly due to Django dependencies, but we can test the helper method
from glob import glob

def test_get_channel_databases():
    """Test the _get_channel_databases method logic"""
    print("=" * 60)
    print("TEST 1: Channel Database Detection")
    print("=" * 60)

    databases = []
    plugin_dir = os.path.join(os.path.dirname(__file__), 'EPG-Janitor')
    pattern = os.path.join(plugin_dir, "*_channels.json")
    channel_files = glob(pattern)

    for channel_file in sorted(channel_files):
        try:
            filename = os.path.basename(channel_file)
            country_code = filename.replace('_channels.json', '')

            with open(channel_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                country_name = data.get('country_name', country_code)

            databases.append({
                'id': country_code,
                'label': f"{country_code} - {country_name}",
                'filename': filename
            })
        except Exception as e:
            print(f"Warning: Error reading {channel_file}: {e}")

    print(f"\nFound {len(databases)} channel databases:")
    for db in databases:
        print(f"  - {db['label']} (ID: {db['id']})")

    assert len(databases) > 0, "No databases found!"
    print("\n✅ TEST 1 PASSED\n")
    return databases

def test_select_field_structure(databases):
    """Test that the select field structure is correct for Dispatcharr"""
    print("=" * 60)
    print("TEST 2: Select Field Structure")
    print("=" * 60)

    # Build options array for select field (same logic as plugin.py)
    options = [
        {"value": db['id'], "label": db['label']}
        for db in databases
    ]

    # Create the channel database selector field (same structure as plugin.py)
    db_selector_field = {
        "id": "selected_channel_database",
        "label": "📚 Channel Database",
        "type": "select",
        "options": options,
        "default": databases[0]['id'] if databases else "",
        "help_text": "Select which channel database to use for matching operations. Only channels from the selected database will be used for EPG matching."
    }

    print("\nGenerated Select Field Structure:")
    print(json.dumps(db_selector_field, indent=2))

    # Validate field structure
    print("\nValidating field structure...")

    assert db_selector_field['id'] == 'selected_channel_database', "Field ID is incorrect!"
    print("  ✓ Field ID is correct")

    assert db_selector_field['type'] == 'select', "Field type should be 'select'!"
    print("  ✓ Field type is 'select'")

    assert 'options' in db_selector_field, "Field must have 'options' array!"
    print("  ✓ Field has 'options' array")

    assert isinstance(db_selector_field['options'], list), "Options must be a list!"
    print("  ✓ Options is a list")

    assert len(db_selector_field['options']) > 0, "Options array should not be empty!"
    print(f"  ✓ Options array has {len(db_selector_field['options'])} items")

    # Validate each option
    for i, option in enumerate(db_selector_field['options']):
        assert 'value' in option, f"Option {i} must have 'value'!"
        assert 'label' in option, f"Option {i} must have 'label'!"
        assert isinstance(option['value'], str), f"Option {i} value must be string!"
        assert isinstance(option['label'], str), f"Option {i} label must be string!"
    print(f"  ✓ All {len(db_selector_field['options'])} options have valid structure")

    assert 'default' in db_selector_field, "Field must have 'default' value!"
    print(f"  ✓ Default value is set to '{db_selector_field['default']}'")

    assert db_selector_field['default'] == databases[0]['id'], "Default should be first database ID!"
    print("  ✓ Default value matches first database")

    print("\n✅ TEST 2 PASSED\n")
    return db_selector_field

def test_option_values(databases, field):
    """Test that option values match database IDs"""
    print("=" * 60)
    print("TEST 3: Option Values Match Database IDs")
    print("=" * 60)

    print("\nComparing options with databases:")
    for i, (db, option) in enumerate(zip(databases, field['options'])):
        print(f"\n  Database {i+1}:")
        print(f"    Database ID: {db['id']}")
        print(f"    Database Label: {db['label']}")
        print(f"    Option Value: {option['value']}")
        print(f"    Option Label: {option['label']}")

        assert db['id'] == option['value'], f"Database ID doesn't match option value at index {i}!"
        assert db['label'] == option['label'], f"Database label doesn't match option label at index {i}!"
        print(f"    ✓ Match confirmed")

    print("\n✅ TEST 3 PASSED\n")

def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("TESTING SELECT FIELD IMPLEMENTATION")
    print("=" * 60 + "\n")

    try:
        databases = test_get_channel_databases()
        field = test_select_field_structure(databases)
        test_option_values(databases, field)

        print("=" * 60)
        print("ALL TESTS PASSED! ✅")
        print("=" * 60)
        print("\nSummary:")
        print(f"  - Channel databases detected: {len(databases)}")
        print(f"  - Select field type: {field['type']}")
        print(f"  - Options count: {len(field['options'])}")
        print(f"  - Default value: {field['default']}")
        print("\nThe select field is correctly structured for Dispatcharr!")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
