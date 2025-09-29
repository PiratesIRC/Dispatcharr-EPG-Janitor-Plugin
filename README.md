# EPG Janitor - Dispatcharr Plugin

**TIRED of channels showing "No Program Information Available"? FRUSTRATED with missing EPG data ruining your viewing experience?**

**Introducing EPG Janitor** - the POWERFUL Dispatcharr plugin that IDENTIFIES problematic channels in SECONDS!

## What Does EPG Janitor Do?

EPG Janitor scans your Dispatcharr channel lineup to identify channels that have EPG assignments but are missing program data, causing them to display "No Program Information Available" in your TV guide. Version 0.2 adds the ability to automatically remove problematic EPG assignments and tag channels for easy identification.

### Key Features

- **Smart Scanning**: Identifies channels with EPG assignments but no program data in the next 12 hours (configurable)
- **Group Filtering**: Scan specific channel groups or all channels at once
- **Automated EPG Removal**: Remove EPG assignments from channels with missing data
- **Regex-Based Removal**: Remove EPG assignments matching patterns within specified groups
- **Bulk Operations**: Remove all EPG assignments from entire channel groups at once
- **Channel Tagging**: Add configurable suffix to channels with missing EPG data
- **Detailed Reports**: Export comprehensive CSV reports with channel details
- **Analytics**: View breakdowns by EPG source and channel groups
- **GUI Refresh**: Automatic interface updates after bulk operations
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
   - Optionally specify **Channel Groups** (comma-separated, or leave empty for all groups)
   - Configure **Bad EPG Suffix** (default: " [BadEPG]")
   - Click **Save Settings**

2. **Scan for Issues**
   - Click **Run** on **Scan for Missing EPG**
   - Review the scan results showing channels with missing program data

3. **Take Action**
   - Use **Remove EPG Assignments** to remove EPG from channels found in the last scan
   - Use **Add Bad EPG Suffix** to tag problematic channels for easy identification
   - Use **Remove EPG by REGEX** to remove EPG assignments matching a pattern
   - Use **Remove ALL EPG from Groups** to clear EPG from entire channel groups

4. **Export and Analyze**
   - Use **Export Results to CSV** to download detailed results
   - Use **View Last Results** to see summary of last scan

## Settings Reference

### Authentication Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| Dispatcharr URL | string | - | Full URL of your Dispatcharr instance (from browser address bar) |
| Dispatcharr Admin Username | string | - | Your admin username for API access |
| Dispatcharr Admin Password | password | - | Your admin password for API access |

### Scan Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| Hours to Check Ahead | number | 12 | How many hours into the future to check for missing EPG data (1-168) |
| Channel Groups | string | - | Comma-separated group names to scan/modify, empty = all groups |

### EPG Management Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| EPG Name REGEX to Remove | string | - | Regular expression to match EPG channel names for removal |
| Bad EPG Suffix | string | " [BadEPG]" | Suffix to add to channels with missing EPG data |

## Output Data

### Scan Results Summary
- Total channels with EPG assignments
- Number of channels missing program data
- Breakdown by EPG source
- Breakdown by channel group
- List of first 10 problematic channels (with group and EPG info)

### CSV Export Fields

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

### CSV Export Location
CSV files are exported to: `/data/exports/epg_janitor_results_YYYYMMDD_HHMMSS.csv`

## Action Reference

### Core Actions
- **Scan for Missing EPG**: Find channels with EPG assignments but no program data
- **View Last Results**: Display summary of the last EPG scan results
- **Export Results to CSV**: Export the last scan results to a CSV file

### EPG Management Actions
- **Remove EPG Assignments**: Remove EPG from channels found with missing data in last scan (requires confirmation)
- **Remove EPG Assignments matching REGEX within Group(s)**: Remove EPG from channels where EPG name matches the configured REGEX pattern (requires confirmation)
- **Remove ALL EPG Assignments from Group(s)**: Remove EPG from all channels in specified groups (requires confirmation)
- **Add Bad EPG Suffix to Channels**: Add configured suffix to channels with missing EPG data (requires confirmation)

## Understanding the Results

EPG Janitor identifies channels that fall into this specific scenario:
- Channel has epg_data assigned (not null)
- The assigned EPG data has no ProgramData records for the specified timeframe
- These channels will show "No Program Information Available" in the TV guide

**Note**: Channels without any EPG assignment get dummy program data and are not flagged by this plugin.

## Important Notes

### Version 0.2 Changes
- **API Authentication Required**: Now requires Dispatcharr URL, username, and password
- **Bulk Operations Available**: Can now modify channels directly via the plugin
- **Destructive Actions**: EPG removal and channel renaming operations are permanent and require confirmation
- **Automatic GUI Updates**: Interface refreshes automatically after bulk operations

### Safety Features
- All destructive operations require confirmation dialogs
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

## Limitations

### Current Version (v0.2)
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

## License

This plugin is provided as-is for use with Dispatcharr. Use at your own discretion.

---

*Professional EPG management with automated fixes has never been this EASY!*
