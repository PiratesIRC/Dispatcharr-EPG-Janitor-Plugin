"""
Dispatcharr EPG Janitor Plugin
Scans for channels with EPG assignments but no program data
Auto-matches EPG to channels using OTA and regular channel data
"""

import logging
import json
import csv
import os
import re
import requests
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from django.utils import timezone
from glob import glob

# Django model imports
from apps.channels.models import Channel, ChannelProfileMembership, ChannelProfile
from apps.epg.models import ProgramData

# Import fuzzy matcher module
from .fuzzy_matcher import FuzzyMatcher

# Setup logging using Dispatcharr's format with plugin name prefix
LOGGER = logging.getLogger("plugins.epg_janitor")
if not LOGGER.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(levelname)s %(name)s %(message)s")
    handler.setFormatter(formatter)
    LOGGER.addHandler(handler)
LOGGER.setLevel(logging.INFO)

# Configuration constants
FUZZY_MATCH_THRESHOLD = 85  # Percentage threshold for fuzzy matching (0-100)
PLUGIN_NAME = "EPG Janitor"

class Plugin:
    """Dispatcharr EPG Janitor Plugin"""

    name = "EPG Janitor"
    version = "0.6b"
    description = "Scan for channels with EPG assignments but no program data. Auto-match EPG to channels using OTA and regular channel data."

    # Settings rendered by UI
    _base_fields = [
        {
            "id": "dispatcharr_url",
            "label": "🌐 Dispatcharr URL",
            "type": "string",
            "default": "",
            "placeholder": "http://192.168.1.10:9191",
            "help_text": "URL of your Dispatcharr instance (from your browser's address bar). This is required. Example: http://127.0.0.1:9191",
        },
        {
            "id": "dispatcharr_username",
            "label": "👤 Dispatcharr Admin Username",
            "type": "string",
            "help_text": "Your admin username for the Dispatcharr UI. Required for API access.",
        },
        {
            "id": "dispatcharr_password",
            "label": "🔑 Dispatcharr Admin Password",
            "type": "string",
            "input_type": "password",
            "help_text": "Your admin password for the Dispatcharr UI. Required for API access.",
        },
        {
            "id": "channel_profile_name",
            "label": "📺 Channel Profile Names (Optional, comma-separated)",
            "type": "string",
            "default": "",
            "placeholder": "My Profile, Sports Profile, News Profile",
            "help_text": "Only scan/match channels visible in these Channel Profiles (comma-separated for multiple). Leave blank to scan/match all channels in the group(s).",
        },
        {
            "id": "epg_sources_to_match",
            "label": "📡 EPG Sources to Match (comma-separated)",
            "type": "string",
            "default": "",
            "placeholder": "Gracenote, XMLTV USA, TVGuide",
            "help_text": "Specific EPG source names to search within and match. Leave blank to search all EPG sources. If multiple sources are specified, matching will be prioritized in the order entered.",
        },
        {
            "id": "check_hours",
            "label": "⏰ Hours to Check Ahead",
            "type": "number",
            "default": 12,
            "help_text": "How many hours ahead to check for missing EPG data",
        },
        {
            "id": "selected_groups",
            "label": "📂 Channel Groups (comma-separated)",
            "type": "string",
            "default": "",
            "placeholder": "Sports, News, Entertainment",
            "help_text": "Specific channel groups to check or remove EPG from, or leave empty for all groups. Must be blank if using 'Ignore Groups' below.",
        },
        {
            "id": "ignore_groups",
            "label": "🚫 Ignore Groups (comma-separated)",
            "type": "string",
            "default": "",
            "placeholder": "Premium Sports, Kids",
            "help_text": "Channel groups to exclude from operations. Works on all groups except these. Requires 'Channel Groups' field above to be blank.",
        },
        {
            "id": "epg_regex_to_remove",
            "label": "🔧 EPG Name REGEX to Remove",
            "type": "string",
            "default": "",
            "placeholder": "e.g., (US)$|\\[BACKUP\\]",
            "help_text": "A regular expression to match against EPG channel names within the specified groups. Matching EPG assignments will be removed.",
        },
        {
            "id": "bad_epg_suffix",
            "label": "🏷️ Bad EPG Suffix",
            "type": "string",
            "default": " [BadEPG]",
            "placeholder": " [BadEPG]",
            "help_text": "Suffix to add to channels with missing EPG program data.",
        },
        {
            "id": "remove_epg_with_suffix",
            "label": "🏷️ Also Remove EPG When Adding Suffix",
            "type": "boolean",
            "default": False,
            "help_text": "When enabled, the 'Add Bad EPG Suffix' action will also remove EPG assignments from tagged channels. This helps clean up broken EPG data while keeping channels visible with the suffix for easy identification.",
        },
        {
            "id": "automatch_confidence_threshold",
            "label": "✅ Auto-Match: Apply Confidence Threshold",
            "type": "number",
            "default": 95,
            "help_text": "Minimum confidence score (0-100) required for 'Apply Auto-Match EPG Assignments'. Prevents low-quality matches. Default: 95",
        },
        {
            "id": "heal_fallback_sources",
            "label": "🩹 Heal: Fallback EPG Sources (comma-separated)",
            "type": "string",
            "default": "",
            "placeholder": "XMLTV USA, TVGuide, Gracenote",
            "help_text": "Priority-ordered EPG sources to search when healing broken channels. If blank, uses 'EPG Sources to Match' setting. First listed = highest priority.",
        },
        {
            "id": "heal_confidence_threshold",
            "label": "🩹 Heal: Auto-Apply Confidence Threshold",
            "type": "number",
            "default": 95,
            "help_text": "Minimum confidence score (0-100) required for automatic EPG replacement during 'Scan & Heal (Apply Changes)'. Prevents low-quality matches. Default: 95",
        },
        {
            "id": "ignore_quality_tags",
            "label": "🎯 Ignore Quality Tags",
            "type": "boolean",
            "default": True,
            "help_text": "Ignore quality-related tags during channel matching (e.g., [4K], [HD], [SD], [UHD], [FHD], (Backup)). Default: enabled for better matching.",
        },
        {
            "id": "ignore_regional_tags",
            "label": "🌍 Ignore Regional Tags",
            "type": "boolean",
            "default": True,
            "help_text": "Ignore regional indicator tags during channel matching (e.g., East, West). Default: enabled for better matching.",
        },
        {
            "id": "ignore_geographic_tags",
            "label": "📍 Ignore Geographic Prefixes",
            "type": "boolean",
            "default": True,
            "help_text": "Ignore geographic prefix tags during channel matching (e.g., US:, USA:, US). Default: enabled for better matching.",
        },
        {
            "id": "ignore_misc_tags",
            "label": "🔧 Ignore Miscellaneous Tags",
            "type": "boolean",
            "default": True,
            "help_text": "Ignore miscellaneous tags during channel matching (e.g., (A), (B), (C), (CX), single-letter tags). Default: enabled for better matching.",
        },
    ]
    
    # Actions for Dispatcharr UI
    actions = [
        {
            "id": "validate_settings",
            "label": "✅ Validate Settings",
            "description": "Validate all plugin settings (profiles, groups, API connection, etc.)",
        },
        {
            "id": "preview_auto_match",
            "label": "🔍 Preview Auto-Match (Dry Run)",
            "description": "Preview intelligent EPG auto-matching with program data validation. Uses weighted scoring (callsign, location, network). Results exported to CSV.",
        },
        {
            "id": "apply_auto_match",
            "label": "✅ Apply Auto-Match EPG Assignments",
            "description": "Automatically match and assign EPG to channels using intelligent weighted scoring. Only assigns EPG sources with validated program data.",
            "confirm": { "required": True, "title": "Apply Auto-Match?", "message": "This will automatically assign validated EPG data to channels using intelligent matching. Only EPG sources with program data will be assigned. Existing EPG assignments will be overwritten. Continue?" }
        },
        {
            "id": "scan_missing_epg",
            "label": "🔎 Scan for Missing Program Data",
            "description": "Find channels with EPG assignments but no program data",
        },
        {
            "id": "scan_and_heal_dry_run",
            "label": "❤️‍🩹 Scan & Heal (Dry Run)",
            "description": "Find broken EPG assignments and search for working replacements. Preview results without applying changes. Results exported to CSV.",
        },
        {
            "id": "scan_and_heal_apply",
            "label": "🚀 Scan & Heal (Apply Changes)",
            "description": "Automatically find and fix broken EPG assignments by searching for working replacements from other sources",
            "confirm": { "required": True, "title": "Apply Scan & Heal?", "message": "This will automatically replace broken EPG assignments with validated working alternatives. Only replacements with confidence ≥ threshold will be applied. Continue?" }
        },
        {
            "id": "export_results",
            "label": "📊 Export Results to CSV",
            "description": "Export the last scan results to a CSV file",
        },
        {
            "id": "get_summary",
            "label": "📋 View Last Results",
            "description": "Display summary of the last EPG scan results",
        },
        {
            "id": "remove_epg_assignments",
            "label": "🗑️ Remove EPG Assignments",
            "description": "Remove EPG assignments from channels that were found missing program data in the last scan",
            "confirm": { "required": True, "title": "Remove EPG Assignments?", "message": "This will remove EPG assignments from channels with missing program data. This action is irreversible. Continue?" }
        },
        {
            "id": "remove_epg_by_regex",
            "label": "🔧 Remove EPG Assignments matching REGEX within Group(s)",
            "description": "Removes EPG from channels in the specified groups if the EPG name matches the REGEX.",
            "confirm": { "required": True, "title": "Remove EPG Assignments by REGEX?", "message": "This will remove EPG assignments from channels in the specified groups where the EPG name matches the REGEX. This action is irreversible. Continue?" }
        },
        {
            "id": "remove_all_epg_from_groups",
            "label": "⚠️ Remove ALL EPG Assignments from Group(s)",
            "description": "Removes EPG from all channels in the group(s) specified in 'Channel Groups' or all except 'Ignore Groups'",
            "confirm": { "required": True, "title": "Remove ALL EPG Assignments?", "message": "This will remove EPG assignments from ALL channels in the specified groups, regardless of whether they have program data. This action is irreversible. Continue?" }
        },
        {
            "id": "add_bad_epg_suffix",
            "label": "🏷️ Add Bad EPG Suffix to Channels",
            "description": "Add suffix to channels that were found missing program data in the last scan. Optionally also removes their EPG assignments (configurable in settings)",
            "confirm": { "required": True, "title": "Add Bad EPG Suffix?", "message": "This will add the configured suffix to channels with missing EPG data. If enabled in settings, this will also remove their EPG assignments. This action is irreversible. Continue?" }
        },
        {
            "id": "remove_epg_from_hidden",
            "label": "👻 Remove EPG from Hidden Channels",
            "description": "Remove all EPG data from channels that are disabled/hidden in the selected profile. Results exported to CSV.",
            "confirm": { "required": True, "title": "Remove EPG Data?", "message": "This will permanently delete all EPG data for channels that are currently hidden/disabled in the selected profile. This action cannot be undone. Continue?" }
        },
        {
            "id": "clear_csv_exports",
            "label": "🧹 Clear CSV Exports",
            "description": "Delete all CSV export files created by this plugin",
            "confirm": { "required": True, "title": "Delete All CSV Exports?", "message": "This will permanently delete all CSV files created by EPG Janitor. This action cannot be undone. Continue?" }
        },
    ]

    @property
    def fields(self):
        """Dynamically generate settings fields including channel database selection."""
        # Check for version updates (with caching)
        version_info = {'message': f"Current version: {self.version}", 'status': 'unknown'}
        try:
            version_info = self._check_version_update()
        except Exception as e:
            LOGGER.debug(f"{PLUGIN_NAME}: Error checking version update: {e}")

        # Start with empty list
        fields_list = []

        # Add dynamic channel database boolean fields
        try:
            databases = self._get_channel_databases()

            if databases:
                # Determine default state for databases
                # If only one database exists, enable it by default
                # Otherwise, only enable US database by default
                single_database = len(databases) == 1

                # Create individual boolean fields for each database
                for db in databases:
                    # Default to True if: single database OR it's the US database
                    default_enabled = single_database or db['id'].upper() == 'US'

                    db_field = {
                        "id": f"enable_db_{db['id']}",
                        "label": f"📚 {db['label']}",
                        "type": "boolean",
                        "default": default_enabled,
                        "help_text": f"Enable {db['label']} channel database for matching operations."
                    }
                    fields_list.append(db_field)
            else:
                # Show warning if no databases found
                no_db_field = {
                    "id": "channel_database_warning",
                    "label": "📚 Channel Databases",
                    "type": "info",
                    "value": "⚠️ No channel databases found. Please ensure *_channels.json files exist in the plugin directory."
                }
                fields_list.append(no_db_field)

        except Exception as e:
            LOGGER.warning(f"{PLUGIN_NAME}: Error loading channel databases for settings: {e}")
            error_db_field = {
                "id": "channel_database_error",
                "label": "📚 Channel Databases",
                "type": "info",
                "value": f"⚠️ Error loading channel databases: {e}"
            }
            fields_list.append(error_db_field)

        # Add all base fields with version info in the first field's label
        base_fields_copy = []
        for i, field in enumerate(self._base_fields):
            field_copy = field.copy()
            # Add version info to the first field's label
            if i == 0:
                field_copy["label"] = f"{field['label']} [{version_info['message']}]"
            base_fields_copy.append(field_copy)

        fields_list.extend(base_fields_copy)

        return fields_list

    def __init__(self):
        self.results_file = "/data/epg_janitor_results.json"
        self.automatch_preview_file = "/data/epg_automatch_preview.csv"
        self.version_check_cache_file = "/data/epg_janitor_version_check.json"
        self.token_cache_file = "/data/epg_janitor_token_cache.json"
        self.last_results = []
        self.scan_progress = {"current": 0, "total": 0, "status": "idle", "start_time": None}
        self.pending_status_message = None
        self.completion_message = None

        # Initialize fuzzy matcher with channel databases
        # Note: Category settings will be configured per-run based on user settings
        plugin_dir = os.path.dirname(__file__)
        self.fuzzy_matcher = FuzzyMatcher(
            plugin_dir=plugin_dir,
            match_threshold=FUZZY_MATCH_THRESHOLD,
            logger=LOGGER
        )

        LOGGER.info(f"{PLUGIN_NAME}: Plugin v{self.version} initialized")

    def _get_channel_databases(self):
        """
        Scan the plugin directory for available channel database files.
        Returns a list of dictionaries with database information.
        """
        databases = []
        plugin_dir = os.path.dirname(__file__)
        pattern = os.path.join(plugin_dir, "*_channels.json")
        channel_files = glob(pattern)

        for channel_file in sorted(channel_files):
            try:
                filename = os.path.basename(channel_file)
                # Extract country code from filename (e.g., "US" from "US_channels.json")
                country_code = filename.replace('_channels.json', '')

                # Read the JSON file to get metadata (with backwards compatibility)
                with open(channel_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                    # Backwards compatibility: handle missing metadata fields
                    country_name = data.get('country_name')
                    version = data.get('version')

                    # If country_name is missing, use filename as fallback
                    if country_name:
                        if version:
                            label = f"{country_code} - {country_name} (v{version})"
                        else:
                            label = f"{country_code} - {country_name}"
                    else:
                        # Fallback: show filename when metadata is missing
                        label = f"{filename}"

                databases.append({
                    'id': country_code,
                    'label': label,
                    'filename': filename
                })
            except Exception as e:
                LOGGER.warning(f"Error reading channel database {channel_file}: {e}")

        return databases

    def _get_latest_version(self, owner, repo):
        """
        Fetches the latest release tag name from GitHub using only Python's standard library.

        Args:
            owner (str): GitHub repository owner
            repo (str): GitHub repository name

        Returns:
            str: Latest version tag or error message
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"

        # Add a user-agent to avoid potential 403 Forbidden errors
        headers = {
            'User-Agent': 'Dispatcharr-Plugin-Version-Checker'
        }

        try:
            # Create a request object with headers
            req = urllib.request.Request(url, headers=headers)

            # Make the request and open the URL with a timeout
            with urllib.request.urlopen(req, timeout=5) as response:
                # Read the response and decode it as UTF-8
                data = response.read().decode('utf-8')

                # Parse the JSON string
                json_data = json.loads(data)

                # Get the tag name
                latest_version = json_data.get("tag_name")

                if latest_version:
                    return latest_version
                else:
                    return None

        except urllib.error.HTTPError as http_err:
            if http_err.code == 404:
                LOGGER.debug(f"{PLUGIN_NAME}: GitHub repo not found or has no releases: {http_err}")
                return None
            else:
                LOGGER.debug(f"{PLUGIN_NAME}: HTTP error checking version: {http_err.code}")
                return None
        except Exception as e:
            # Catch other errors like timeouts
            LOGGER.debug(f"{PLUGIN_NAME}: Error checking version: {str(e)}")
            return None

    def _load_version_check_cache(self):
        """
        Load version check cache from file.
        Returns: cache dict or None
        """
        try:
            if os.path.exists(self.version_check_cache_file):
                with open(self.version_check_cache_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            LOGGER.warning(f"{PLUGIN_NAME}: Error loading version check cache: {e}")
        return None

    def _save_version_check_cache(self, cache_data):
        """
        Save version check cache to file.
        """
        try:
            os.makedirs(os.path.dirname(self.version_check_cache_file), exist_ok=True)
            with open(self.version_check_cache_file, 'w') as f:
                json.dump(cache_data, f)
        except Exception as e:
            LOGGER.warning(f"{PLUGIN_NAME}: Error saving version check cache: {e}")

    def _should_check_version(self):
        """
        Determines if we should check for a new version.
        Checks once per day or when the plugin version has changed.
        Returns: (should_check: bool, cached_info: dict or None)
        """
        cache = self._load_version_check_cache()

        if not cache:
            return True, None

        try:
            last_check_timestamp = cache.get("timestamp")
            last_plugin_version = cache.get("plugin_version")
            cached_info = cache.get("version_info")

            # If plugin version changed, check again
            if last_plugin_version != self.version:
                return True, None

            # Check if 24 hours have passed
            current_time = time.time()
            hours_passed = (current_time - last_check_timestamp) / 3600

            if hours_passed >= 24:
                return True, None

            # Use cached info
            return False, cached_info

        except Exception as e:
            LOGGER.warning(f"{PLUGIN_NAME}: Error parsing version check cache: {e}")
            return True, None

    def _check_version_update(self):
        """
        Checks version against GitHub and returns version info dict.
        Saves the result to cache file.
        Returns: dict with 'message' and 'status' keys
        """
        # Check if we should perform a version check
        should_check, cached_info = self._should_check_version()

        if not should_check and cached_info:
            return cached_info

        # Perform version check
        latest_version = self._get_latest_version("PiratesIRC", "Dispatcharr-EPG-Janitor-Plugin")

        current_time = time.time()

        if latest_version is None:
            version_info = {
                'message': f"v{self.version} (update check failed)",
                'status': 'error'
            }
            cache_data = {
                "timestamp": current_time,
                "plugin_version": self.version,
                "latest_version": None,
                "version_info": version_info
            }
            self._save_version_check_cache(cache_data)
            return version_info

        # Remove 'v' prefix if present for comparison
        current_clean = self.version.lstrip('v')
        latest_clean = latest_version.lstrip('v')

        if current_clean == latest_clean:
            version_info = {
                'message': f"v{self.version} (up to date)",
                'status': 'current'
            }
        else:
            # Try to compare versions to see if update is newer
            try:
                # Simple version comparison (works for X.Y format)
                current_parts = [int(x) for x in current_clean.split('.')]
                latest_parts = [int(x) for x in latest_clean.split('.')]

                if latest_parts > current_parts:
                    version_info = {
                        'message': f"v{self.version} (update available: {latest_version})",
                        'status': 'outdated'
                    }
                else:
                    version_info = {
                        'message': f"v{self.version} (up to date)",
                        'status': 'current'
                    }
            except:
                # If version comparison fails, just show both versions
                version_info = {
                    'message': f"v{self.version} (latest: {latest_version})",
                    'status': 'unknown'
                }

        cache_data = {
            "timestamp": current_time,
            "plugin_version": self.version,
            "latest_version": latest_version,
            "version_info": version_info
        }
        self._save_version_check_cache(cache_data)
        return version_info

    def _load_token_cache(self):
        """
        Load API token cache from file.
        Returns: cache dict or None
        """
        try:
            if os.path.exists(self.token_cache_file):
                with open(self.token_cache_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            LOGGER.warning(f"{PLUGIN_NAME}: Error loading token cache: {e}")
        return None

    def _save_token_cache(self, cache_data):
        """
        Save API token cache to file.
        """
        try:
            os.makedirs(os.path.dirname(self.token_cache_file), exist_ok=True)
            with open(self.token_cache_file, 'w') as f:
                json.dump(cache_data, f)
        except Exception as e:
            LOGGER.warning(f"{PLUGIN_NAME}: Error saving token cache: {e}")

    def _is_token_valid(self, cache, settings):
        """
        Check if the cached token is still valid.

        Args:
            cache: Token cache dictionary
            settings: Current plugin settings

        Returns:
            (is_valid: bool, token: str or None)
        """
        if not cache:
            return False, None

        try:
            cached_token = cache.get("token")
            cache_timestamp = cache.get("timestamp")
            cached_url = cache.get("dispatcharr_url")
            cached_username = cache.get("username")

            if not all([cached_token, cache_timestamp, cached_url, cached_username]):
                return False, None

            # Check if credentials/URL have changed
            current_url = settings.get("dispatcharr_url", "").strip().rstrip('/')
            current_username = settings.get("dispatcharr_username", "")

            if cached_url != current_url or cached_username != current_username:
                LOGGER.info(f"{PLUGIN_NAME}: Credentials or URL changed, invalidating cached token")
                return False, None

            # Check if token has expired (cache for 50 minutes to be safe - JWT tokens typically last 1 hour)
            current_time = time.time()
            token_age_minutes = (current_time - cache_timestamp) / 60

            if token_age_minutes > 50:
                LOGGER.info(f"{PLUGIN_NAME}: Cached token expired ({token_age_minutes:.1f} minutes old)")
                return False, None

            LOGGER.info(f"{PLUGIN_NAME}: Using cached API token ({token_age_minutes:.1f} minutes old)")
            return True, cached_token

        except Exception as e:
            LOGGER.warning(f"{PLUGIN_NAME}: Error validating token cache: {e}")
            return False, None

    def _search_epg_data(self, matched_name, epg_data_list, logger):
        """
        Search EPG data for the matched name (callsign).
        EPG data list is pre-sorted by priority, so first match is preferred.
        """
        if not matched_name:
            return None

        # Normalize the matched name (callsign) for comparison
        matched_name_upper = matched_name.upper()

        # Try exact match first (respects EPG source priority)
        for epg in epg_data_list:
            epg_name = epg.get('name', '')
            epg_name_upper = epg_name.upper()

            if epg_name_upper == matched_name_upper:
                return epg

        # For callsigns, try matching the base callsign (before the dash)
        # EPG names may have format like "WAGT-CD.us_locals1" or just "WAGT-CD"
        # Since epg_data_list is sorted by priority, find the first match from highest priority source
        best_matches_by_source = {}  # {epg_source_id: (epg, score)}

        for epg in epg_data_list:
            epg_name = epg.get('name', '')
            epg_source_id = epg.get('epg_source')

            # Skip if we already have a match from this source
            if epg_source_id in best_matches_by_source:
                continue

            # Extract base name from EPG (remove anything after dot)
            # e.g., "WAGT-CD.us_locals1" -> "WAGT-CD"
            epg_base_name = epg_name.split('.')[0] if '.' in epg_name else epg_name

            # Extract base callsign (before the dash)
            # e.g., "WAGT-CD" -> "WAGT"
            epg_base_callsign = epg_base_name.split('-')[0] if '-' in epg_base_name else epg_base_name

            # Check if the matched callsign matches the base EPG callsign
            if matched_name_upper == epg_base_callsign.upper():
                # Prefer shorter EPG names (e.g., "WAGT-CD" over "WAGT-CD2")
                score = 100 - len(epg_name)
                best_matches_by_source[epg_source_id] = (epg, score)

        # Return the first match (highest priority source due to pre-sorted list)
        if best_matches_by_source:
            # Get the best match from the first source that had a match
            for epg in epg_data_list:
                epg_source_id = epg.get('epg_source')
                if epg_source_id in best_matches_by_source:
                    return best_matches_by_source[epg_source_id][0]

        # Try fuzzy match if exact fails (respects priority order)
        epg_names = [epg.get('name', '').split('.')[0] for epg in epg_data_list]
        best_match, score = self.fuzzy_matcher.find_best_match(matched_name, epg_names)

        if best_match:
            # Return first EPG that matches (respects priority)
            for epg in epg_data_list:
                if epg.get('name', '').startswith(best_match):
                    return epg

        return None

    def _get_filtered_epg_data(self, token, settings, logger):
        """Fetch and filter EPG data based on settings with validation and prioritization"""
        try:
            # Fetch all EPG data
            all_epg_data = self._get_api_data("/api/epg/epgdata/", token, settings, logger)
            logger.info(f"{PLUGIN_NAME}: Fetched {len(all_epg_data)} EPG data entries")

            # Filter by EPG sources if specified
            epg_sources_str = settings.get("epg_sources_to_match", "").strip()
            if epg_sources_str:
                try:
                    # Get EPG source names to IDs mapping
                    logger.info(f"{PLUGIN_NAME}: Fetching EPG sources for filtering...")
                    epg_sources = self._get_api_data("/api/epg/sources/", token, settings, logger)

                    if not epg_sources:
                        logger.warning(f"{PLUGIN_NAME}: No EPG sources returned from API, skipping source filtering")
                        return all_epg_data

                    # Parse user-entered source names (maintain order for prioritization)
                    source_names_input = [s.strip() for s in epg_sources_str.split(',') if s.strip()]

                    # Get available source names from API
                    available_sources = {src.get('name', '').strip(): src['id'] for src in epg_sources if src.get('name')}
                    available_sources_upper = {name.upper(): (name, src_id) for name, src_id in available_sources.items()}

                    # Validate and match source names (case-insensitive)
                    valid_source_ids = []
                    valid_source_names = []
                    invalid_sources = []

                    for input_name in source_names_input:
                        input_name_upper = input_name.upper()
                        if input_name_upper in available_sources_upper:
                            actual_name, src_id = available_sources_upper[input_name_upper]
                            valid_source_ids.append(src_id)
                            valid_source_names.append(actual_name)
                        else:
                            invalid_sources.append(input_name)

                    # Log validation results
                    if invalid_sources:
                        logger.warning(f"{PLUGIN_NAME}: ⚠️ Invalid EPG source name(s): {', '.join(invalid_sources)}")
                        logger.info(f"{PLUGIN_NAME}: Available EPG sources: {', '.join(sorted(available_sources.keys()))}")

                    if valid_source_ids:
                        # Filter EPG data by valid source IDs
                        filtered_data = [epg for epg in all_epg_data if epg.get('epg_source') in valid_source_ids]

                        # Prioritize by user-specified order
                        # Create a priority map based on the order of valid source IDs
                        source_priority = {src_id: idx for idx, src_id in enumerate(valid_source_ids)}

                        # Sort filtered data by source priority (lower index = higher priority)
                        filtered_data.sort(key=lambda epg: source_priority.get(epg.get('epg_source'), 999))

                        logger.info(f"{PLUGIN_NAME}: ✓ Filtered to {len(filtered_data)} EPG entries from {len(valid_source_ids)} source(s)")
                        logger.info(f"{PLUGIN_NAME}: Priority order: {', '.join(valid_source_names)}")
                        return filtered_data
                    else:
                        logger.warning(f"{PLUGIN_NAME}: No valid EPG sources found in: {epg_sources_str}")
                        logger.info(f"{PLUGIN_NAME}: Proceeding with all EPG data")
                        return all_epg_data

                except Exception as source_error:
                    logger.warning(f"{PLUGIN_NAME}: Error fetching EPG sources, proceeding without source filtering: {source_error}")
                    return all_epg_data

            return all_epg_data

        except Exception as e:
            logger.error(f"{PLUGIN_NAME}: Error fetching EPG data: {e}")
            raise

    def _auto_match_channels(self, settings, logger, dry_run=True):
        """Auto-match EPG to channels"""
        try:
            # Validate channel databases
            if not self.fuzzy_matcher.broadcast_channels and not self.fuzzy_matcher.premium_channels:
                return {"status": "error", "message": "No channel databases found. Please ensure *_channels.json files exist in the plugin directory."}
            
            # Get API token
            token, error = self._get_api_token(settings, logger)
            if error:
                return {"status": "error", "message": error}
            
            # Get filtered EPG data
            logger.info("Fetching EPG data...")
            epg_data_list = self._get_filtered_epg_data(token, settings, logger)
            
            if not epg_data_list:
                return {"status": "error", "message": "No EPG data found. Please check your EPG sources."}
            
            # Get channels to process
            channels_query = Channel.objects.all().select_related('channel_group', 'logo', 'epg_data')
            
            logger.info(f"{PLUGIN_NAME}: Creating initial channels query...")
            
            # Apply group filters
            try:
                logger.info(f"{PLUGIN_NAME}: Starting group filtering...")
                channels_query, group_filter_info, groups_used = self._validate_and_filter_groups(
                    settings, logger, channels_query, token
                )
                logger.info(f"{PLUGIN_NAME}: Group filtering completed. Filter info: {group_filter_info}")
            except ValueError as e:
                logger.error(f"{PLUGIN_NAME}: ValueError during group filtering: {e}")
                return {"status": "error", "message": str(e)}
            except Exception as e:
                logger.error(f"{PLUGIN_NAME}: Unexpected error during group filtering: {e}")
                import traceback
                logger.error(f"{PLUGIN_NAME}: Traceback: {traceback.format_exc()}")
                return {"status": "error", "message": f"Error during filtering: {str(e)}"}
            
            logger.info(f"{PLUGIN_NAME}: About to execute channels query...")
            try:
                channels = list(channels_query)
                logger.info(f"{PLUGIN_NAME}: Channels query executed successfully, got {len(channels)} channels")
            except Exception as query_error:
                logger.error(f"{PLUGIN_NAME}: Error executing channels query: {query_error}")
                import traceback
                logger.error(f"{PLUGIN_NAME}: Query error traceback: {traceback.format_exc()}")
                return {"status": "error", "message": f"Database query error: {str(query_error)}"}
            
            total_channels = len(channels)
            
            logger.info(f"{PLUGIN_NAME}: Starting auto-match for {total_channels} channels{group_filter_info}")
            logger.info(f"{PLUGIN_NAME}: Check Dispatcharr logs for detailed progress...")

            # Set up time window for program data validation
            check_hours = settings.get("check_hours", 12)
            automatch_confidence_threshold = settings.get("automatch_confidence_threshold", 95)
            now = timezone.now()
            end_time = now + timedelta(hours=check_hours)
            logger.info(f"{PLUGIN_NAME}: Validating EPG matches have program data for next {check_hours} hours")
            logger.info(f"{PLUGIN_NAME}: Using confidence threshold: {automatch_confidence_threshold}%")

            # Initialize progress
            self.scan_progress = {"current": 0, "total": total_channels, "status": "running", "start_time": time.time()}

            match_results = []
            matched_count = 0
            validated_count = 0

            # Process each channel
            for i, channel in enumerate(channels):
                self.scan_progress["current"] = i + 1
                progress_pct = int((i + 1) / total_channels * 100)

                # Log progress every 10 channels or at completion
                if (i + 1) % 10 == 0 or (i + 1) == total_channels:
                    logger.info(f"{PLUGIN_NAME}: Auto-match progress: {progress_pct}% ({i + 1}/{total_channels} channels processed, {validated_count} validated)")

                # Use intelligent weighted scoring with program data validation
                epg_match, confidence_score, match_method = self._find_best_epg_match(
                    channel.name,
                    epg_data_list,
                    now,
                    end_time,
                    logger,
                    exclude_epg_id=None
                )

                # Check if match meets confidence threshold
                meets_threshold = epg_match and confidence_score >= automatch_confidence_threshold

                if epg_match:
                    matched_count += 1
                    if meets_threshold:
                        validated_count += 1
                        if (i + 1) % 50 == 0:
                            logger.info(f"{PLUGIN_NAME}: Validated matches so far: {validated_count} channels")

                # Extract callsign for reporting
                extracted_callsign = self.fuzzy_matcher.extract_callsign(channel.name)

                # Store result
                result = {
                    "channel_id": channel.id,
                    "channel_name": channel.name,
                    "channel_number": float(channel.channel_number) if channel.channel_number else None,
                    "channel_group": channel.channel_group.name if channel.channel_group else "No Group",
                    "match_method": match_method or "None",
                    "confidence_score": confidence_score if confidence_score else 0,
                    "extracted_callsign": extracted_callsign or "N/A",
                    "epg_source_name": None,
                    "epg_data_id": None,
                    "epg_channel_name": None,
                    "current_epg_id": channel.epg_data.id if channel.epg_data else None,
                    "current_epg_name": channel.epg_data.name if channel.epg_data else None,
                    "has_program_data": "Yes" if meets_threshold else "No"
                }

                if meets_threshold:
                    # Get EPG source name
                    epg_source_id = epg_match.get('epg_source')
                    epg_source_name = None
                    if epg_source_id:
                        try:
                            epg_sources = self._get_api_data("/api/epg/sources/", token, settings, logger)
                            for src in epg_sources:
                                if src['id'] == epg_source_id:
                                    epg_source_name = src['name']
                                    break
                        except:
                            pass

                    result["epg_source_name"] = epg_source_name
                    result["epg_data_id"] = epg_match.get('id')
                    result["epg_channel_name"] = epg_match.get('name')

                match_results.append(result)
            
            # Mark scan as complete
            self.scan_progress['status'] = 'idle'
            
            # Calculate different types of matches
            callsigns_extracted = sum(1 for r in match_results if r['extracted_callsign'] != 'N/A')
            epg_found = sum(1 for r in match_results if r['epg_data_id'] is not None)
            validated_matches = sum(1 for r in match_results if r['has_program_data'] == 'Yes')

            logger.info(f"{PLUGIN_NAME}: Auto-match completed: {callsigns_extracted} callsigns extracted, {validated_matches} validated EPG matches (with program data) out of {total_channels} channels")

            # Export results to CSV
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_filename = f"epg_janitor_automatch_{'preview' if dry_run else 'applied'}_{timestamp}.csv"
            csv_filepath = os.path.join("/data/exports", csv_filename)
            os.makedirs("/data/exports", exist_ok=True)

            with open(csv_filepath, 'w', newline='', encoding='utf-8') as csvfile:
                # Write comment header with plugin options
                header_comments = self._generate_csv_header_comments(settings, total_channels)
                for comment_line in header_comments:
                    csvfile.write(comment_line + '\n')

                fieldnames = [
                    'channel_id', 'channel_name', 'channel_number', 'channel_group',
                    'match_method', 'confidence_score', 'extracted_callsign',
                    'epg_source_name', 'epg_data_id', 'epg_channel_name',
                    'current_epg_id', 'current_epg_name', 'has_program_data'
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for result in match_results:
                    writer.writerow(result)
            
            logger.info(f"{PLUGIN_NAME}: Results exported to {csv_filepath}")
            
            # Apply matches if not dry run
            if not dry_run:
                associations = []
                for result in match_results:
                    if result['epg_data_id']:
                        associations.append({
                            'channel_id': int(result['channel_id']),
                            'epg_data_id': int(result['epg_data_id'])
                        })
                
                if associations:
                    logger.info(f"{PLUGIN_NAME}: Applying {len(associations)} EPG assignments...")
                    
                    try:
                        response = self._post_api_data("/api/channels/channels/batch-set-epg/", token, 
                                          {"associations": associations}, settings, logger)
                        
                        channels_updated = response.get('channels_updated', 0)
                        programs_refreshed = response.get('programs_refreshed', 0)
                        
                        if channels_updated == 0:
                            logger.warning(f"{PLUGIN_NAME}: API returned 0 channels updated! Response: {response}")
                            return {"status": "error", "message": f"EPG assignments failed: API updated 0 channels. Check user permissions and EPG data validity."}
                        
                        logger.info(f"{PLUGIN_NAME}: EPG assignments applied successfully: {channels_updated} channels updated, {programs_refreshed} programs refreshed")
                    except Exception as e:
                        logger.error(f"{PLUGIN_NAME}: Failed to apply EPG assignments: {e}")
                        return {"status": "error", "message": f"Failed to apply EPG assignments: {e}"}
                    
                    # Trigger frontend refresh
                    self._trigger_frontend_refresh(settings, logger)
                else:
                    logger.warning(f"{PLUGIN_NAME}: No associations to apply - no channels had valid epg_data_id")
            
            # Build summary message
            mode_text = "Preview" if dry_run else "Applied"

            message_parts = [
                f"Auto-match {mode_text}: {validated_matches}/{total_channels} channels matched with validated EPG data{group_filter_info}",
                f"• Callsigns extracted: {callsigns_extracted}/{total_channels}",
                f"• Validated matches (with program data): {validated_matches}/{total_channels}",
                f"• Time window checked: next {check_hours} hours",
                f"Results exported to: {csv_filepath}",
                "",
                "Match breakdown:"
            ]

            # Count by method
            method_counts = {}
            for result in match_results:
                method = result['match_method']
                method_counts[method] = method_counts.get(method, 0) + 1

            for method, count in sorted(method_counts.items(), key=lambda x: x[1], reverse=True):
                message_parts.append(f"• {method}: {count} channels")

            if dry_run:
                message_parts.append("")
                message_parts.append("ℹ️ All matches validated to have program data in the specified time window.")
                message_parts.append("Use 'Apply Auto-Match EPG Assignments' to apply these matches.")
            else:
                message_parts.append("")
                message_parts.append("✓ All assigned EPG sources have been validated to contain program data.")
                message_parts.append("GUI refresh triggered - changes should be visible shortly.")
            
            return {
                "status": "success",
                "message": "\n".join(message_parts),
                "results": {
                    "total_channels": total_channels,
                    "matched": epg_found,
                    "csv_file": csv_filepath
                }
            }
            
        except Exception as e:
            self.scan_progress['status'] = 'idle'
            logger.error(f"{PLUGIN_NAME}: Error during auto-match: {str(e)}")
            return {"status": "error", "message": f"Error during auto-match: {str(e)}"}

    def _extract_location(self, channel_name):
        """
        Extract geographic location (city and state) from channel name.

        Patterns supported:
        - "ABC - IL Harrisburg (WSIL)" -> {"state": "IL", "city": "Harrisburg"}
        - "NBC (WKBW) NY Buffalo" -> {"state": "NY", "city": "Buffalo"}
        - "CBS - OH Cleveland" -> {"state": "OH", "city": "Cleveland"}

        Returns:
            dict: {"state": str, "city": str} or {"state": None, "city": None}
        """
        if not channel_name:
            return {"state": None, "city": None}

        # Pattern 1: "- STATE CITY" (most common)
        # Example: "ABC - IL Harrisburg (WSIL)"
        pattern1 = r'-\s*([A-Z]{2})\s+([A-Za-z\s]+?)(?:\s*\(|$)'
        match = re.search(pattern1, channel_name)
        if match:
            state = match.group(1)
            city = match.group(2).strip()
            return {"state": state, "city": city}

        # Pattern 2: "(CALLSIGN) STATE CITY" or "STATE CITY (CALLSIGN)"
        # Example: "NBC (WKBW) NY Buffalo"
        pattern2 = r'(?:\([A-Z]{4}\)\s*)?([A-Z]{2})\s+([A-Za-z\s]+)'
        match = re.search(pattern2, channel_name)
        if match:
            state = match.group(1)
            city = match.group(2).strip()
            # Remove trailing parentheses content
            city = re.sub(r'\s*\(.*$', '', city).strip()
            if city and len(city) > 2:  # Valid city name
                return {"state": state, "city": city}

        # Pattern 3: Just look for two-letter state code
        pattern3 = r'\b([A-Z]{2})\b'
        match = re.search(pattern3, channel_name)
        if match:
            state = match.group(1)
            # Common state codes
            valid_states = [
                'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
                'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
                'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
                'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
                'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY', 'DC'
            ]
            if state in valid_states:
                return {"state": state, "city": None}

        return {"state": None, "city": None}

    def _find_best_epg_match(self, channel_name, all_epg_data, now, end_time, logger, exclude_epg_id=None):
        """
        Find the best EPG match for a channel using intelligent weighted scoring and program data validation.

        This is a shared matching function used by both Auto-Match and Scan & Heal.

        Uses a weighted scoring system:
        - Callsign match: 50 points (highest priority)
        - State match: 30 points (medium-high priority)
        - City match: 20 points (medium priority)
        - Network match: 10 points (low priority)

        Validates that the matched EPG has actual program data.

        Args:
            channel_name: Name of the channel to match
            all_epg_data: List of all available EPG data entries
            now: Current time for program data validation
            end_time: End of scan window for program data validation
            logger: Logger instance
            exclude_epg_id: Optional EPG ID to exclude from matching (for Scan & Heal)

        Returns:
            Tuple of (epg_dict, confidence_score, match_method) or (None, 0, None)
        """
        try:
            # Extract clues from channel name
            callsign = self.fuzzy_matcher.extract_callsign(channel_name)
            location = self._extract_location(channel_name)

            # Extract network name (ABC, NBC, CBS, FOX, etc.)
            network = None
            network_pattern = r'\b(ABC|NBC|CBS|FOX|PBS|CW|ION|MNT|IND)\b'
            network_match = re.search(network_pattern, channel_name, re.IGNORECASE)
            if network_match:
                network = network_match.group(1).upper()

            # Score all EPG candidates
            candidates = []

            for epg in all_epg_data:
                # Skip excluded EPG if specified
                if exclude_epg_id and epg.get('id') == exclude_epg_id:
                    continue

                score = 0
                match_components = []
                epg_name = epg.get('name', '')

                # High Priority: Callsign match
                if callsign:
                    epg_callsign = self.fuzzy_matcher.extract_callsign(epg_name)
                    if epg_callsign and epg_callsign.upper() == callsign.upper():
                        score += 50
                        match_components.append("Callsign")

                # Medium-High Priority: State match
                if location['state']:
                    epg_location = self._extract_location(epg_name)
                    if epg_location['state'] and epg_location['state'] == location['state']:
                        score += 30
                        match_components.append("State")

                        # Medium Priority: City match (bonus if state already matches)
                        if location['city'] and epg_location['city']:
                            if location['city'].upper() in epg_location['city'].upper() or \
                               epg_location['city'].upper() in location['city'].upper():
                                score += 20
                                match_components.append("City")

                # Low Priority: Network match
                if network:
                    if network in epg_name.upper():
                        score += 10
                        match_components.append("Network")

                # Fallback: Try fuzzy matching on channel name (for premium channels without callsigns)
                if score == 0:
                    # Use fuzzy matcher for similarity
                    from difflib import SequenceMatcher
                    similarity = SequenceMatcher(None, channel_name.upper(), epg_name.upper()).ratio()
                    if similarity >= 0.85:  # 85% similarity threshold
                        score = int(similarity * 50)  # Max 50 points for fuzzy match
                        match_components.append("Fuzzy")

                # Only consider candidates with some score
                if score > 0:
                    candidates.append({
                        'epg': epg,
                        'score': score,
                        'components': match_components
                    })

            # Sort candidates by score (highest first)
            candidates.sort(key=lambda x: x['score'], reverse=True)

            # Validate candidates in order until we find one with program data
            for candidate in candidates:
                epg = candidate['epg']
                epg_id = epg.get('id')

                # Check if this EPG has program data
                try:
                    from apps.epg.models import EPGData
                    epg_obj = EPGData.objects.get(id=epg_id)

                    has_programs = ProgramData.objects.filter(
                        epg=epg_obj,
                        end_time__gte=now,
                        start_time__lt=end_time
                    ).exists()

                    if has_programs:
                        # Found a working match!
                        match_method = " + ".join(candidate['components'])
                        confidence = min(candidate['score'], 100)  # Cap at 100

                        logger.debug(f"{PLUGIN_NAME}: Found EPG match for {channel_name}: {epg.get('name')} (confidence: {confidence}%, method: {match_method})")

                        return epg, confidence, match_method

                except Exception as val_error:
                    # EPG validation failed, try next candidate
                    logger.debug(f"{PLUGIN_NAME}: Validation failed for EPG {epg_id}: {val_error}")
                    continue

            # No working match found
            logger.debug(f"{PLUGIN_NAME}: No working EPG match found for {channel_name} (tried {len(candidates)} candidates)")
            return None, 0, None

        except Exception as e:
            logger.error(f"{PLUGIN_NAME}: Error finding EPG match for {channel_name}: {e}")
            return None, 0, None

    def _find_working_replacement(self, channel, all_epg_data, now, end_time, logger):
        """
        Find a working EPG replacement for a broken channel.

        This is a wrapper around _find_best_epg_match that excludes the original broken EPG.

        Args:
            channel: The broken channel object
            all_epg_data: List of all available EPG data entries
            now: Current time
            end_time: End of scan window
            logger: Logger instance

        Returns:
            Tuple of (epg_dict, confidence_score, match_method) or (None, 0, None)
        """
        original_epg_id = channel.epg_data.id if channel.epg_data else None
        return self._find_best_epg_match(
            channel.name,
            all_epg_data,
            now,
            end_time,
            logger,
            exclude_epg_id=original_epg_id
        )

    def _scan_and_heal_worker(self, settings, logger, context, dry_run=True):
        """
        Scan for broken EPG assignments and find working replacements.

        Steps:
        1. Find channels with EPG but no program data (broken channels)
        2. Gather all available EPG data from all sources
        3. For each broken channel, search for a working replacement
        4. Validate that replacement has actual program data
        5. Apply fixes if not dry run and confidence >= threshold
        6. Generate detailed CSV report and summary message
        """
        try:
            # Get API token
            token, error = self._get_api_token(settings, logger)
            if error:
                return {"status": "error", "message": error}

            check_hours = settings.get("check_hours", 12)
            now = timezone.now()
            end_time = now + timedelta(hours=check_hours)

            logger.info(f"{PLUGIN_NAME}: Starting Scan & Heal for next {check_hours} hours...")

            # STEP 1: Find broken channels (reuse scan logic)
            logger.info(f"{PLUGIN_NAME}: Step 1/6: Finding channels with broken EPG assignments...")

            channels_query = Channel.objects.filter(
                epg_data__isnull=False
            ).select_related('epg_data', 'epg_data__epg_source', 'channel_group')

            # Validate and filter groups
            try:
                channels_query, group_filter_info, groups_used = self._validate_and_filter_groups(
                    settings, logger, channels_query, token
                )
            except ValueError as e:
                return {"status": "error", "message": str(e)}

            channels_with_epg = list(channels_query)
            total_channels = len(channels_with_epg)

            # Initialize progress tracking
            self.scan_progress = {"current": 0, "total": total_channels, "status": "running", "start_time": time.time()}

            broken_channels = []

            # Find channels with no program data
            for i, channel in enumerate(channels_with_epg):
                self.scan_progress["current"] = i + 1

                has_programs = ProgramData.objects.filter(
                    epg=channel.epg_data,
                    end_time__gte=now,
                    start_time__lt=end_time
                ).exists()

                if not has_programs:
                    broken_channels.append(channel)

            # If no channels are found based on filters
            if total_channels == 0:
                self.scan_progress['status'] = 'idle'
                return {
                    "status": "success",
                    "message": "No channels found with the current filter settings. Please check your 'Channel Groups' and 'Channel Profile' settings.",
                    "results": {"total_scanned": 0, "broken": 0, "healed": 0}
                }

            logger.info(f"{PLUGIN_NAME}: Found {len(broken_channels)} channels with broken EPG assignments")

            if not broken_channels:
                self.scan_progress['status'] = 'idle'
                return {
                    "status": "success",
                    "message": f"No broken EPG assignments found! All {total_channels} channels have program data.",
                    "results": {"total_scanned": total_channels, "broken": 0, "healed": 0}
                }

            # STEP 2: Gather all available EPG data
            logger.info(f"{PLUGIN_NAME}: Step 2/6: Gathering all available EPG data...")

            # Determine which EPG sources to search
            heal_sources_str = settings.get("heal_fallback_sources", "").strip()
            if not heal_sources_str:
                heal_sources_str = settings.get("epg_sources_to_match", "").strip()

            # Get all EPG data with source filtering
            # Create a copy of settings and override epg_sources_to_match if needed
            epg_settings = settings.copy()
            if heal_sources_str:
                epg_settings["epg_sources_to_match"] = heal_sources_str

            all_epg_data = self._get_filtered_epg_data(token, epg_settings, logger)

            logger.info(f"{PLUGIN_NAME}: Loaded {len(all_epg_data)} EPG entries from available sources")

            if not all_epg_data:
                self.scan_progress['status'] = 'idle'
                return {
                    "status": "error",
                    "message": "No EPG data available to search for replacements. Check your EPG sources."
                }

            # STEP 3: Hunt for replacements
            logger.info(f"{PLUGIN_NAME}: Step 3/6: Searching for working replacements...")

            heal_results = []
            replacements_found = 0
            high_confidence_replacements = 0
            confidence_threshold = settings.get("heal_confidence_threshold", 95)

            for i, channel in enumerate(broken_channels):
                self.scan_progress["current"] = total_channels + i + 1
                self.scan_progress["total"] = total_channels + len(broken_channels)

                if (i + 1) % 10 == 0 or (i + 1) == len(broken_channels):
                    logger.info(f"{PLUGIN_NAME}: Processing {i + 1}/{len(broken_channels)} broken channels...")

                # Try to find a working replacement
                replacement_epg, confidence, match_method = self._find_working_replacement(
                    channel, all_epg_data, now, end_time, logger
                )

                result = {
                    "channel_id": channel.id,
                    "channel_name": channel.name,
                    "channel_number": float(channel.channel_number) if channel.channel_number else None,
                    "channel_group": channel.channel_group.name if channel.channel_group else "No Group",
                    "original_epg_id": channel.epg_data.id,
                    "original_epg_name": channel.epg_data.name,
                    "original_epg_source": channel.epg_data.epg_source.name if channel.epg_data.epg_source else "Unknown",
                    "new_epg_id": None,
                    "new_epg_name": None,
                    "new_epg_source": None,
                    "match_confidence": 0,
                    "match_method": "NO_REPLACEMENT_FOUND",
                    "status": "NO_REPLACEMENT_FOUND",
                }

                if replacement_epg:
                    replacements_found += 1
                    result["new_epg_id"] = replacement_epg.get('id')
                    result["new_epg_name"] = replacement_epg.get('name')

                    # Get source name
                    epg_source_id = replacement_epg.get('epg_source')
                    if epg_source_id:
                        try:
                            epg_sources = self._get_api_data("/api/epg/sources/", token, settings, logger)
                            for src in epg_sources:
                                if src['id'] == epg_source_id:
                                    result["new_epg_source"] = src['name']
                                    break
                        except:
                            result["new_epg_source"] = "Unknown"

                    result["match_confidence"] = confidence
                    result["match_method"] = match_method

                    # Determine status based on mode and confidence
                    if dry_run:
                        result["status"] = "REPLACEMENT_PREVIEW"
                    else:
                        if confidence >= confidence_threshold:
                            result["status"] = "HEALED"
                            high_confidence_replacements += 1
                        else:
                            result["status"] = "SKIPPED_LOW_CONFIDENCE"

                heal_results.append(result)

            logger.info(f"{PLUGIN_NAME}: Search complete. Found {replacements_found} potential replacements ({high_confidence_replacements} high-confidence)")

            # STEP 4: Process results (already done above)

            # STEP 5: Apply fixes if not dry run
            if not dry_run and high_confidence_replacements > 0:
                logger.info(f"{PLUGIN_NAME}: Step 4/6: Applying {high_confidence_replacements} high-confidence EPG replacements...")

                associations = []
                for result in heal_results:
                    if result['status'] == 'HEALED' and result['new_epg_id']:
                        associations.append({
                            'channel_id': int(result['channel_id']),
                            'epg_data_id': int(result['new_epg_id'])
                        })

                if associations:
                    try:
                        response = self._post_api_data("/api/channels/channels/batch-set-epg/", token,
                                          {"associations": associations}, settings, logger)

                        channels_updated = response.get('channels_updated', 0)
                        logger.info(f"{PLUGIN_NAME}: Successfully healed {channels_updated} channels")

                        # Trigger frontend refresh
                        self._trigger_frontend_refresh(settings, logger)
                    except Exception as e:
                        logger.error(f"{PLUGIN_NAME}: Failed to apply EPG replacements: {e}")
                        return {"status": "error", "message": f"Failed to apply EPG replacements: {e}"}

            # STEP 6: Generate CSV report and summary
            logger.info(f"{PLUGIN_NAME}: Step 5/6: Generating report...")

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_filename = f"epg_janitor_heal_results_{timestamp}.csv"
            csv_filepath = os.path.join("/data/exports", csv_filename)
            os.makedirs("/data/exports", exist_ok=True)

            with open(csv_filepath, 'w', newline='', encoding='utf-8') as csvfile:
                # Write comment header with plugin options
                header_comments = self._generate_csv_header_comments(settings, total_channels)
                for comment_line in header_comments:
                    csvfile.write(comment_line + '\n')

                fieldnames = [
                    'channel_id', 'channel_name', 'channel_number', 'channel_group',
                    'original_epg_name', 'original_epg_source',
                    'new_epg_name', 'new_epg_source',
                    'match_confidence', 'match_method', 'status'
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for result in heal_results:
                    writer.writerow({
                        'channel_id': result['channel_id'],
                        'channel_name': result['channel_name'],
                        'channel_number': result['channel_number'],
                        'channel_group': result['channel_group'],
                        'original_epg_name': result['original_epg_name'],
                        'original_epg_source': result['original_epg_source'],
                        'new_epg_name': result['new_epg_name'] or 'N/A',
                        'new_epg_source': result['new_epg_source'] or 'N/A',
                        'match_confidence': result['match_confidence'],
                        'match_method': result['match_method'],
                        'status': result['status']
                    })

            logger.info(f"{PLUGIN_NAME}: Report exported to {csv_filepath}")

            # Mark scan as complete
            self.scan_progress['status'] = 'idle'

            # Build summary message
            mode_text = "Dry Run" if dry_run else "Applied"

            message_parts = [
                f"Scan & Heal {mode_text} completed{group_filter_info}:",
                f"• Total channels scanned: {total_channels}",
                f"• Broken EPG assignments: {len(broken_channels)}",
                f"• Working replacements found: {replacements_found}",
            ]

            if not dry_run:
                message_parts.append(f"• High-confidence fixes applied: {high_confidence_replacements}")
                skipped = replacements_found - high_confidence_replacements
                if skipped > 0:
                    message_parts.append(f"• Skipped (low confidence): {skipped}")
                not_fixed = len(broken_channels) - high_confidence_replacements
                if not_fixed > 0:
                    message_parts.append(f"• Could not fix: {not_fixed}")
            else:
                high_conf = sum(1 for r in heal_results if r['match_confidence'] >= confidence_threshold and r['new_epg_id'])
                message_parts.append(f"• Would apply (confidence ≥{confidence_threshold}%): {high_conf}")

            message_parts.append("")
            message_parts.append(f"Results exported to: {csv_filepath}")

            if dry_run:
                message_parts.append("")
                message_parts.append("Use '🚀 Scan & Heal (Apply Changes)' to apply these fixes.")
            else:
                message_parts.append("")
                message_parts.append("GUI refresh triggered - changes should be visible shortly.")

            return {
                "status": "success",
                "message": "\n".join(message_parts),
                "results": {
                    "total_scanned": total_channels,
                    "broken": len(broken_channels),
                    "replacements_found": replacements_found,
                    "healed": high_confidence_replacements if not dry_run else 0,
                    "csv_file": csv_filepath
                }
            }

        except Exception as e:
            self.scan_progress['status'] = 'idle'
            logger.error(f"{PLUGIN_NAME}: Error during Scan & Heal: {str(e)}")
            import traceback
            logger.error(f"{PLUGIN_NAME}: Traceback: {traceback.format_exc()}")
            return {"status": "error", "message": f"Error during Scan & Heal: {str(e)}"}

    def _validate_and_filter_groups(self, settings, logger, channels_query, token):
        """Validate group settings and filter channels accordingly"""
        selected_groups_str = settings.get("selected_groups", "").strip()
        ignore_groups_str = settings.get("ignore_groups", "").strip()
        channel_profile_names_str = settings.get("channel_profile_name", "").strip()

        # Validation: both cannot be used together
        if selected_groups_str and ignore_groups_str:
            raise ValueError("Cannot use both 'Channel Groups' and 'Ignore Groups' at the same time. Please use only one.")

        # Try to get channel groups via API first
        try:
            logger.info(f"{PLUGIN_NAME}: Attempting to fetch channel groups via API...")
            api_groups = self._get_api_data("/api/channels/groups/", token, settings, logger)
            logger.info(f"{PLUGIN_NAME}: Successfully fetched {len(api_groups)} groups via API")
            group_name_to_id = {g['name']: g['id'] for g in api_groups if 'name' in g and 'id' in g}
        except Exception as api_error:
            logger.warning(f"{PLUGIN_NAME}: API request failed, falling back to Django ORM: {api_error}")
            group_name_to_id = {}

        group_filter_info = ""
        profile_filter_info = ""

        # Handle Channel Profile filtering (supports multiple comma-separated profiles)
        if channel_profile_names_str:
            try:
                # Parse comma-separated profile names
                profile_names = [name.strip() for name in channel_profile_names_str.split(',') if name.strip()]
                logger.info(f"{PLUGIN_NAME}: Filtering by Channel Profile(s): {', '.join(profile_names)}")

                # Fetch all channel profiles
                profiles = self._get_api_data("/api/channels/profiles/", token, settings, logger)

                # Build a mapping of profile names to IDs (case-insensitive)
                profile_name_to_id = {p.get('name', '').strip().upper(): p.get('id') for p in profiles if p.get('name')}

                # Collect all visible channel IDs from all requested profiles
                all_visible_channel_ids = set()
                found_profiles = []
                not_found_profiles = []

                for profile_name in profile_names:
                    profile_name_upper = profile_name.upper()
                    profile_id = profile_name_to_id.get(profile_name_upper)

                    if not profile_id:
                        not_found_profiles.append(profile_name)
                        continue

                    # Fetch the profile details to get visible channel IDs
                    profile_details = self._get_api_data(f"/api/channels/profiles/{profile_id}/", token, settings, logger)

                    # The API returns 'channels' not 'visible_channels'
                    visible_channel_ids = profile_details.get('channels', [])

                    if visible_channel_ids:
                        all_visible_channel_ids.update(visible_channel_ids)
                        found_profiles.append(profile_name)
                        logger.info(f"{PLUGIN_NAME}: Profile '{profile_name}' has {len(visible_channel_ids)} visible channels")

                # Report any profiles that weren't found
                if not_found_profiles:
                    available_profiles = ', '.join([p.get('name', '') for p in profiles])
                    logger.warning(f"{PLUGIN_NAME}: Profile(s) not found: {', '.join(not_found_profiles)}. Available profiles: {available_profiles}")

                # Check if we found at least one profile with channels
                if not all_visible_channel_ids:
                    if not_found_profiles and not found_profiles:
                        available_profiles = ', '.join([p.get('name', '') for p in profiles])
                        raise ValueError(f"None of the specified Channel Profiles were found: {', '.join(profile_names)}. Available profiles: {available_profiles}")
                    else:
                        raise ValueError(f"The specified Channel Profile(s) have no visible channels: {', '.join(found_profiles if found_profiles else profile_names)}")

                logger.info(f"{PLUGIN_NAME}: Total unique channels across {len(found_profiles)} profile(s): {len(all_visible_channel_ids)}")

                # Filter channels to only those visible in any of the profiles
                channels_query = channels_query.filter(id__in=list(all_visible_channel_ids))

                if len(found_profiles) == 1:
                    profile_filter_info = f" in profile '{found_profiles[0]}'"
                else:
                    profile_filter_info = f" in profiles: {', '.join(found_profiles)}"

            except ValueError as e:
                # Re-raise ValueError for proper error handling
                raise
            except Exception as e:
                logger.error(f"{PLUGIN_NAME}: Error filtering by Channel Profile(s): {e}")
                import traceback
                logger.error(f"{PLUGIN_NAME}: Traceback: {traceback.format_exc()}")
                raise ValueError(f"Error filtering by Channel Profile(s) '{channel_profile_names_str}': {e}")
        
        # Handle selected groups (include only these)
        if selected_groups_str:
            selected_groups = [g.strip() for g in selected_groups_str.split(',') if g.strip()]
            if group_name_to_id:
                valid_group_ids = [group_name_to_id[name] for name in selected_groups if name in group_name_to_id]
                if not valid_group_ids:
                    raise ValueError(f"None of the specified groups were found: {', '.join(selected_groups)}")
                channels_query = channels_query.filter(channel_group_id__in=valid_group_ids)
            else:
                channels_query = channels_query.filter(channel_group__name__in=selected_groups)
            
            logger.info(f"{PLUGIN_NAME}: Filtering to groups: {', '.join(selected_groups)}")
            group_filter_info = f" in groups: {', '.join(selected_groups)}"
        
        # Handle ignore groups (exclude these)
        elif ignore_groups_str:
            ignore_groups = [g.strip() for g in ignore_groups_str.split(',') if g.strip()]
            if group_name_to_id:
                ignore_group_ids = [group_name_to_id[name] for name in ignore_groups if name in group_name_to_id]
                if ignore_group_ids:
                    channels_query = channels_query.exclude(channel_group_id__in=ignore_group_ids)
                else:
                    logger.warning(f"{PLUGIN_NAME}: None of the ignore groups were found: {', '.join(ignore_groups)}")
            else:
                channels_query = channels_query.exclude(channel_group__name__in=ignore_groups)
            
            logger.info(f"{PLUGIN_NAME}: Ignoring groups: {', '.join(ignore_groups)}")
            group_filter_info = f" (ignoring: {', '.join(ignore_groups)})"
        
        # Combine filter info messages
        combined_filter_info = profile_filter_info + group_filter_info

        return channels_query, combined_filter_info, selected_groups_str or ignore_groups_str or channel_profile_names_str

    def _get_api_token(self, settings, logger):
        """
        Get an API access token using username and password.
        Uses caching to avoid unnecessary authentication requests.
        """
        dispatcharr_url = settings.get("dispatcharr_url", "").strip().rstrip('/')
        username = settings.get("dispatcharr_username", "")
        password = settings.get("dispatcharr_password", "")

        if not all([dispatcharr_url, username, password]):
            return None, "Dispatcharr URL, Username, and Password must be configured in the plugin settings."

        # Check cache first
        cache = self._load_token_cache()
        is_valid, cached_token = self._is_token_valid(cache, settings)

        if is_valid and cached_token:
            return cached_token, None

        # Cache miss or expired - authenticate with API
        try:
            url = f"{dispatcharr_url}/api/accounts/token/"
            payload = {"username": username, "password": password}

            logger.info(f"{PLUGIN_NAME}: Obtaining new API token from Dispatcharr at: {url}")
            response = requests.post(url, json=payload, timeout=15)

            if response.status_code == 401:
                logger.error(f"{PLUGIN_NAME}: Authentication failed - invalid credentials")
                return None, "Authentication failed. Please check your username and password in the plugin settings."
            elif response.status_code == 404:
                logger.error(f"{PLUGIN_NAME}: API endpoint not found - check Dispatcharr URL: {dispatcharr_url}")
                return None, f"API endpoint not found. Please verify your Dispatcharr URL: {dispatcharr_url}"
            elif response.status_code >= 500:
                logger.error(f"{PLUGIN_NAME}: Server error from Dispatcharr: {response.status_code}")
                return None, f"Dispatcharr server error ({response.status_code}). Please check if Dispatcharr is running properly."

            response.raise_for_status()
            token_data = response.json()
            access_token = token_data.get("access")

            if not access_token:
                logger.error(f"{PLUGIN_NAME}: No access token returned from API")
                return None, "Login successful, but no access token was returned by the API."

            # Cache the new token
            cache_data = {
                "token": access_token,
                "timestamp": time.time(),
                "dispatcharr_url": dispatcharr_url,
                "username": username
            }
            self._save_token_cache(cache_data)

            logger.info(f"{PLUGIN_NAME}: Successfully obtained and cached new API access token")
            return access_token, None
            
        except requests.exceptions.ConnectionError as e:
            logger.error(f"{PLUGIN_NAME}: Connection error: {e}")
            return None, f"Unable to connect to Dispatcharr at {dispatcharr_url}. Please check the URL and ensure Dispatcharr is running."
        except requests.exceptions.Timeout as e:
            logger.error(f"{PLUGIN_NAME}: Request timeout: {e}")
            return None, "Request timed out while connecting to Dispatcharr. Please check your network connection."
        except requests.RequestException as e:
            logger.error(f"{PLUGIN_NAME}: Request error: {e}")
            return None, f"Network error occurred while authenticating: {e}"
        except json.JSONDecodeError as e:
            logger.error(f"{PLUGIN_NAME}: Invalid JSON response: {e}")
            return None, "Invalid response from Dispatcharr API. Please check if the URL is correct."
        except Exception as e:
            logger.error(f"{PLUGIN_NAME}: Unexpected error during authentication: {e}")
            return None, f"Unexpected error during authentication: {e}"

    def _get_api_data(self, endpoint, token, settings, logger):
        """Helper to perform GET requests to the Dispatcharr API."""
        dispatcharr_url = settings.get("dispatcharr_url", "").strip().rstrip('/')
        url = f"{dispatcharr_url}{endpoint}"
        headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 401:
                logger.error(f"{PLUGIN_NAME}: API token expired or invalid")
                raise Exception("API authentication failed. Token may have expired.")
            elif response.status_code == 403:
                logger.error(f"{PLUGIN_NAME}: API access forbidden")
                raise Exception("API access forbidden. Check user permissions.")
            elif response.status_code == 404:
                logger.error(f"{PLUGIN_NAME}: API endpoint not found: {endpoint}")
                raise Exception(f"API endpoint not found: {endpoint}")
            
            response.raise_for_status()
            
            # Check if response is empty
            if not response.text or response.text.strip() == '':
                logger.warning(f"{PLUGIN_NAME}: Empty response from {endpoint}, returning empty list")
                return []
            
            try:
                json_data = response.json()
            except json.JSONDecodeError as e:
                logger.error(f"{PLUGIN_NAME}: Failed to parse JSON from {endpoint}: {e}")
                logger.error(f"{PLUGIN_NAME}: Response text: {response.text}")
                raise Exception(f"Invalid JSON response from {endpoint}: {e}")
            
            if isinstance(json_data, dict):
                return json_data.get('results', json_data)
            elif isinstance(json_data, list):
                return json_data
            return []
            
        except requests.exceptions.RequestException as e:
            logger.error(f"{PLUGIN_NAME}: API request failed for {endpoint}: {e}")
            raise Exception(f"API request failed: {e}")

    def _post_api_data(self, endpoint, token, payload, settings, logger):
        """Helper to perform POST requests to the Dispatcharr API."""
        dispatcharr_url = settings.get("dispatcharr_url", "").strip().rstrip('/')
        url = f"{dispatcharr_url}{endpoint}"
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        
        try:
            logger.info(f"{PLUGIN_NAME}: Making API POST request to: {endpoint}")
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 401:
                logger.error(f"{PLUGIN_NAME}: API token expired or invalid")
                raise Exception("API authentication failed. Token may have expired.")
            elif response.status_code == 403:
                logger.error(f"{PLUGIN_NAME}: API access forbidden")
                raise Exception("API access forbidden. Check user permissions.")
            elif response.status_code == 404:
                logger.error(f"{PLUGIN_NAME}: API endpoint not found: {endpoint}")
                raise Exception(f"API endpoint not found: {endpoint}")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"{PLUGIN_NAME}: API POST request failed for {endpoint}: {e}")
            raise Exception(f"API POST request failed: {e}")

    def _patch_api_data(self, endpoint, token, payload, settings, logger):
        """Helper to perform PATCH requests to the Dispatcharr API."""
        dispatcharr_url = settings.get("dispatcharr_url", "").strip().rstrip('/')
        url = f"{dispatcharr_url}{endpoint}"
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        
        try:
            logger.info(f"{PLUGIN_NAME}: Making API PATCH request to: {endpoint}")
            response = requests.patch(url, headers=headers, json=payload, timeout=60)
            
            if response.status_code == 401:
                logger.error(f"{PLUGIN_NAME}: API token expired or invalid")
                raise Exception("API authentication failed. Token may have expired.")
            elif response.status_code == 403:
                logger.error(f"{PLUGIN_NAME}: API access forbidden")
                raise Exception("API access forbidden. Check user permissions.")
            elif response.status_code == 404:
                logger.error(f"{PLUGIN_NAME}: API endpoint not found: {endpoint}")
                raise Exception(f"API endpoint not found: {endpoint}")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"{PLUGIN_NAME}: API PATCH request failed for {endpoint}: {e}")
            raise Exception(f"API PATCH request failed: {e}")

    def _trigger_frontend_refresh(self, settings, logger):
        """Trigger frontend channel list refresh via WebSocket"""
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            
            channel_layer = get_channel_layer()
            if channel_layer:
                # Send WebSocket message to trigger frontend refresh
                async_to_sync(channel_layer.group_send)(
                    "dispatcharr_updates",
                    {
                        "type": "channels.updated",
                        "message": "Channels updated by EPG Janitor"
                    }
                )
                logger.info(f"{PLUGIN_NAME}: Frontend refresh triggered via WebSocket")
                return True
        except Exception as e:
            logger.warning(f"{PLUGIN_NAME}: Could not trigger frontend refresh: {e}")
        return False

    def _generate_csv_header_comments(self, settings, total_channels):
        """
        Generate CSV comment header lines showing plugin options and channel count.
        Excludes admin credentials and Dispatcharr URL for security.

        Args:
            settings: Plugin settings dictionary
            total_channels: Number of channels processed

        Returns:
            List of comment strings to write as CSV header
        """
        header_lines = []
        header_lines.append(f"# EPG Janitor v{self.version} - Export Report")
        header_lines.append(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        header_lines.append(f"# Channels Processed: {total_channels}")
        header_lines.append("#")
        header_lines.append("# Plugin Settings:")

        # Add all settings except sensitive ones
        settings_to_show = {
            "channel_profile_name": "Channel Profiles",
            "epg_sources_to_match": "EPG Sources to Match",
            "check_hours": "Hours to Check Ahead",
            "selected_groups": "Channel Groups",
            "ignore_groups": "Ignore Groups",
            "epg_regex_to_remove": "EPG Name REGEX to Remove",
            "bad_epg_suffix": "Bad EPG Suffix",
            "remove_epg_with_suffix": "Remove EPG When Adding Suffix",
            "heal_fallback_sources": "Heal: Fallback EPG Sources",
            "heal_confidence_threshold": "Heal: Confidence Threshold",
            "ignore_quality_tags": "Ignore Quality Tags",
            "ignore_regional_tags": "Ignore Regional Tags",
            "ignore_geographic_tags": "Ignore Geographic Prefixes",
            "ignore_misc_tags": "Ignore Miscellaneous Tags",
        }

        for setting_id, label in settings_to_show.items():
            value = settings.get(setting_id)
            if value is None or value == "":
                value = "(not set)"
            header_lines.append(f"#   {label}: {value}")

        header_lines.append("#")
        return header_lines

    def run(self, action, params, context):
        """Main plugin entry point"""
        LOGGER.info(f"{PLUGIN_NAME}: run called with action: {action}")

        try:
            # Get settings from context
            settings = context.get("settings", {})
            logger = context.get("logger", LOGGER)

            # Handle channel database selection from boolean fields
            # Get list of available databases
            available_databases = self._get_channel_databases()

            # Determine if this is first run (no database settings saved yet)
            has_any_db_setting = any(key.startswith("enable_db_") for key in settings.keys())

            # Collect all enabled databases
            enabled_databases = []
            if available_databases:
                single_database = len(available_databases) == 1

                for db in available_databases:
                    db_key = f"enable_db_{db['id']}"

                    # Check if setting exists in settings
                    if db_key in settings:
                        # Use the explicit setting
                        if settings[db_key] is True:
                            enabled_databases.append(db['id'])
                    elif not has_any_db_setting:
                        # No database settings exist yet - apply defaults
                        # Default to True if: single database OR it's the US database
                        default_enabled = single_database or db['id'].upper() == 'US'
                        if default_enabled:
                            enabled_databases.append(db['id'])

            # Sort for consistency
            enabled_databases.sort()

            # Ensure fuzzy matcher has country_codes attribute (backward compatibility)
            if not hasattr(self.fuzzy_matcher, 'country_codes'):
                self.fuzzy_matcher.country_codes = None
                LOGGER.warning(f"{PLUGIN_NAME}: FuzzyMatcher missing country_codes attribute, initialized to None")

            if enabled_databases:
                # Reload fuzzy matcher with enabled databases
                current_codes = self.fuzzy_matcher.country_codes
                new_codes = enabled_databases

                # Only reload if the selection has changed
                if current_codes != new_codes:
                    LOGGER.info(f"{PLUGIN_NAME}: Loading channel databases for: {', '.join(enabled_databases)}")
                    success = self.fuzzy_matcher.reload_databases(country_codes=new_codes)
                    if not success:
                        return {
                            "status": "error",
                            "message": f"Failed to load channel databases: {', '.join(enabled_databases)}. Please verify the database files exist."
                        }
                    LOGGER.info(f"{PLUGIN_NAME}: Successfully loaded {len(enabled_databases)} channel database(s)")
            else:
                # If no databases are enabled, ensure all databases are loaded
                if self.fuzzy_matcher.country_codes is not None:
                    LOGGER.info(f"{PLUGIN_NAME}: No databases enabled, loading all available databases")
                    self.fuzzy_matcher.reload_databases(country_codes=None)

            # Update fuzzy matcher category settings from user preferences
            self.fuzzy_matcher.ignore_quality = settings.get("ignore_quality_tags", True)
            self.fuzzy_matcher.ignore_regional = settings.get("ignore_regional_tags", True)
            self.fuzzy_matcher.ignore_geographic = settings.get("ignore_geographic_tags", True)
            self.fuzzy_matcher.ignore_misc = settings.get("ignore_misc_tags", True)

            action_map = {
                "validate_settings": self.validate_settings_action,
                "preview_auto_match": self.preview_auto_match_action,
                "apply_auto_match": self.apply_auto_match_action,
                "scan_missing_epg": self.scan_missing_epg_action,
                "scan_and_heal_dry_run": self.scan_and_heal_dry_run_action,
                "scan_and_heal_apply": self.scan_and_heal_apply_action,
                "export_results": self.export_results_action,
                "get_summary": self.get_summary_action,
                "remove_epg_assignments": self.remove_epg_assignments_action,
                "remove_epg_by_regex": self.remove_epg_by_regex_action,
                "remove_all_epg_from_groups": self.remove_all_epg_from_groups_action,
                "add_bad_epg_suffix": self.add_bad_epg_suffix_action,
                "remove_epg_from_hidden": self.remove_epg_from_hidden_action,
                "clear_csv_exports": self.clear_csv_exports_action,
            }
            
            if action not in action_map:
                return {
                    "status": "error",
                    "message": f"Unknown action: {action}",
                    "available_actions": list(action_map.keys())
                }
            
            # Pass context to actions that need it
            if action in ["scan_missing_epg", "preview_auto_match", "apply_auto_match", "scan_and_heal_dry_run", "scan_and_heal_apply"]:
                return action_map[action](settings, logger, context)
            else:
                return action_map[action](settings, logger)
                
        except Exception as e:
            self.scan_progress['status'] = 'idle'
            LOGGER.error(f"Error in plugin run: {str(e)}")
            return {"status": "error", "message": str(e)}

    def preview_auto_match_action(self, settings, logger, context=None):
        """Preview auto-match without applying changes"""
        return self._auto_match_channels(settings, logger, dry_run=True)

    def apply_auto_match_action(self, settings, logger, context=None):
        """Apply auto-match and assign EPG to channels"""
        return self._auto_match_channels(settings, logger, dry_run=False)

    def scan_and_heal_dry_run_action(self, settings, logger, context=None):
        """Scan for broken EPG and find replacements without applying changes"""
        return self._scan_and_heal_worker(settings, logger, context, dry_run=True)

    def scan_and_heal_apply_action(self, settings, logger, context=None):
        """Scan for broken EPG and automatically apply validated replacements"""
        return self._scan_and_heal_worker(settings, logger, context, dry_run=False)

    def scan_missing_epg_action(self, settings, logger, context=None):
        """Scan for channels with EPG but no program data"""
        try:
            # Get API token first
            token, error = self._get_api_token(settings, logger)
            if error:
                return {"status": "error", "message": error}
            
            check_hours = settings.get("check_hours", 12)
            now = timezone.now()
            end_time = now + timedelta(hours=check_hours)
            
            logger.info(f"{PLUGIN_NAME}: Starting EPG scan for next {check_hours} hours...")
            
            # Get all channels that have EPG data assigned
            channels_query = Channel.objects.filter(
                epg_data__isnull=False
            ).select_related('epg_data', 'channel_group')
            
            # Validate and filter groups
            try:
                channels_query, group_filter_info, groups_used = self._validate_and_filter_groups(
                    settings, logger, channels_query, token
                )
            except ValueError as e:
                return {"status": "error", "message": str(e)}
            
            channels_with_epg = list(channels_query)
            total_channels = len(channels_with_epg)
            logger.info(f"{PLUGIN_NAME}: Found {total_channels} channels with EPG assignments")
            
            # Initialize progress tracking
            self.scan_progress = {"current": 0, "total": total_channels, "status": "running", "start_time": time.time()}
            
            channels_with_no_data = []
            
            # Check each channel for program data in the specified timeframe
            for i, channel in enumerate(channels_with_epg):
                self.scan_progress["current"] = i + 1
                
                # Look for programs in the EPG data for this timeframe
                has_programs = ProgramData.objects.filter(
                    epg=channel.epg_data,
                    end_time__gte=now,  # Programs that end now or later
                    start_time__lt=end_time  # Programs that start before our end time
                ).exists()
                
                if not has_programs:
                    channel_info = {
                        "channel_id": channel.id,
                        "channel_name": channel.name,
                        "channel_number": float(channel.channel_number) if channel.channel_number else None,
                        "channel_group": channel.channel_group.name if channel.channel_group else "No Group",
                        "epg_channel_id": channel.epg_data.tvg_id,
                        "epg_channel_name": channel.epg_data.name,
                        "epg_source": channel.epg_data.epg_source.name if channel.epg_data.epg_source else "No Source",
                        "scanned_at": datetime.now().isoformat()
                    }
                    channels_with_no_data.append(channel_info)

            # If no channels are found based on filters
            if total_channels == 0:
                self.scan_progress['status'] = 'idle'
                return {
                    "status": "success",
                    "message": "No channels found with the current filter settings. Please check your 'Channel Groups' and 'Channel Profile' settings.",
                }

            # Mark scan as complete
            self.scan_progress['status'] = 'idle'
            
            # Save results
            results = {
                "scan_time": datetime.now().isoformat(),
                "check_hours": check_hours,
                "selected_groups": settings.get("selected_groups", "").strip(),
                "ignore_groups": settings.get("ignore_groups", "").strip(),
                "total_channels_with_epg": total_channels,
                "channels_missing_data": len(channels_with_no_data),
                "channels": channels_with_no_data
            }
            
            with open(self.results_file, 'w') as f:
                json.dump(results, f, indent=2)
            
            self.last_results = channels_with_no_data
            
            logger.info(f"{PLUGIN_NAME}: EPG scan complete. Found {len(channels_with_no_data)} channels with missing program data")
            
            # Set completion message
            self.completion_message = f"EPG scan completed. Found {len(channels_with_no_data)} channels with missing program data."
            
            # Create summary message
            if channels_with_no_data:
                message_parts = [
                    f"EPG scan completed for next {check_hours} hours{group_filter_info}:",
                    f"• Total channels with EPG: {total_channels}",
                    f"• Channels missing program data: {len(channels_with_no_data)}",
                    "",
                    "Channels with missing EPG data:"
                ]
                
                # Show first 10 channels with issues
                for i, channel in enumerate(channels_with_no_data[:10]):
                    group_info = f" ({channel['channel_group']})" if channel['channel_group'] != "No Group" else ""
                    epg_info = f" [EPG: {channel['epg_channel_name']}]"
                    message_parts.append(f"• {channel['channel_name']}{group_info}{epg_info}")
                
                if len(channels_with_no_data) > 10:
                    message_parts.append(f"... and {len(channels_with_no_data) - 10} more channels")
                
                message_parts.append("")
                message_parts.append("Use 'Export Results to CSV' to get the full list.")
                message_parts.append("Use 'Remove EPG Assignments' to remove EPG from channels with missing data.")
                
            else:
                message_parts = [
                    f"EPG scan completed for next {check_hours} hours{group_filter_info}:",
                    f"• Total channels with EPG: {total_channels}",
                    f"• All channels have program data - no issues found!"
                ]
            
            return {
                "status": "success",
                "message": "\n".join(message_parts),
                "results": {
                    "total_scanned": total_channels,
                    "missing_data": len(channels_with_no_data)
                }
            }
            
        except Exception as e:
            self.scan_progress['status'] = 'idle'
            logger.error(f"{PLUGIN_NAME}: Error during EPG scan: {str(e)}")
            return {"status": "error", "message": f"Error during EPG scan: {str(e)}"}

    def remove_epg_assignments_action(self, settings, logger):
        """Remove EPG assignments from channels that were found missing program data in the last scan"""
        if not os.path.exists(self.results_file):
            return {"status": "error", "message": "No scan results found. Please run 'Scan for Missing Program Data' first."}
        
        try:
            # Get API token first
            token, error = self._get_api_token(settings, logger)
            if error:
                return {"status": "error", "message": error}
            
            # Load the last scan results
            with open(self.results_file, 'r') as f:
                results = json.load(f)
            
            channels_with_missing_data = results.get('channels', [])
            if not channels_with_missing_data:
                return {"status": "success", "message": "No channels with missing EPG data found in the last scan."}
            
            # Extract channel IDs that need EPG removal
            channel_ids_to_update = [channel['channel_id'] for channel in channels_with_missing_data]
            
            logger.info(f"{PLUGIN_NAME}: Removing EPG assignments from {len(channel_ids_to_update)} channels...")
            
            # Prepare bulk update payload to remove EPG assignments (set epg_data_id to null)
            payload = []
            for channel_id in channel_ids_to_update:
                payload.append({
                    'id': channel_id,
                    'epg_data_id': None  # This removes the EPG assignment
                })
            
            # Perform bulk update via API
            if payload:
                logger.info(f"{PLUGIN_NAME}: Sending bulk update to remove EPG assignments for {len(payload)} channels")
                self._patch_api_data("/api/channels/channels/edit/bulk/", token, payload, settings, logger)
                logger.info(f"{PLUGIN_NAME}: Successfully removed EPG assignments from {len(payload)} channels")
                
                # Trigger M3U refresh to update the GUI
                self._trigger_frontend_refresh(settings, logger)
                
                return {
                    "status": "success",
                    "message": f"Successfully removed EPG assignments from {len(payload)} channels with missing program data.\n\nGUI refresh triggered - the changes should be visible in the interface shortly."
                }
            else:
                return {"status": "success", "message": "No channels needed EPG assignment removal."}
                
        except Exception as e:
            logger.error(f"{PLUGIN_NAME}: Error removing EPG assignments: {str(e)}")
            return {"status": "error", "message": f"Error removing EPG assignments: {str(e)}"}

    def add_bad_epg_suffix_action(self, settings, logger):
        """Add suffix to channels that were found missing program data in the last scan"""
        if not os.path.exists(self.results_file):
            return {"status": "error", "message": "No scan results found. Please run 'Scan for Missing Program Data' first."}

        try:
            # Get API token first
            token, error = self._get_api_token(settings, logger)
            if error:
                return {"status": "error", "message": error}

            bad_epg_suffix = settings.get("bad_epg_suffix", " [BadEPG]")
            if not bad_epg_suffix:
                return {"status": "error", "message": "Please configure a Bad EPG Suffix in the plugin settings."}

            # Check if EPG removal is also requested
            remove_epg_enabled = settings.get("remove_epg_with_suffix", False)

            # Load the last scan results
            with open(self.results_file, 'r') as f:
                results = json.load(f)

            channels_with_missing_data = results.get('channels', [])
            if not channels_with_missing_data:
                return {"status": "success", "message": "No channels with missing EPG data found in the last scan."}

            # Get current channel names via API to ensure we have the latest data
            try:
                all_channels = self._get_api_data("/api/channels/channels/", token, settings, logger)
                channel_id_to_name = {c['id']: c['name'] for c in all_channels}
            except Exception as api_error:
                logger.warning(f"{PLUGIN_NAME}: Could not fetch current channel names via API: {api_error}")
                # Fall back to using names from scan results
                channel_id_to_name = {ch['channel_id']: ch['channel_name'] for ch in channels_with_missing_data}

            # Prepare bulk update payload to add suffix (and optionally remove EPG)
            payload = []
            channels_to_update = []

            for channel in channels_with_missing_data:
                channel_id = channel['channel_id']
                current_name = channel_id_to_name.get(channel_id, channel['channel_name'])

                # Only add suffix if it is not already present
                if not current_name.endswith(bad_epg_suffix):
                    new_name = f"{current_name}{bad_epg_suffix}"
                    update_payload = {
                        'id': channel_id,
                        'name': new_name
                    }

                    # Also remove EPG if enabled
                    if remove_epg_enabled:
                        update_payload['epg_data_id'] = None

                    payload.append(update_payload)
                    channels_to_update.append({
                        'id': channel_id,
                        'old_name': current_name,
                        'new_name': new_name
                    })
                else:
                    logger.info(f"{PLUGIN_NAME}: Channel '{current_name}' already has the suffix, skipping")

            if not payload:
                return {"status": "success", "message": f"No channels needed the suffix '{bad_epg_suffix}' - all channels already have it or no channels found."}

            action_description = f"Adding suffix '{bad_epg_suffix}' to {len(payload)} channels"
            if remove_epg_enabled:
                action_description += " and removing their EPG assignments"
            logger.info(f"{PLUGIN_NAME}: {action_description}...")

            # Perform bulk update via API
            self._patch_api_data("/api/channels/channels/edit/bulk/", token, payload, settings, logger)
            logger.info(f"{PLUGIN_NAME}: Successfully completed bulk update for {len(payload)} channels")

            # Trigger M3U refresh to update the GUI
            self._trigger_frontend_refresh(settings, logger)

            # Create summary message with examples
            message_parts = [
                f"Successfully added suffix '{bad_epg_suffix}' to {len(payload)} channels with missing EPG data."
            ]

            if remove_epg_enabled:
                message_parts[0] += f"\nAlso removed EPG assignments from these {len(payload)} channels."

            message_parts.extend([
                "",
                "Sample renamed channels:"
            ])

            # Show first 5 renamed channels as examples
            for i, channel in enumerate(channels_to_update[:5]):
                message_parts.append(f"• {channel['old_name']} → {channel['new_name']}")

            if len(channels_to_update) > 5:
                message_parts.append(f"... and {len(channels_to_update) - 5} more channels")

            message_parts.append("")
            message_parts.append("GUI refresh triggered - the changes should be visible in the interface shortly.")

            return {
                "status": "success",
                "message": "\n".join(message_parts)
            }

        except Exception as e:
            logger.error(f"{PLUGIN_NAME}: Error adding Bad EPG suffix: {str(e)}")
            return {"status": "error", "message": f"Error adding Bad EPG suffix: {str(e)}"}

    def remove_epg_from_hidden_action(self, settings, logger):
        """Remove EPG data from all hidden/disabled channels in the selected profile and set to dummy EPG"""
        try:
            logger.info(f"{PLUGIN_NAME}: Starting EPG removal from hidden channels...")
            
            # Validate required settings
            channel_profile_name = settings.get("channel_profile_name", "").strip()
            if not channel_profile_name:
                return {
                    "status": "error",
                    "message": "Channel Profile Name is required. Please configure it in settings."
                }
            
            # Get channel profile using Django ORM
            try:
                profile = ChannelProfile.objects.get(name=channel_profile_name)
                profile_id = profile.id
                logger.info(f"{PLUGIN_NAME}: Found profile: {channel_profile_name} (ID: {profile_id})")
            except ChannelProfile.DoesNotExist:
                return {
                    "status": "error",
                    "message": f"Channel profile '{channel_profile_name}' not found"
                }
            
            # Get all channel memberships in this profile that are disabled
            hidden_memberships = ChannelProfileMembership.objects.filter(
                channel_profile_id=profile_id,
                enabled=False
            ).select_related('channel')
            
            if not hidden_memberships.exists():
                return {
                    "status": "success",
                    "message": "No hidden channels found in the selected profile. No EPG data to remove."
                }
            
            hidden_count = hidden_memberships.count()
            logger.info(f"{PLUGIN_NAME}: Found {hidden_count} hidden channels")
            
            # Collect EPG removal results
            results = []
            total_epg_removed = 0
            channels_set_to_dummy = 0
            
            for membership in hidden_memberships:
                channel = membership.channel
                channel_id = channel.id
                channel_name = channel.name or 'Unknown'
                channel_number = channel.channel_number or 'N/A'
                
                # Query EPG data for this channel
                epg_count = 0
                deleted_count = 0
                had_epg = False
                
                if channel.epg_data:
                    had_epg = True
                    epg_count = ProgramData.objects.filter(epg=channel.epg_data).count()
                    
                    if epg_count > 0:
                        # Delete all EPG data for this channel
                        deleted_count = ProgramData.objects.filter(epg=channel.epg_data).delete()[0]
                        total_epg_removed += deleted_count
                        logger.info(f"{PLUGIN_NAME}: Removed {deleted_count} EPG entries from channel {channel_number} - {channel_name}")
                    
                    # Set channel EPG to null (dummy EPG)
                    channel.epg_data = None
                    channel.save()
                    channels_set_to_dummy += 1
                    logger.info(f"{PLUGIN_NAME}: Set channel {channel_number} - {channel_name} to dummy EPG")
                    
                    results.append({
                        'channel_id': channel_id,
                        'channel_name': channel_name,
                        'channel_number': channel_number,
                        'epg_entries_removed': deleted_count,
                        'status': 'set_to_dummy'
                    })
                else:
                    results.append({
                        'channel_id': channel_id,
                        'channel_name': channel_name,
                        'channel_number': channel_number,
                        'epg_entries_removed': 0,
                        'status': 'already_dummy'
                    })
            
            # Export results to CSV
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            csv_filename = f"epg_janitor_removal_{timestamp}.csv"
            csv_filepath = f"/data/exports/{csv_filename}"
            
            os.makedirs("/data/exports", exist_ok=True)
            
            with open(csv_filepath, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['channel_id', 'channel_name', 'channel_number', 'epg_entries_removed', 'status']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for result in results:
                    writer.writerow(result)
            
            logger.info(f"{PLUGIN_NAME}: EPG removal results exported to {csv_filepath}")
            
            # Trigger frontend refresh
            self._trigger_frontend_refresh(settings, logger)
            
            # Build summary message
            message_parts = [
                f"EPG Removal Complete:",
                f"• Hidden channels processed: {hidden_count}",
                f"• Channels set to dummy EPG: {channels_set_to_dummy}",
                f"• Total EPG entries removed: {total_epg_removed}",
                f"• Channels already using dummy EPG: {sum(1 for r in results if r['status'] == 'already_dummy')}",
                f"",
                f"Results exported to: {csv_filepath}",
                f"",
                f"Frontend refresh triggered - GUI should update shortly."
            ]
            
            return {
                "status": "success",
                "message": "\n".join(message_parts),
                "results": {
                    "hidden_channels": hidden_count,
                    "channels_set_to_dummy": channels_set_to_dummy,
                    "total_epg_removed": total_epg_removed,
                    "csv_file": csv_filepath
                }
            }
            
        except Exception as e:
            logger.error(f"{PLUGIN_NAME}: Error removing EPG from hidden channels: {str(e)}")
            import traceback
            logger.error(f"{PLUGIN_NAME}: Traceback: {traceback.format_exc()}")
            return {"status": "error", "message": f"Error removing EPG: {str(e)}"}

    def clear_csv_exports_action(self, settings, logger):
        """Delete all CSV export files created by this plugin"""
        try:
            export_dir = "/data/exports"
            
            if not os.path.exists(export_dir):
                return {
                    "status": "success",
                    "message": "No export directory found. No files to delete."
                }
            
            # Find all CSV files created by this plugin
            deleted_count = 0
            deleted_files = []
            
            for filename in os.listdir(export_dir):
                if filename.startswith("epg_janitor_") and filename.endswith(".csv"):
                    filepath = os.path.join(export_dir, filename)
                    try:
                        os.remove(filepath)
                        deleted_count += 1
                        deleted_files.append(filename)
                        logger.info(f"{PLUGIN_NAME}: Deleted CSV file: {filename}")
                    except Exception as e:
                        logger.warning(f"{PLUGIN_NAME}: Failed to delete {filename}: {e}")
            
            if deleted_count == 0:
                return {
                    "status": "success",
                    "message": "No CSV export files found to delete."
                }

            # Create summary message - show count and sample files for small windows
            if deleted_count <= 3:
                # Show all files if 3 or fewer
                message_parts = [
                    f"✅ Successfully deleted {deleted_count} CSV export file(s):"
                ]
                for filename in deleted_files:
                    message_parts.append(f"• {filename}")
            else:
                # Show summary for more than 3 files
                message_parts = [
                    f"✅ Successfully deleted {deleted_count} CSV export file(s)",
                    f"Sample files: {', '.join(deleted_files[:2])}",
                    f"... and {deleted_count - 2} more"
                ]
            
            return {
                "status": "success",
                "message": "\n".join(message_parts)
            }
            
        except Exception as e:
            logger.error(f"{PLUGIN_NAME}: Error clearing CSV exports: {e}")
            return {"status": "error", "message": f"Error clearing CSV exports: {e}"}


    def remove_epg_by_regex_action(self, settings, logger):
        """Remove EPG assignments from channels in groups where EPG name matches a REGEX."""
        try:
            token, error = self._get_api_token(settings, logger)
            if error:
                return {"status": "error", "message": error}
            
            regex_pattern = settings.get("epg_regex_to_remove", "").strip()
            if not regex_pattern:
                return {"status": "error", "message": "Please provide a REGEX pattern in the settings."}

            try:
                compiled_regex = re.compile(regex_pattern)
            except re.error as e:
                return {"status": "error", "message": f"Invalid REGEX pattern: {e}"}
            
            # Fetch channels that have EPG
            channels_query = Channel.objects.filter(epg_data__isnull=False).select_related('epg_data', 'channel_group', 'epg_data__epg_source')

            # Validate and filter groups
            try:
                channels_query, group_filter_info, groups_used = self._validate_and_filter_groups(
                    settings, logger, channels_query, token
                )
            except ValueError as e:
                return {"status": "error", "message": str(e)}

            channels_to_check = list(channels_query)
            if not channels_to_check:
                return {"status": "success", "message": f"No channels with EPG assignments found{group_filter_info}."}

            channel_ids_to_update = []
            channels_updated_summary = []
            for channel in channels_to_check:
                epg_name = channel.epg_data.name if channel.epg_data else ""
                if epg_name and compiled_regex.search(epg_name):
                    channel_ids_to_update.append(channel.id)
                    channels_updated_summary.append(f"• {channel.name} (EPG: {epg_name})")

            if not channel_ids_to_update:
                return {"status": "success", "message": f"No EPG assignments matched the REGEX '{regex_pattern}'{group_filter_info}."}

            # Prepare and send bulk update
            payload = [{'id': cid, 'epg_data_id': None} for cid in channel_ids_to_update]
            self._patch_api_data("/api/channels/channels/edit/bulk/", token, payload, settings, logger)
            self._trigger_frontend_refresh(settings, logger)

            message_parts = [
                f"Successfully removed EPG assignments from {len(channel_ids_to_update)} channels{group_filter_info} matching REGEX: '{regex_pattern}'",
                "\nChannels affected:"
            ]
            message_parts.extend(channels_updated_summary[:10])
            if len(channels_updated_summary) > 10:
                message_parts.append(f"...and {len(channels_updated_summary) - 10} more.")
            
            message_parts.append("")
            message_parts.append("GUI refresh triggered - the changes should be visible in the interface shortly.")

            return {"status": "success", "message": "\n".join(message_parts)}

        except Exception as e:
            logger.error(f"{PLUGIN_NAME}: Error removing EPG by REGEX: {e}")
            return {"status": "error", "message": f"An error occurred: {e}"}
            
    def remove_all_epg_from_groups_action(self, settings, logger):
        """Remove EPG assignments from ALL channels in the specified groups or all except ignored groups"""
        try:
            # Get API token first
            token, error = self._get_api_token(settings, logger)
            if error:
                return {"status": "error", "message": error}
            
            # Get all channels that have EPG data assigned
            channels_query = Channel.objects.filter(
                epg_data__isnull=False
            ).select_related('epg_data', 'channel_group')
            
            # Validate and filter groups
            try:
                channels_query, group_filter_info, groups_used = self._validate_and_filter_groups(
                    settings, logger, channels_query, token
                )
            except ValueError as e:
                return {"status": "error", "message": str(e)}
            
            channels_with_epg = list(channels_query)
            total_channels = len(channels_with_epg)
            
            if total_channels == 0:
                return {"status": "success", "message": f"No channels with EPG assignments found{group_filter_info}."}
            
            logger.info(f"{PLUGIN_NAME}: Found {total_channels} channels with EPG assignments{group_filter_info}")
            
            # Extract channel IDs that need EPG removal
            channel_ids_to_update = [channel.id for channel in channels_with_epg]
            
            logger.info(f"{PLUGIN_NAME}: Removing EPG assignments from {len(channel_ids_to_update)} channels...")
            
            # Prepare bulk update payload to remove EPG assignments (set epg_data_id to null)
            payload = []
            for channel_id in channel_ids_to_update:
                payload.append({
                    'id': channel_id,
                    'epg_data_id': None  # This removes the EPG assignment
                })
            
            # Perform bulk update via API
            if payload:
                logger.info(f"{PLUGIN_NAME}: Sending bulk update to remove EPG assignments for {len(payload)} channels")
                self._patch_api_data("/api/channels/channels/edit/bulk/", token, payload, settings, logger)
                logger.info(f"{PLUGIN_NAME}: Successfully removed EPG assignments from {len(payload)} channels")
                
                # Trigger M3U refresh to update the GUI
                self._trigger_frontend_refresh(settings, logger)
                
                return {
                    "status": "success",
                    "message": f"Successfully removed EPG assignments from {len(payload)} channels{group_filter_info}.\n\nGUI refresh triggered - the changes should be visible in the interface shortly."
                }
            else:
                return {"status": "success", "message": "No channels needed EPG assignment removal."}
                
        except Exception as e:
            logger.error(f"{PLUGIN_NAME}: Error removing all EPG assignments from groups: {str(e)}")
            return {"status": "error", "message": f"Error removing EPG assignments from groups: {str(e)}"}

    def export_results_action(self, settings, logger):
        """Export results to CSV"""
        if not os.path.exists(self.results_file):
            return {"status": "error", "message": "No results to export. Run 'Scan for Missing Program Data' first."}
        
        try:
            with open(self.results_file, 'r') as f:
                results = json.load(f)
            
            channels = results.get('channels', [])
            if not channels:
                return {"status": "error", "message": "No channel data found in results."}
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"epg_janitor_results_{timestamp}.csv"
            filepath = os.path.join("/data/exports", filename)
            
            # Ensure export directory exists
            os.makedirs("/data/exports", exist_ok=True)
            
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'channel_id',
                    'channel_name', 
                    'channel_number',
                    'channel_group',
                    'epg_channel_id',
                    'epg_channel_name',
                    'epg_source',
                    'scanned_at'
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                for channel in channels:
                    writer.writerow(channel)
            
            logger.info(f"{PLUGIN_NAME}: Results exported to {filepath}")
            
            return {
                "status": "success", 
                "message": f"Results exported to {filepath}\n\nExported {len(channels)} channels with missing EPG data.",
                "file_path": filepath,
                "total_channels": len(channels)
            }
        except Exception as e:
            logger.error(f"{PLUGIN_NAME}: Error exporting CSV: {str(e)}")
            return {"status": "error", "message": f"Error exporting results: {str(e)}"}
    
    def get_summary_action(self, settings, logger):
        """Display summary of last results"""
        if not os.path.exists(self.results_file):
            return {"status": "error", "message": "No results available. Run 'Scan for Missing Program Data' first."}
        
        try:
            with open(self.results_file, 'r') as f:
                results = json.load(f)
            
            channels = results.get('channels', [])
            scan_time = results.get('scan_time', 'Unknown')
            check_hours = results.get('check_hours', 12)
            selected_groups = results.get('selected_groups', '')
            ignore_groups = results.get('ignore_groups', '')
            total_with_epg = results.get('total_channels_with_epg', 0)
            
            # Group by EPG source
            source_summary = {}
            group_summary = {}
            
            for channel in channels:
                source = channel.get('epg_source', 'Unknown')
                group = channel.get('channel_group', 'No Group')
                
                source_summary[source] = source_summary.get(source, 0) + 1
                group_summary[group] = group_summary.get(group, 0) + 1
            
            # Determine group filter info
            if selected_groups:
                group_filter_info = f" (filtered to: {selected_groups})"
            elif ignore_groups:
                group_filter_info = f" (ignoring: {ignore_groups})"
            else:
                group_filter_info = " (all groups)"
            
            message_parts = [
                f"Last EPG scan results:",
                f"• Scan time: {scan_time}",
                f"• Checked timeframe: next {check_hours} hours{group_filter_info}",
                f"• Total channels with EPG: {total_with_epg}",
                f"• Channels missing program data: {len(channels)}"
            ]
            
            if source_summary:
                message_parts.append("\nMissing data by EPG source:")
                for source, count in sorted(source_summary.items(), key=lambda x: x[1], reverse=True):
                    message_parts.append(f"• {source}: {count} channels")
            
            if group_summary:
                message_parts.append("\nMissing data by channel group:")
                for group, count in sorted(group_summary.items(), key=lambda x: x[1], reverse=True)[:5]:
                    message_parts.append(f"• {group}: {count} channels")
                if len(group_summary) > 5:
                    message_parts.append(f"• ... and {len(group_summary) - 5} more groups")
            
            if channels:
                message_parts.append(f"\nUse 'Export Results to CSV' to get the full list of {len(channels)} channels.")
                message_parts.append("Use 'Remove EPG Assignments' to remove EPG from channels with missing data.")
            
            return {
                "status": "success",
                "message": "\n".join(message_parts)
            }
            
        except Exception as e:
            logger.error(f"{PLUGIN_NAME}: Error reading results: {str(e)}")
            return {"status": "error", "message": f"Error reading results: {str(e)}"}

    def validate_settings_action(self, settings, logger):
        """Validate all plugin settings and API connection"""
        validation_results = []
        all_valid = True

        # 1. Validate API Connection
        logger.info(f"{PLUGIN_NAME}: Validating API connection...")
        token, error = self._get_api_token(settings, logger)
        if error:
            validation_results.append(f"❌ API: {error}")
            all_valid = False
            # Cannot proceed with further validation without API access
            return {
                "status": "error",
                "message": "\n".join(validation_results) + "\n\nFix API settings first."
            }
        else:
            validation_results.append("✅ API Connected")

        # 2. Validate Channel Profile Names (if provided)
        channel_profile_name = settings.get("channel_profile_name", "").strip()
        if channel_profile_name:
            profile_names = [name.strip() for name in channel_profile_name.split(",") if name.strip()]
            try:
                # Fetch all available profiles
                profiles_data = self._get_api_data("/api/channels/profiles/", token, settings, logger)
                all_profiles = {p['name']: p for p in profiles_data}
                found_profiles = []
                missing_profiles = []

                for profile_name in profile_names:
                    if profile_name in all_profiles:
                        found_profiles.append(profile_name)
                    else:
                        missing_profiles.append(profile_name)

                if missing_profiles:
                    validation_results.append(f"❌ Profile not found: {', '.join(missing_profiles)}")
                    all_valid = False
                else:
                    profile_list = ', '.join(found_profiles)
                    validation_results.append(f"✅ Profile: {profile_list}")
            except Exception as e:
                validation_results.append(f"❌ Profile error: {str(e)}")
                all_valid = False
        else:
            validation_results.append("ℹ️ Profile: All channels")

        # 3. Validate Channel Groups (if provided)
        selected_groups = settings.get("selected_groups", "").strip()
        ignore_groups = settings.get("ignore_groups", "").strip()

        # Check for conflict between selected_groups and ignore_groups
        if selected_groups and ignore_groups:
            validation_results.append("❌ Groups: Can't use both selected and ignore")
            all_valid = False
        elif selected_groups or ignore_groups:
            groups_to_validate = selected_groups if selected_groups else ignore_groups
            group_type = "Groups" if selected_groups else "Ignore Groups"

            try:
                # Fetch all available groups
                groups_data = self._get_api_data("/api/channels/groups/", token, settings, logger)

                # Extract group names
                all_groups = set()
                for group in groups_data:
                    group_name = group.get('name')
                    if group_name:
                        all_groups.add(group_name)

                # Parse and validate configured groups
                configured_groups = [g.strip() for g in groups_to_validate.split(",") if g.strip()]
                found_groups = []
                missing_groups = []

                for group_name in configured_groups:
                    if group_name in all_groups:
                        found_groups.append(group_name)
                    else:
                        missing_groups.append(group_name)

                if missing_groups:
                    validation_results.append(f"⚠️ {group_type} not found: {', '.join(missing_groups)}")
                    if found_groups:
                        validation_results.append(f"✅ {group_type}: {', '.join(found_groups)}")
                else:
                    group_list = ', '.join(found_groups)
                    validation_results.append(f"✅ {group_type}: {group_list}")
            except Exception as e:
                validation_results.append(f"❌ {group_type} error: {str(e)}")
                all_valid = False
        else:
            validation_results.append("ℹ️ Groups: All groups")

        # 4. Validate Fuzzy Match Threshold
        try:
            fuzzy_threshold = FUZZY_MATCH_THRESHOLD
            if 0 <= fuzzy_threshold <= 100:
                validation_results.append(f"✅ Fuzzy Threshold: {fuzzy_threshold}")
            else:
                validation_results.append(f"❌ Fuzzy Threshold invalid: {fuzzy_threshold}")
                all_valid = False
        except Exception as e:
            validation_results.append(f"❌ Fuzzy Threshold: {str(e)}")
            all_valid = False

        # 5. Validate Fuzzy Matcher Initialization
        try:
            if hasattr(self, 'fuzzy_matcher') and self.fuzzy_matcher is not None:
                validation_results.append(f"✅ Fuzzy Matcher: Ready")
            else:
                validation_results.append("❌ Fuzzy Matcher: Not initialized")
                all_valid = False
        except Exception as e:
            validation_results.append(f"❌ Fuzzy Matcher: {str(e)}")
            all_valid = False

        # 6. Report on Ignore Tags Settings
        ignore_tags_info = []
        if settings.get("ignore_quality_tags", True):
            ignore_tags_info.append("Quality")
        if settings.get("ignore_regional_tags", True):
            ignore_tags_info.append("Regional")
        if settings.get("ignore_geographic_tags", True):
            ignore_tags_info.append("Geographic")
        if settings.get("ignore_misc_tags", True):
            ignore_tags_info.append("Misc")

        if ignore_tags_info:
            validation_results.append(f"ℹ️ Ignore Tags: {', '.join(ignore_tags_info)}")
        else:
            validation_results.append("ℹ️ Ignore Tags: None")

        # 7. Report on other optional settings
        if settings.get("remove_epg_with_suffix", False):
            validation_results.append("ℹ️ Remove EPG with suffix enabled")

        # 8. Validate numeric settings
        check_hours = settings.get("check_hours", 12)
        if 1 <= check_hours <= 168:
            validation_results.append(f"✅ Check Hours: {check_hours}")
        else:
            validation_results.append(f"⚠️ Check Hours out of range: {check_hours}")

        heal_confidence = settings.get("heal_confidence_threshold", 95)
        if 0 <= heal_confidence <= 100:
            validation_results.append(f"✅ Heal Threshold: {heal_confidence}")
        else:
            validation_results.append(f"⚠️ Heal Threshold out of range: {heal_confidence}")

        # Build final message (concise version)
        if all_valid:
            # For success, show only a brief summary
            final_message = "✅ All settings validated successfully. Ready to Load/Process Channels."
        else:
            # For errors, show only the error/warning lines
            error_lines = [line for line in validation_results if line.startswith(("❌", "⚠️"))]
            final_message = "❌ Validation errors:\n" + "\n".join(error_lines) + "\n\nFix errors first."

        return {
            "status": "success" if all_valid else "error",
            "message": final_message
        }

# Additional exports for Dispatcharr plugin system compatibility
plugin = Plugin()
plugin_instance = Plugin()

# Alternative export names in case Dispatcharr looks for these
epg_janitor = Plugin()
EPG_JANITOR = Plugin()

# Export fields and actions for Dispatcharr plugin system
# Note: fields is now a property, so we access it from an instance
fields = plugin.fields
actions = Plugin.actions