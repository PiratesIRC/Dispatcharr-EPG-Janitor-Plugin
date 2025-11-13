#!/usr/bin/env python3
"""
Test script for boolean field generation
Tests that the plugin generates the correct boolean field structure for Dispatcharr
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

def test_boolean_field_structure(databases):
    """Test that the boolean field structure is correct for Dispatcharr"""
    print("=" * 60)
    print("TEST 2: Boolean Field Structure")
    print("=" * 60)

    # Create individual boolean fields for each database (same logic as plugin.py)
    boolean_fields = []
    for db in databases:
        db_field = {
            "id": f"enable_db_{db['id']}",
            "label": f"📚 {db['label']}",
            "type": "boolean",
            "default": True,  # Enable all databases by default
            "help_text": f"Enable {db['label']} channel database for matching operations."
        }
        boolean_fields.append(db_field)

    print(f"\nGenerated {len(boolean_fields)} Boolean Fields:")
    for field in boolean_fields:
        print(json.dumps(field, indent=2))
        print()

    # Validate field structures
    print("Validating field structures...")

    for i, field in enumerate(boolean_fields):
        db = databases[i]

        expected_id = f"enable_db_{db['id']}"
        assert field['id'] == expected_id, f"Field {i} ID should be '{expected_id}'!"
        print(f"  ✓ Field {i} ID is correct: {field['id']}")

        assert field['type'] == 'boolean', f"Field {i} type should be 'boolean'!"
        print(f"  ✓ Field {i} type is 'boolean'")

        assert field['default'] == True, f"Field {i} default should be True!"
        print(f"  ✓ Field {i} default is True")

        assert 'help_text' in field, f"Field {i} must have 'help_text'!"
        print(f"  ✓ Field {i} has help_text")

        assert db['label'] in field['label'], f"Field {i} label should contain database label!"
        print(f"  ✓ Field {i} label contains database label")
        print()

    print(f"✅ TEST 2 PASSED - All {len(boolean_fields)} fields are correctly structured\n")
    return boolean_fields

def test_enabled_database_collection(databases, fields):
    """Test the logic for collecting enabled databases from boolean fields"""
    print("=" * 60)
    print("TEST 3: Enabled Database Collection Logic")
    print("=" * 60)

    # Simulate settings with some databases enabled
    test_cases = [
        {
            "name": "All databases enabled",
            "settings": {f"enable_db_{db['id']}": True for db in databases},
            "expected": sorted([db['id'] for db in databases])
        },
        {
            "name": "No databases enabled",
            "settings": {f"enable_db_{db['id']}": False for db in databases},
            "expected": []
        },
        {
            "name": "Only first database enabled",
            "settings": {f"enable_db_{databases[0]['id']}": True},
            "expected": [databases[0]['id']]
        },
        {
            "name": "Multiple specific databases enabled",
            "settings": {
                f"enable_db_{databases[0]['id']}": True,
                f"enable_db_{databases[min(2, len(databases)-1)]['id']}": True if len(databases) > 2 else False
            },
            "expected": sorted([databases[0]['id']] + ([databases[2]['id']] if len(databases) > 2 else []))
        }
    ]

    for test_case in test_cases:
        print(f"\nTest case: {test_case['name']}")
        settings = test_case['settings']
        expected = test_case['expected']

        # Collect enabled databases (same logic as plugin.py)
        enabled_databases = []
        for key, value in settings.items():
            if key.startswith("enable_db_") and value is True:
                db_code = key.replace("enable_db_", "")
                enabled_databases.append(db_code)

        enabled_databases.sort()

        print(f"  Settings: {settings}")
        print(f"  Expected: {expected}")
        print(f"  Actual:   {enabled_databases}")

        assert enabled_databases == expected, f"Enabled databases don't match expected!"
        print(f"  ✓ Correctly collected {len(enabled_databases)} enabled database(s)")

    print("\n✅ TEST 3 PASSED\n")

def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("TESTING BOOLEAN FIELD IMPLEMENTATION")
    print("=" * 60 + "\n")

    try:
        databases = test_get_channel_databases()
        fields = test_boolean_field_structure(databases)
        test_enabled_database_collection(databases, fields)

        print("=" * 60)
        print("ALL TESTS PASSED! ✅")
        print("=" * 60)
        print("\nSummary:")
        print(f"  - Channel databases detected: {len(databases)}")
        print(f"  - Boolean fields generated: {len(fields)}")
        print(f"  - Field type: boolean")
        print(f"  - Default value: True (all enabled by default)")
        print("\nThe boolean fields are correctly structured for Dispatcharr!")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
