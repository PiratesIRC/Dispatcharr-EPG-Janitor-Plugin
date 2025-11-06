# EPG Janitor - Dispatcharr Plugin

**TIRED of channels showing "No Program Information Available"? FRUSTRATED with missing EPG data ruining your viewing experience?**

**Introducing EPG Janitor** - the POWERFUL Dispatcharr plugin that IDENTIFIES problematic channels in SECONDS and AUTOMATICALLY matches EPG data!

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin)

## ⚠️ Important: Backup Your Database

Before installing or using this plugin, it is highly recommended that you create a backup of your Dispatcharr database. This plugin makes significant changes to your channel and stream assignments.

[Click here for instructions on how to back up your database.](https://dispatcharr.github.io/Dispatcharr-Docs/troubleshooting/?h=backup#how-can-i-make-a-backup-of-the-database)

## What Does EPG Janitor Do?

EPG Janitor scans your Dispatcharr channel lineup to identify channels that have EPG assignments but are missing program data, causing them to display "No Program Information Available" in your TV guide. The plugin includes intelligent auto-matching capabilities with improved channel database management using JSON format and enhanced fuzzy matching for more accurate EPG assignments.

### Key Features

#### Intelligent Matching & Automation
- **Auto-Match EPG**: Automatically match and assign EPG to channels based on OTA and regular channel data with intelligent fuzzy matching
- **Scan & Heal**: Automatically find broken EPG assignments and replace them with working alternatives from other sources
- **Enhanced Fuzzy Matching**: Integrated dedicated fuzzy matcher module for improved accuracy
- **Preview Mode**: Dry run auto-matching and healing to review results before applying changes
- **EPG Source Prioritization**: Match EPG sources in the order you specify - first listed gets highest priority
- **EPG Source Validation**: Validates EPG source names and warns about typos with helpful suggestions
- **Intelligent Replacement Matching**: Weighted scoring system prioritizes callsign, location, and network matches

#### Smart Filtering & Targeting
- **Channel Profile Support**: Limit scanning and matching to specific Channel Profiles
- **EPG Source Filtering**: Target specific EPG sources for matching operations
- **Group Filtering**: Scan specific channel groups or exclude certain groups
- **Smart Scanning**: Identifies channels with EPG assignments but no program data in configurable time window

#### Powerful Management Tools
- **Automated EPG Removal**: Remove EPG assignments from channels with missing data
- **Regex-Based Removal**: Remove EPG assignments matching patterns within specified groups
- **Bulk Operations**: Remove all EPG assignments from entire channel groups at once
- **Channel Tagging**: Add configurable suffix to channels with missing EPG data
- **Hidden Channel Cleanup**: Remove EPG data from disabled/hidden channels in profiles

#### User Experience
- **Emoji-Enhanced UI**: All settings fields include helpful emojis for easy identification
- **Detailed Reports**: Export comprehensive CSV reports with channel details (all files include plugin name)
- **Analytics**: View breakdowns by EPG source and channel groups
- **Smart Notifications**: Long file lists show concise summaries for small popup windows
- **GUI Refresh**: Automatic interface updates after bulk operations
- **Better Logging**: All log messages prefixed with plugin name for easier debugging
- **Fast Results**: Complete scans in seconds, not hours

## Installation

1. Log on to Dispatcharr's web UI
2. Go to **Plugins**
3. In the upper right, click **Import Plugin** and upload the zip file
4. Select 'Upload'
5. Select 'Enable' and then press Done

## How to Use

### Step-by-Step Workflow

1. **Configure Settings**
   - Navigate to **Settings** → **Plugins** in your Dispatcharr web UI
   - Find **EPG Janitor** in the plugins list
   - Enter your **Dispatcharr URL** (e.g., http://127.0.0.1:9191)
   - Enter your **Dispatcharr Admin Username** and **Password**
   - Set **Hours to Check Ahead** (default: 12)
   - Optionally specify **Channel Profile Name** to limit operations to specific profiles
   - Optionally specify **EPG Sources to Match** for targeted matching
   - Optionally specify **Channel Groups** (comma-separated, or leave empty for all groups)
   - Optionally specify **Ignore Groups** to exclude certain groups (cannot be used with Channel Groups)
   - Configure **Bad EPG Suffix** (default: " [BadEPG]")
   - Click **Save Settings**

2. **Auto-Match EPG**
   - Click **Run** on **Preview Auto-Match (Dry Run)** to see what matches would be made
   - Review the exported CSV file to verify matches are accurate
   - Click **Run** on **Apply Auto-Match EPG Assignments** to apply the matches
   - Confirm the action when prompted

3. **Scan for Issues**
   - Click **Run** on **Scan for Missing Program Data**
   - Review the scan results showing channels with missing program data

4. **Auto-Heal Broken Channels** (New!)
   - Click **Run** on **Scan & Heal (Dry Run)** to preview automatic fixes
   - Review the exported CSV file to see proposed replacements with confidence scores
   - Click **Run** on **Scan & Heal (Apply Changes)** to automatically fix high-confidence matches
   - Only replacements meeting the confidence threshold will be applied (default: 95%)

5. **Take Manual Action**
   - Use **Remove EPG Assignments** to remove EPG from channels found in the last scan
   - Use **Add Bad EPG Suffix** to tag problematic channels for easy identification
   - Use **Remove EPG by REGEX** to remove EPG assignments matching a pattern
   - Use **Remove ALL EPG from Groups** to clear EPG from entire channel groups

6. **Export and Analyze**
   - Use **Export Results to CSV** to download detailed results
   - Use **View Last Results** to see summary of last scan

## Settings Reference

> **Note:** All settings fields now include helpful emojis for easy identification in the UI.

### Authentication Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| 🌐 Dispatcharr URL | string | - | Full URL of your Dispatcharr instance (from browser address bar). **Required** |
| 👤 Dispatcharr Admin Username | string | - | Your admin username for API access. **Required** |
| 🔑 Dispatcharr Admin Password | password | - | Your admin password for API access. **Required** |

### Channel Selection Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| 📺 Channel Profile Name | string | - | Only scan/match channels visible in this Channel Profile (leave blank for all) |
| 📡 EPG Sources to Match | string | - | Comma-separated EPG source names to search within (leave blank for all). **Names are validated** and invalid names will trigger a warning with available options. If multiple sources are specified, **matching is prioritized** in the order entered (first = highest priority) |

### Scan Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| ⏰ Hours to Check Ahead | number | 12 | How many hours into the future to check for missing EPG data (1-168) |
| 📂 Channel Groups | string | - | Comma-separated group names to scan/modify, empty = all groups (cannot use with Ignore Groups) |
| 🚫 Ignore Groups | string | - | Comma-separated group names to exclude from operations (cannot use with Channel Groups) |

### EPG Management Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| 🔧 EPG Name REGEX to Remove | string | - | Regular expression to match EPG channel names for removal |
| 🏷️ Bad EPG Suffix | string | " [BadEPG]" | Suffix to add to channels with missing EPG data |

### Scan & Heal Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| 🩹 Heal: Fallback EPG Sources | string | - | Priority-ordered EPG sources to search when healing broken channels. If blank, uses "EPG Sources to Match" setting. First listed = highest priority |
| 🩹 Heal: Auto-Apply Confidence Threshold | number | 95 | Minimum confidence score (0-100) required for automatic EPG replacement during "Scan & Heal (Apply Changes)". Prevents low-quality matches |

## Output Data

### Scan Results Summary
- Total channels with EPG assignments
- Number of channels missing program data
- Breakdown by EPG source
- Breakdown by channel group
- List of first 10 problematic channels (with group and EPG info)

### Auto-Match Results
- Total channels processed
- Number of successful matches
- Match confidence scores
- Matching strategy used (exact, fuzzy, callsign, etc.)
- Preview export for verification before applying

### CSV Export Fields

**Standard Scan Results:**

| Field | Description | Example |
|-------|-------------|---------|
| channel_id | Internal Dispatcharr channel ID | 123 |
| channel_name | Display name of the channel | ESPN HD |
| channel_number | Channel number (if assigned) | 101.0 |
| channel_group | Channel group name | Sports |
| epg_channel_id | TVG ID from EPG data | espn.us |
| epg_channel_name | Name from EPG data | ESPN |
| epg_source | EPG source name | XMLTV Sports Guide |
| scanned_at | Timestamp of scan | 2025-01-15T10:30:00 |

**Auto-Match Results (additional fields):**

| Field | Description | Example |
|-------|-------------|---------|
| match_confidence | Match confidence percentage | 95.5 |
| match_strategy | Strategy used for matching | fuzzy_match |

**Scan & Heal Results (additional fields):**

| Field | Description | Example |
|-------|-------------|---------|
| original_epg_name | Original broken EPG name | XMLTV LA - KABC |
| original_epg_source | Original broken EPG source | EPGShare Locals |
| new_epg_name | Replacement EPG name | WKBW-DT |
| match_confidence | Replacement confidence score (0-100) | 80 |
| match_method | Matching components used | Callsign + State |
| status | Healing status | HEALED, REPLACEMENT_PREVIEW, or NO_REPLACEMENT_FOUND |

### CSV Export Location
CSV files are exported to: `/data/exports/epg_janitor_results_YYYYMMDD_HHMMSS.csv`

## Action Reference

### Auto-Match Actions
- **Preview Auto-Match (Dry Run)**: Preview EPG auto-matching results without applying changes. Results exported to CSV.
- **Apply Auto-Match EPG Assignments**: Automatically match and assign EPG to channels based on OTA and channel data (requires confirmation)

### Core Actions
- **Scan for Missing Program Data**: Find channels with EPG assignments but no program data
- **Scan & Heal (Dry Run)**: Find broken EPG assignments and search for working replacements. Preview results without applying changes. Results exported to CSV
- **Scan & Heal (Apply Changes)**: Automatically find and fix broken EPG assignments by replacing them with validated working alternatives from other sources (requires confirmation)
- **View Last Results**: Display summary of the last EPG scan results
- **Export Results to CSV**: Export the last scan results to a CSV file

### EPG Management Actions
- **Remove EPG Assignments**: Remove EPG from channels found with missing data in last scan (requires confirmation)
- **Remove EPG Assignments matching REGEX within Group(s)**: Remove EPG from channels where EPG name matches the configured REGEX pattern (requires confirmation)
- **Remove ALL EPG Assignments from Group(s)**: Remove EPG from all channels in specified groups (requires confirmation)
- **Add Bad EPG Suffix to Channels**: Add configured suffix to channels with missing EPG data (requires confirmation)

### Utility Actions
- **Clear CSV Exports**: Delete all old CSV export files to free up disk space

## Understanding the Results

EPG Janitor identifies channels that fall into this specific scenario:
- Channel has epg_data assigned (not null)
- The assigned EPG data has no ProgramData records for the specified timeframe
- These channels will show "No Program Information Available" in the TV guide

**Note**: Channels without any EPG assignment get dummy program data and are not flagged by this plugin.

## Auto-Match Technology

### How Auto-Matching Works

EPG Janitor uses a multi-strategy approach to find the best EPG match for each channel:

1. **Exact Match**: Direct match on channel name or TVG ID
2. **Fuzzy Match**: Uses 85% similarity threshold for close matches
3. **Callsign Match**: Matches based on broadcast callsigns (e.g., WABC, KCBS)
4. **Channel Number Match**: Matches based on channel number patterns
5. **OTA Data Match**: Leverages over-the-air channel data when available

### Match Confidence Scores

- **95-100%**: Highly confident match (exact or near-exact)
- **85-94%**: Good match (fuzzy matching with high similarity)
- **70-84%**: Moderate match (may require verification)
- **Below 70%**: Low confidence (review recommended)

### Best Practices for Auto-Matching

1. **Start with Preview**: Always run "Preview Auto-Match (Dry Run)" first
2. **Review CSV**: Check the exported CSV for match confidence and strategy
3. **Test Small Groups**: Try auto-matching on a single channel group first
4. **Use EPG Source Filter**: Narrow down to specific EPG sources for better accuracy
5. **Prioritize Sources**: List EPG sources in order of preference (first = highest priority)
6. **Verify Results**: Check a few channels after applying to ensure correct matches

### EPG Source Prioritization

When you specify multiple EPG sources in the "📡 EPG Sources to Match" field, the plugin prioritizes them in the order you enter:

**Example:** `Gracenote, XMLTV USA, TVGuide`

- **Gracenote** = First priority (checked first for matches)
- **XMLTV USA** = Second priority (checked if no Gracenote match)
- **TVGuide** = Third priority (checked if no previous matches)

**How it works:**
1. Plugin validates all source names (warns about typos)
2. EPG data is filtered and sorted by your priority order
3. During matching, the first match from the highest-priority source is selected
4. Logs show the priority order for transparency

**Benefits:**
- Prefer premium EPG sources over free sources
- Use backup sources when primary sources lack data
- Consistent matching behavior across all channels
- Full control over EPG source selection

## Scan & Heal Technology

### How Scan & Heal Works

Scan & Heal is an intelligent auto-repair feature that finds broken EPG assignments and automatically replaces them with working alternatives:

**6-Step Process:**

1. **Find Broken Channels**: Identifies channels with EPG assignments but no program data
2. **Gather EPG Data**: Collects all available EPG sources (uses "Heal: Fallback EPG Sources" or "EPG Sources to Match")
3. **Hunt for Replacements**: For each broken channel, searches for working alternatives using intelligent matching
4. **Validate Candidates**: Tests potential replacements to verify they have actual program data
5. **Apply Fixes**: Automatically replaces broken EPG assignments (only if confidence ≥ threshold)
6. **Generate Report**: Creates detailed CSV report with all results and confidence scores

### Intelligent Replacement Matching

Scan & Heal uses a weighted scoring system to find the best replacement EPG:

| Match Type | Points | Priority | Example |
|------------|--------|----------|---------|
| **Callsign Match** | 50 | Highest | WABC-DT → WABC-DT |
| **State Match** | 30 | Medium-High | NY → NY |
| **City Match** | 20 | Medium | Buffalo → Buffalo |
| **Network Match** | 10 | Low | ABC → ABC |

**Match Confidence Calculation:**
- Callsign + State + City + Network = 100% (perfect match)
- Callsign + State = 80% (very good match)
- State + Network = 40% (moderate match)
- Network only = 10% (poor match)

**Safety Mechanism:**
- Only replacements with confidence ≥ threshold are automatically applied
- Default threshold: 95% (callsign + state + city, or callsign + state + network)
- Low-confidence matches are flagged as "REPLACEMENT_PREVIEW" in CSV for manual review

### Understanding Scan & Heal Results

**CSV Export Statuses:**

| Status | Meaning | What Happens |
|--------|---------|--------------|
| **HEALED** | High confidence replacement applied | EPG automatically replaced with working alternative |
| **REPLACEMENT_PREVIEW** | Low confidence match found | Match shown in CSV but NOT applied - review and apply manually |
| **NO_REPLACEMENT_FOUND** | No suitable alternative found | No working EPG available in specified sources |

**Why Replacements May Not Be Found:**
1. **Missing Data**: Your EPG sources don't have program data for that specific channel/callsign
2. **Different Market**: Channel is from a market not covered by your EPG sources (e.g., local station from another state)
3. **Source Limitations**: The EPG sources specified in "Heal: Fallback EPG Sources" are too limited

**Best Practices:**
1. **Configure Fallback Sources**: Add multiple diverse EPG sources to "Heal: Fallback EPG Sources"
2. **Start with Dry Run**: Always preview results before applying changes
3. **Review CSV**: Check confidence scores and match methods in the exported CSV
4. **Adjust Threshold**: Lower the confidence threshold (e.g., 85) if you're comfortable with moderate matches
5. **Manual Review**: For "REPLACEMENT_PREVIEW" status channels, manually verify and apply if appropriate

### Example Healing Scenarios

**Scenario 1: Perfect Match (100% confidence)**
- **Original**: ABC - NY Buffalo (WKBW) → "XMLTV LA" (broken, wrong market)
- **Match Found**: WKBW-DT (callsign) + NY (state) + Buffalo (city) + ABC (network) from "Gracenote"
- **Result**: HEALED ✓ (automatically applied)

**Scenario 2: Good Match (80% confidence)**
- **Original**: NBC (WAGT) Augusta, GA → "EPGShare Locals" (broken, no data)
- **Match Found**: WAGT-CD (callsign) + GA (state) + NBC (network) from "TVGuide"
- **Result**: REPLACEMENT_PREVIEW (below 95% threshold, needs manual review)

**Scenario 3: Poor Match (10% confidence)**
- **Original**: ABC - UT Salt Lake City (KTVX) → "EPGShare Locals" (broken, no data)
- **Match Found**: KABC-DT (different callsign) + CA (different state) + Los Angeles (different city) + ABC (network only)
- **Result**: REPLACEMENT_PREVIEW (way below threshold, incorrect match - should NOT be applied)

**Scenario 4: No Match Found**
- **Original**: ABC - WY Casper (KTWO) → "EPGShare Locals" (broken, no data)
- **Match Found**: None (no EPG sources have data for KTWO-DT)
- **Result**: NO_REPLACEMENT_FOUND (add more EPG sources or manual fix required)

## Important Notes

### Recent Improvements

#### Database & Matching Enhancements
- **🔄 Refactored Channel Database**: Now uses JSON format (*_channels.json) for improved maintainability
- **✨ Enhanced Fuzzy Matching**: Integrated dedicated fuzzy_matcher module for more accurate channel matching
- **🎯 EPG Source Prioritization**: Match EPG sources in the order you specify - first listed gets highest priority
- **✅ EPG Source Validation**: Validates EPG source names (case-insensitive), warns about typos, suggests corrections
- **Auto-Match EPG**: Intelligent matching algorithms for automatic EPG assignment

#### User Interface & Experience
- **🎨 Emoji-Enhanced Settings**: All settings fields include helpful emojis for easy identification (🌐 🔑 📺 📡 ⏰ etc.)
- **🎨 Emoji Action Buttons**: All action buttons include visual emojis for better clarity
- **📊 Smart Notifications**: Long file lists show concise summaries to fit small popup windows
- **📝 Better Logging**: All log messages prefixed with "EPG Janitor:" for easier debugging
- **📁 Consistent CSV Naming**: All CSV exports include "epg_janitor_" prefix for easy identification

#### Features & Capabilities
- **🩹 Scan & Heal**: Automatically find and fix broken EPG assignments with intelligent replacement matching
- **🎯 Intelligent Replacement Matching**: Weighted scoring system (callsign: 50pts, state: 30pts, city: 20pts, network: 10pts)
- **🛡️ Safety Mechanism**: Confidence threshold prevents low-quality auto-replacements (default: 95%)
- **Channel Profile Support**: Limit operations to specific Channel Profiles
- **EPG Source Filtering**: Target specific EPG sources for matching with validation
- **Enhanced Frontend Refresh**: Broader UI synchronization after operations
- **🧹 Code Cleanup**: Removed duplicate matching code and legacy file format support

### Plugin Capabilities
- **API Authentication Required**: Requires Dispatcharr URL, username, and password
- **Bulk Operations Available**: Can modify channels directly via the plugin
- **Destructive Actions**: EPG removal and channel renaming operations are permanent and require confirmation
- **Automatic GUI Updates**: Interface refreshes automatically after bulk operations

### Safety Features
- All destructive operations require confirmation dialogs
- Preview mode for auto-matching before applying changes
- Duplicate prevention logic avoids adding existing suffixes
- Sample results shown before applying changes
- Detailed success messages with affected channel counts

## Troubleshooting

### First Step: Restart Container
For any plugin issues, always try restarting the Dispatcharr container first:
```bash
docker restart dispatcharr
```
This resolves most plugin loading, configuration, and caching issues.

### Common Issues

**Frontend not updating after changes**
* Plugin uses WebSocket-based updates for real-time refresh
* If changes are not immediately visible, refresh your browser
* Check logs for "Frontend refresh triggered via WebSocket" message

**Many old CSV export files**
* Use the "Clear CSV Exports" action to delete all old reports
* This will free up disk space in `/data/exports/`

**"Plugin 'epg_janitor' not found" error**
* Log out of Dispatcharr
* Refresh your browser or close and reopen it
* Log back in and try again

**Auto-match not finding good matches**
* Verify EPG sources contain data for your channels
* Try using EPG Source Filter to target specific sources
* Check that channel names in your lineup match EPG channel names reasonably well
* Review the preview CSV to see what matches were attempted

**Scan & Heal not finding replacements or only finding low-confidence matches**
* Check that "Heal: Fallback EPG Sources" includes diverse EPG sources covering your channels
* Verify EPG sources have program data for your specific channel callsigns and markets
* If you see only network matches (10% confidence), your sources likely don't cover those local stations
* Try adding more comprehensive EPG sources (e.g., Gracenote, TVGuide, regional sources)
* For low-confidence matches, review the CSV and manually verify if they're actually correct
* Lower the confidence threshold if you're comfortable manually reviewing moderate matches

### Plugin Not Appearing
- Check plugin files are in the correct location: `/data/plugins/epg_janitor/`
- Verify file permissions are correct
- Restart container: `docker restart dispatcharr`
- Go to Settings → Plugins → Reload Discovery

### Authentication Errors
- Verify Dispatcharr URL is accessible from the browser
- Ensure username and password are correct
- Check user has admin access permissions
- Restart container: `docker restart dispatcharr`

### Settings Not Saving
- Click the "Save Settings" button after making changes
- Refresh the browser page
- Restart container: `docker restart dispatcharr`

### Actions Not Working
- Verify plugin loaded successfully in logs
- Check for JavaScript errors in the browser console
- Ensure you have run a scan before using management actions
- Restart container: `docker restart dispatcharr`

### No Results Found
- Verify channels have EPG data assigned in Dispatcharr
- Check that your EPG sources are actively providing data
- Ensure the time window includes periods where you expect program data
- Try scanning all groups instead of specific ones

### CSV Export Issues
- Ensure `/data/exports/` directory exists and is writable
- Check available disk space
- Verify no permission issues with the Dispatcharr data directory

### Updating the Plugin

To update EPG Janitor:

1. **Remove Old Plugin**
   * Navigate to **Plugins** in Dispatcharr
   * Click the trash icon next to the old EPG Janitor plugin
   * Confirm deletion

2. **Restart Dispatcharr**
   * Log out of Dispatcharr
   * Restart the Docker container:
     ```bash
     docker restart dispatcharr
     ```

3. **Install Updated Plugin**
   * Log back into Dispatcharr
   * Navigate to **Plugins**
   * Click **Import Plugin** and upload the new plugin zip file
   * Enable the plugin after installation

4. **Verify Installation**
   * Check that the plugin appears in the plugin list
   * Reconfigure your settings if needed
   * Run "Preview Auto-Match (Dry Run)" to test the plugin

### Debugging Commands

**Enable Verbose Logging:**
```bash
docker logs dispatcharr | grep -i epg_janitor
```

**Check Plugin Status:**
```bash
docker exec dispatcharr ls -la /data/plugins/epg_janitor/
```

**Verify Plugin Files:**
```bash
docker exec dispatcharr cat /data/plugins/epg_janitor/plugin.py
```

**Check Frontend Refresh:**
```bash
docker logs dispatcharr | grep -i "Frontend refresh"
```

## Limitations

### Plugin Limitations
- **Match Accuracy**: Auto-matching depends on similarity between channel names and EPG data
- **Permanent Operations**: EPG removal and channel renaming cannot be undone
- **Sequential Processing**: Operations are performed one at a time
- **Group Filtering**: REGEX removal only works within specified groups
- **API Dependency**: Requires valid Dispatcharr credentials for bulk operations

### System Limitations
- **Plugin System Constraints**: Limited by the current Dispatcharr plugin API capabilities
- **Memory Usage**: Large channel lineups may require more processing time
- **EPG Source Dependencies**: Results depend on EPG source data quality and availability

## Contributing

Found a bug or want to suggest improvements? Please open an issue or submit a pull request.
