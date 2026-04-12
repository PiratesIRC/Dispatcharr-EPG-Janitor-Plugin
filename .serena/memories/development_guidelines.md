# Development Guidelines

## Python Version
- Target: Python 3.13.8

## Dependencies
- Standard library only
- No external dependencies or requirements.txt file
- Uses built-in modules: logging, json, re, unicodedata, glob, os

## Plugin Architecture

### Dispatcharr Plugin System
The plugin integrates with Dispatcharr through:
- **plugin.json**: Defines plugin metadata, module path, class name, and actions
- **Plugin class**: Must implement required interface methods
- **Actions**: Exposed methods that can be triggered by Dispatcharr

### Key Plugin Methods
- `fields()`: Property that returns configuration fields for the plugin UI
- `run()`: Main entry point called by Dispatcharr
- Action methods: Named with `_action` suffix (e.g., `scan_missing_epg_action`)

## Module Design

### Reusability
The fuzzy_matcher.py module is designed for reuse across multiple Dispatcharr plugins:
- Stream-Mapparr
- Channel Mapparr
- EPG-Janitor (this plugin)

### Fuzzy Matching Features
- Callsign extraction for US broadcast channels
- Name normalization with pattern categories:
  - Quality patterns (4K, HD, SD, etc.)
  - Regional patterns (East, West)
  - Geographic patterns (US:, USA:)
  - Miscellaneous patterns (single letters, backup tags)
- Multi-stage matching: exact, substring, fuzzy
- Channel database management with country code filtering

## Data Storage
- Channel databases stored as JSON files with country code prefix
- Results exported to CSV files
- Cache files for tokens and version checks
- All data files use UTF-8 encoding

## Logging
- Uses Python standard logging module
- Log to plugin-specific logger names
- Log levels used appropriately (info, warning, error)

## Error Handling
- Try-except blocks for API calls and file operations
- Graceful degradation when features unavailable
- User-friendly error messages