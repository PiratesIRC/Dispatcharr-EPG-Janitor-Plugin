# IPTV Checker - Dispatcharr Plugin

**TIRED of dead IPTV streams cluttering your channel lineup? FRUSTRATED with slow framerates and unknown stream quality?**

**Introducing IPTV Checker** - the COMPREHENSIVE Dispatcharr plugin that ANALYZES stream health, IDENTIFIES quality issues, and AUTOMATES channel management in MINUTES!

## 🔍 What Does IPTV Checker Do?

IPTV Checker scans your Dispatcharr channel groups to verify stream availability, analyze technical quality, and automatically organize channels based on their performance. It identifies dead streams, low framerate channels, and categorizes video quality - then provides tools to rename, tag, and relocate problematic channels.

### Key Features

- **🎯 Stream Health Verification**: Test IPTV streams to identify dead or unreachable channels
- **📊 Technical Analysis**: Extract resolution, framerate, and video format from live streams
- **🔄 Smart Retry Logic**: Automatic retry attempts for timeout streams with server-friendly delays
- **📁 Automated Channel Management**: Bulk rename, tag, and move channels based on analysis results
- **⚡ Real-Time Progress Tracking**: Live ETA calculations and completion notifications
- **🎨 Quality-Based Tagging**: Add [4K], [FHD], [HD], [SD] tags based on detected resolution
- **🚀 Background Processing**: Stream checking continues without browser timeout risk
- **📈 Detailed Reporting**: Export comprehensive CSV reports with error categorization

## 🚀 Installation

### System Requirements

This plugin requires **ffmpeg** and **ffprobe** to be installed in the Dispatcharr container for stream analysis.

**Default Locations:**
- **ffprobe:** `/usr/local/bin/ffprobe` (plugin default)
- **ffmpeg:** `/usr/local/bin/ffmpeg`

**Verify Installation:**
```bash
docker exec dispatcharr which ffprobe
docker exec dispatcharr which ffmpeg
```

### Plugin Installation

1. Log on to Dispatcharr's web UI
2. Go to **Plugins**
3. In the upper right, click **Import Plugin** and upload the zip file
4. Select 'Upload'
5. Select 'Enable' and then press Done

## 📋 How to Use

### Step-by-Step Workflow

