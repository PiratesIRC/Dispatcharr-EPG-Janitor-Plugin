# Code Style and Conventions

## General Guidelines
- No formal style guide enforced
- No linting or formatting tools configured
- No type hints required
- No specific docstring format required

## Observed Patterns

### Naming Conventions
- **Classes**: PascalCase (e.g., `Plugin`, `FuzzyMatcher`)
- **Methods**: snake_case (e.g., `_get_api_token`, `scan_missing_epg_action`)
- **Private methods**: Prefixed with underscore (e.g., `_auto_match_channels`, `_load_token_cache`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `LOGGER`, `FUZZY_MATCH_THRESHOLD`, `PLUGIN_NAME`)
- **Variables**: snake_case (e.g., `results_file`, `scan_progress`)

### File Organization
- Plugin modules placed in subdirectory named after plugin
- Main plugin class in `plugin.py`
- Utility modules as separate files (e.g., `fuzzy_matcher.py`)
- Configuration in `plugin.json`

### Logging
- Uses Python standard `logging` module
- Logger instances named after module (e.g., `logging.getLogger("plugins.fuzzy_matcher")`)
- Logger stored in `LOGGER` constant

### Documentation
- Module docstrings in triple quotes at file top
- Inline comments for complex logic
- README files in .txt format

### Pattern Usage
- Extensive use of regex for text processing
- JSON for data storage and configuration
- Glob patterns for file discovery