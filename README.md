# EPG Janitor - Dispatcharr Plugin

**TIRED of channels showing "No Program Information Available"? FRUSTRATED with missing EPG data ruining your viewing experience?**

**Introducing EPG Janitor** - the REVOLUTIONARY Dispatcharr plugin that IDENTIFIES problematic channels in SECONDS and helps you take control of your EPG data management!

## 🧹 What Does EPG Janitor Do?

EPG Janitor scans your Dispatcharr channel lineup to identify channels that have EPG assignments but are missing program data, causing them to display "No Program Information Available" in your TV guide.

### Key Features

- **🔍 Smart Scanning**: Identifies channels with EPG assignments but no program data in the next 24 hours (configurable)
- **🎯 Group Filtering**: Scan specific channel groups or all channels at once
- **📊 Detailed Reports**: Export comprehensive CSV reports with channel details
- **📈 Analytics**: View breakdowns by EPG source and channel groups  
- **🔒 Read-Only Safe**: No modifications to your system - information only
- **⚡ Fast Results**: Complete scans in seconds, not hours

## 🚀 Installation

1. Log on to Dispatcharr's web UI
2. Go to **Plugins**
3. In the upper right, click **Import Plugin** and upload the zip file
4. Select 'Upload'
5. Select 'Enable' and then press Done.

## 📋 How to Use

1. Navigate to **Settings** → **Plugins** in your Dispatcharr web UI
2. Find **EPG Janitor** in the plugins list
3. Configure your settings:
   - Set **Hours to Check Ahead** (default: 24)
   - Optionally specify **Channel Groups to Check** (comma-separated, or leave empty for all groups)
4. Click **Save Settings**
5. Run one of the available actions:
   - **Scan for Missing EPG**: Perform the main scan
   - **Export Results to CSV**: Download detailed results
   - **View Last Results**: See summary of last scan

## ⚙️ Settings Reference

### Hours to Check Ahead
- **Type**: Number
- **Default**: 12
- **Description**: How many hours into the future to check for missing EPG data
- **Range**: 1-168 hours (1 week maximum recommended)

### Channel Groups to Check
- **Type**: Text (comma-separated)
- **Default**: Empty (scans all groups)
- **Description**: Specific channel groups to scan
- **Example**: `Sports, News, Entertainment, Movies`
- **Note**: Case-sensitive group names

## 📊 Output Data

### Scan Results Summary
- Total channels with EPG assignments
- Number of channels missing program data
- Breakdown by EPG source
- Breakdown by channel group
- List of first 10 problematic channels (with group and EPG info)

### CSV Export Fields
The CSV file contains the following columns:

| Field | Description | Example |
|-------|-------------|---------|
| `channel_id` | Internal Dispatcharr channel ID | `123` |
| `channel_name` | Display name of the channel | `ESPN HD` |
| `channel_number` | Channel number (if assigned) | `101.0` |
| `channel_group` | Channel group name | `Sports` |
| `epg_channel_id` | TVG ID from EPG data | `espn.us` |
| `epg_channel_name` | Name from EPG data | `ESPN` |
| `epg_source` | EPG source name | `XMLTV Sports Guide` |
| `scanned_at` | Timestamp of scan | `2025-01-15T10:30:00` |

### CSV Export Location
CSV files are exported to: `/data/exports/epg_janitor_results_YYYYMMDD_HHMMSS.csv`

Example: `/data/exports/epg_janitor_results_20250115_103000.csv`

## 📊 CSV Export Fields

The exported CSV includes the following fields:

- `channel_id`: Internal Dispatcharr channel ID
- `channel_name`: Display name of the channel
- `channel_number`: Channel number (if assigned)
- `channel_group`: Channel group name
- `epg_channel_id`: TVG ID from EPG data
- `epg_channel_name`: Name from EPG data
- `epg_source`: EPG source name
- `scanned_at`: Timestamp of when the channel was scanned

## 🤔 Understanding the Results

EPG Janitor identifies channels that fall into this specific scenario:
- Channel has `epg_data` assigned (not null)
- The assigned EPG data has no `ProgramData` records for the specified timeframe
- These channels will show "No Program Information Available" in the TV guide

**Note**: Channels without any EPG assignment get dummy program data and are not flagged by this plugin.

## ⚠️ Important Notes

- **READ ONLY ACCESS**: This plugin only identifies issues - manual intervention required to fix EPG assignments
- **No Modifications**: The plugin does not modify any channel or EPG data
- **Information Only**: Use the results to guide your manual EPG management workflow

## 🔧 Troubleshooting

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

### Settings Not Saving
- Click the "Save Settings" button after making changes
- Refresh the browser page
- Restart container: `docker restart dispatcharr`

### Actions Not Working
- Verify plugin loaded successfully in logs
- Check for JavaScript errors in the browser console
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

### General Plugin Issues
- Always restart the container first: `docker restart dispatcharr`
- Wait 30-60 seconds for full startup
- Refresh the browser page
- Check container logs for errors

### Debugging
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
docker exec dispatcharr cat /data/plugins/epg_janitor/__init__.py
```

## ⚠️ Limitations

### Current Version (v0.1)
- **Read-Only Operation**: Plugin cannot modify EPG assignments or channel data
- **Manual Intervention Required**: All fixes must be done through Dispatcharr's web interface
- **No Bulk Operations**: Each channel must be fixed individually
- **No Automated Scheduling**: Scans must be triggered manually
- **No Real-Time Monitoring**: Plugin does not continuously monitor EPG status

### System Limitations
- **Plugin System Constraints**: Limited by the current Dispatcharr plugin API capabilities
- **Memory Usage**: Large channel lineups may require more processing time
- **EPG Source Dependencies**: Results depend on EPG source data quality and availability

### Future Enhancements (Pending Plugin System Development)
- Automated EPG assignment and correction
- Bulk operations for multiple channels
- Scheduled scanning with notifications  
- Direct EPG source validation
- Real-time monitoring capabilities

## 🤝 Contributing

Found a bug or want to suggest improvements? Please open an issue or submit a pull request.

## 📄 License

This plugin is provided as-is for use with Dispatcharr. Use at your own discretion.

---

**Don't let missing EPG data ruin another viewing session - Get EPG Janitor TODAY and take control of your channel guide!**

*Professional EPG management has never been this EASY!*
