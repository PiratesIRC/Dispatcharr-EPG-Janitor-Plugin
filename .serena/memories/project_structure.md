# Project Structure

## Directory Layout
```
EPG-Janitor/
├── EPG-Janitor/              # Main plugin directory
│   ├── plugin.py             # Main plugin class (3211 lines)
│   ├── fuzzy_matcher.py      # Fuzzy matching module for channel name normalization
│   ├── plugin.json           # Plugin metadata and configuration
│   ├── readme.txt            # Plugin description
│   ├── __init__.py           # Python package initializer
│   └── *_channels.json       # Channel databases by country
│       ├── AU_channels.json  # Australia
│       ├── BR_channels.json  # Brazil
│       ├── CA_channels.json  # Canada
│       ├── DE_channels.json  # Germany
│       ├── ES_channels.json  # Spain
│       ├── FR_channels.json  # France
│       ├── IN_channels.json  # India
│       ├── MX_channels.json  # Mexico
│       ├── UK_channels.json  # United Kingdom
│       └── US_channels.json  # United States
└── EPG-Janitor.txt           # Additional documentation
```

## Key Files

### plugin.py
The main plugin implementation containing:
- **Plugin class**: Main class with all plugin functionality
- **Key constants**: LOGGER, FUZZY_MATCH_THRESHOLD, PLUGIN_NAME
- **Plugin version**: Tracked internally
- **Main actions**: 
  - run() - Main entry point
  - scan_missing_epg_action() - Scans for missing EPG data
  - auto_match channels methods (preview and apply)
  - scan_and_heal methods (dry run and apply)
  - remove_epg_assignments_action()
  - add_bad_epg_suffix_action()
  - remove_epg_from_hidden_action()
  - clear_csv_exports_action()
  - remove_epg_by_regex_action()
  - remove_all_epg_from_groups_action()
  - export_results_action()
  - get_summary_action()
  - validate_settings_action()

### fuzzy_matcher.py
Reusable fuzzy matching module containing:
- **FuzzyMatcher class**: Handles channel name normalization and matching
- **Version**: 25.330.1600 (Julian date format: YY.DDD.HHMM)
- **Key features**:
  - Callsign extraction for US TV channels
  - Name normalization with configurable pattern removal
  - Token-sort fuzzy matching
  - Channel database loading and management
  - Support for broadcast (OTA) and premium channels

### Channel Database Files
JSON files containing channel data organized by country:
- Channel names
- Callsigns (for broadcast channels)
- Categories
- Channel types (broadcast, premium, cable, national)