1. **Configure Authentication**
   - Navigate to **Settings** → **Plugins** in your Dispatcharr web UI
   - Find **IPTV Checker** in the plugins list
   - Enter your **Dispatcharr URL** (e.g., http://127.0.0.1:9191)
   - Enter your **Dispatcharr Username** and **Password**
   - Optionally specify **Groups to Check** (leave empty to check all)
   - Configure retry and timeout settings
   - Click **Save Settings**

2. **Load Channel Groups**
   - Click **Run** on **Load Group(s)**
   - Review available groups and channel counts
   - Note the estimated checking time

3. **Check Streams**
   - Click **Run** on **Process Channels/Streams**
   - Processing runs in the background to prevent browser timeouts
   - Stream checking includes a 3-second delay between checks for better reliability

4. **Monitor Progress**
   - Use **Get Status Update** for real-time progress with ETA
   - Use **View Last Results** for summary when complete
   - Status shows format: "Checking streams X/Y - Z% complete | ETA: N min"

5. **Manage Results**
   - Use channel management actions based on results
   - Export data to CSV with detailed error categorization

## ⚙️ Settings Reference

### Authentication Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| Dispatcharr URL | string | - | Full URL of your Dispatcharr instance (e.g., http://127.0.0.1:9191) |
| Dispatcharr Username | string | - | Username for API authentication |
| Dispatcharr Password | password | - | Password for API authentication |

### Stream Checking Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| Groups to Check | string | - | Comma-separated group names, empty = all groups |
| Connection Timeout | number | 10 | Seconds to wait for stream connection |
| Dead Connection Retries | number | 3 | Number of retry attempts for failed streams |

### Dead Channel Management

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| Dead Channel Prefix | string | - | Prefix to add to dead channel names |
| Dead Channel Suffix | string | - | Suffix to add to dead channel names |
| Move Dead Channels to Group | string | "Graveyard" | Group to move dead channels to |

### Low Framerate Management

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| Low Framerate Prefix | string | - | Prefix for channels under 30fps |
| Low Framerate Suffix | string | " [Slow]" | Suffix for channels under 30fps |
| Move Low Framerate Group | string | "Slow" | Group to move low framerate channels to |

### Video Format Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| Video Format Suffixes | string | "4k, FHD, HD, SD, Unknown" | Formats to add as suffixes |

## 📊 Output Data

### Stream Analysis Results

The plugin provides detailed analysis for each checked stream:

| Field | Description | Example |
|-------|-------------|---------|
| `name` | Channel name from Dispatcharr | `ESPN HD` |
| `group` | Current channel group | `Sports` |
| `status` | Stream availability | `Alive` or `Dead` |
| `resolution` | Video resolution | `1920x1080` |
| `format` | Detected quality format | `FHD` |
| `framerate` | Frames per second (1 decimal) | `29.9` |
| `error_type` | Categorized failure reason | `Connection Timeout` |
| `error_details` | Specific failure information | `Stream unreachable after 3 retries` |
| `checked_at` | Analysis timestamp | `2025-01-15T10:30:00` |

### Quality Detection Rules

- **Low Framerate:** Streams with <30fps
- **Format Detection:**
  - **4K:** 3840x2160+
  - **FHD:** 1920x1080+
  - **HD:** 1280x720+
  - **SD:** Below HD resolution

### File Locations

- **Results:** `/data/iptv_checker_results.json`
- **Loaded Channels:** `/data/iptv_checker_loaded_channels.json`
- **CSV Exports:** `/data/exports/iptv_check_results_YYYYMMDD_HHMMSS.csv`

## 🎬 Action Reference

### Core Actions

- **Load Group(s):** Load channels from specified groups
- **Process Channels/Streams:** Check all loaded streams (background processing)
- **Get Status Update:** Real-time progress with ETA
- **View Last Results:** Summary of completed check

### Channel Management

#### Dead Channel Management
- **Rename Dead Channels:** Apply prefixes/suffixes to dead streams
- **Move Dead Channels to Group:** Relocate dead channels

#### Low Framerate Management (<30fps)
- **Rename Low Framerate Channels:** Apply prefixes/suffixes to slow streams
- **Move Low Framerate Channels to Group:** Relocate slow channels

#### Video Format Management
- **Add Video Format Suffix to Channels:** Apply format tags ([4K], [FHD], [HD], [SD])
- **Remove [] tags:** Clean up channel names by removing text within square brackets

### Data Export

- **View Results Table:** Detailed tabular format
- **Export Results to CSV:** Save analysis data

## 🛠️ Advanced Features

### Smart Retry System
- Timeout streams get retried after processing other streams (not immediately)
- Provides server recovery time between retry attempts
- Improves success rates for intermittent connection issues

### Real-Time Progress Tracking
- **ETA Calculation:** Updates remaining time based on actual processing speed
- **Background Processing:** Stream checking continues without browser timeout risk
- **Completion Notifications:** Clear status when checking finishes

### Performance Optimizations
- **3-Second Delays:** Built-in pause between stream checks for server stability
- **Accurate Time Estimates:** Based on real-world performance data (~8.5 seconds per stream with 20% buffer)
- **Server-Friendly Processing:** Reduces load on IPTV providers

### Smart Channel Management Features
- **Duplicate Prevention:** Avoids adding prefixes/suffixes that already exist
- **Auto Group Creation:** Creates target groups if they do not exist
- **GUI Refresh:** Automatically updates Dispatcharr interface after changes

## 🔧 Troubleshooting

### First Step: Restart Container

For any plugin issues, always try refreshing your browser (F5) and then restarting the Dispatcharr container:

```bash
docker restart dispatcharr
```

This resolves most plugin loading, configuration, and caching issues.

### Common Issues

**"Plugin not found" Errors:**
- Refresh browser page
- Restart Dispatcharr container
- Check plugin folder structure: `/data/plugins/iptv_checker/`

**Authentication Errors:**
- Verify Dispatcharr URL is accessible from the browser
- Ensure username and password are correct
- Check user has appropriate API access permissions
- Restart container: `docker restart dispatcharr`

**"No Groups Found" Error:**
- Check that channel groups exist in Dispatcharr
- Verify group names are spelled correctly (case-sensitive)
- Restart container: `docker restart dispatcharr`

**Stream Check Failures:**
- Increase timeout setting for slow streams
- Adjust retry count for unstable connections
- Check network connectivity from the container
- Restart container: `docker restart dispatcharr`

**Progress Stuck or Not Updating:**
- Use "Get Status Update" for real-time progress
- Stream checking continues in the background even if the browser shows a timeout
- Check container logs for actual processing status
- Restart container: `docker restart dispatcharr`

### Debugging Commands

**Check Plugin Status:**
```bash
docker exec dispatcharr ls -la /data/plugins/iptv_checker/
```

**Monitor Plugin Activity:**
```bash
docker logs dispatcharr | grep -i iptv
```

**Test ffprobe Installation:**
```bash
docker exec dispatcharr /usr/local/bin/ffprobe -version
```

**Check Processing Status:**
```bash
docker logs dispatcharr | tail -20
```

## 🤔 Understanding the Results

### Stream Status Categories

**Alive Streams:**
- Stream is accessible and responding
- Technical analysis successfully completed
- Resolution, framerate, and format detected

**Dead Streams:**
- Stream is unreachable or not responding
- Failed after configured retry attempts
- Includes categorized error types and details

**Low Framerate Streams:**
- Stream is alive but running below 30fps
- May indicate quality issues or encoding problems
- Can be filtered and managed separately

## ⚠️ Important Notes

- **Sequential Processing:** Streams are checked one at a time for server stability (not parallel)
- **Permanent Changes:** Channel management operations (rename, move) are irreversible - backup recommended
- **Time Investment:** Processing time increases with 3-second delays (trade-off for reliability)
- **Authentication Required:** Valid Dispatcharr credentials needed for API access
- **Format Support:** Limited to ffprobe-supported stream formats

## ⚠️ Limitations

### Current Version
- Sequential stream processing only (no parallel checking)
- Requires valid Dispatcharr authentication
- Limited to ffprobe-supported stream formats
- Channel management operations are permanent
- Processing time scales linearly with channel count

### Performance Notes
- **Time Estimates:** Based on approximately 8.5 seconds per stream average with 20% buffer
- **3-Second Delays:** Built-in pause between each stream check for server stability
- **Smart Retries:** Timeout streams are retried after other streams are processed

## 🤝 Contributing

This plugin integrates deeply with Dispatcharr's API and channel management system. When reporting issues:

1. Include Dispatcharr version information
2. Provide relevant container logs
3. Test with small channel groups first
4. Document specific API error messages
5. Note if using "Get Status Update" shows different information than browser display

## 📄 License

This plugin is provided as-is for use with Dispatcharr. Use at your own discretion.

---

*Professional IPTV stream management has never been this EASY!*
