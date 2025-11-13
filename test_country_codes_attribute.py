#!/usr/bin/env python3
"""
Test script to verify country_codes attribute handling
Tests that FuzzyMatcher properly initializes and maintains the country_codes attribute
"""

import sys
import os

# Add the EPG-Janitor directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'EPG-Janitor'))

from fuzzy_matcher import FuzzyMatcher

def test_country_codes_initialization():
    """Test that country_codes attribute is properly initialized"""
    print("=" * 60)
    print("TEST 1: Country Codes Attribute Initialization")
    print("=" * 60)

    # Test 1: FuzzyMatcher initialized without country_codes
    print("\n1. Testing FuzzyMatcher() with no country_codes parameter...")
    fm1 = FuzzyMatcher(plugin_dir=os.path.join(os.path.dirname(__file__), 'EPG-Janitor'))
    assert hasattr(fm1, 'country_codes'), "FuzzyMatcher should have country_codes attribute!"
    assert fm1.country_codes is None, "country_codes should be None when not specified!"
    print(f"   ✓ Has country_codes attribute: {hasattr(fm1, 'country_codes')}")
    print(f"   ✓ Value is None: {fm1.country_codes is None}")

    # Test 2: FuzzyMatcher initialized with country_codes
    print("\n2. Testing FuzzyMatcher() with country_codes=['US', 'CA']...")
    fm2 = FuzzyMatcher(
        plugin_dir=os.path.join(os.path.dirname(__file__), 'EPG-Janitor'),
        country_codes=['US', 'CA']
    )
    assert hasattr(fm2, 'country_codes'), "FuzzyMatcher should have country_codes attribute!"
    assert fm2.country_codes == ['US', 'CA'], "country_codes should match initialized value!"
    print(f"   ✓ Has country_codes attribute: {hasattr(fm2, 'country_codes')}")
    print(f"   ✓ Value is ['US', 'CA']: {fm2.country_codes == ['US', 'CA']}")

    print("\n✅ TEST 1 PASSED\n")

def test_reload_databases():
    """Test that reload_databases properly updates country_codes"""
    print("=" * 60)
    print("TEST 2: Reload Databases Updates Country Codes")
    print("=" * 60)

    fm = FuzzyMatcher(plugin_dir=os.path.join(os.path.dirname(__file__), 'EPG-Janitor'))

    # Initial state
    print("\n1. Initial state (no country filter)...")
    assert fm.country_codes is None, "Initial country_codes should be None!"
    print(f"   ✓ country_codes is None: {fm.country_codes is None}")

    # Reload with specific country codes
    print("\n2. Reloading with country_codes=['AU', 'UK']...")
    success = fm.reload_databases(country_codes=['AU', 'UK'])
    assert success, "reload_databases should return True on success!"
    assert fm.country_codes == ['AU', 'UK'], "country_codes should be updated after reload!"
    print(f"   ✓ reload_databases returned True: {success}")
    print(f"   ✓ country_codes updated to ['AU', 'UK']: {fm.country_codes == ['AU', 'UK']}")

    # Reload with None (all databases)
    print("\n3. Reloading with country_codes=None (all databases)...")
    success = fm.reload_databases(country_codes=None)
    assert success, "reload_databases should return True on success!"
    assert fm.country_codes is None, "country_codes should be None after reload with None!"
    print(f"   ✓ reload_databases returned True: {success}")
    print(f"   ✓ country_codes reset to None: {fm.country_codes is None}")

    print("\n✅ TEST 2 PASSED\n")

def test_defensive_code_simulation():
    """Simulate the defensive code check from plugin.py"""
    print("=" * 60)
    print("TEST 3: Defensive Code Simulation")
    print("=" * 60)

    fm = FuzzyMatcher(plugin_dir=os.path.join(os.path.dirname(__file__), 'EPG-Janitor'))

    print("\n1. Testing hasattr check (normal case)...")
    if not hasattr(fm, 'country_codes'):
        fm.country_codes = None
        print("   ⚠️ Had to initialize country_codes (should not happen with current code)")
    else:
        print("   ✓ country_codes attribute exists")

    print(f"   ✓ country_codes value: {fm.country_codes}")

    # Simulate deletion of attribute (edge case)
    print("\n2. Simulating missing attribute (edge case)...")
    delattr(fm, 'country_codes')
    assert not hasattr(fm, 'country_codes'), "Attribute should be deleted!"
    print("   ✓ Attribute deleted (simulating old version)")

    # Defensive code should handle this
    if not hasattr(fm, 'country_codes'):
        fm.country_codes = None
        print("   ✓ Defensive code successfully initialized country_codes")

    assert hasattr(fm, 'country_codes'), "Defensive code should restore attribute!"
    assert fm.country_codes is None, "Defensive code should set to None!"
    print(f"   ✓ country_codes now exists: {hasattr(fm, 'country_codes')}")
    print(f"   ✓ country_codes value: {fm.country_codes}")

    print("\n✅ TEST 3 PASSED\n")

def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("TESTING COUNTRY_CODES ATTRIBUTE HANDLING")
    print("=" * 60 + "\n")

    try:
        test_country_codes_initialization()
        test_reload_databases()
        test_defensive_code_simulation()

        print("=" * 60)
        print("ALL TESTS PASSED! ✅")
        print("=" * 60)
        print("\nSummary:")
        print("  - FuzzyMatcher properly initializes country_codes attribute")
        print("  - reload_databases correctly updates country_codes")
        print("  - Defensive code successfully handles missing attribute")
        print("\nThe country_codes attribute is properly implemented!")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
