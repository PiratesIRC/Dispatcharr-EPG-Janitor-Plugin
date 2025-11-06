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
    version = "0.4.0a"
    description = "Scan for channels with EPG assignments but no program data. Auto-match EPG to channels using OTA and regular channel data."
    
    # Settings rendered by UI
    fields = [
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
            "label": "📺 Channel Profile Name (Optional)",
            "type": "string",
            "default": "",
            "placeholder": "My Profile",
            "help_text": "Only scan/match channels visible in this Channel Profile. Leave blank to scan/match all channels in the group(s).",
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
    ]
    
    # Actions for Dispatcharr UI
    actions = [
        {
            "id": "preview_auto_match",
            "label": "🔍 Preview Auto-Match (Dry Run)",
            "description": "Preview EPG auto-matching results without applying changes. Results exported to CSV.",
        },
        {
            "id": "apply_auto_match",
            "label": "✅ Apply Auto-Match EPG Assignments",
            "description": "Automatically match and assign EPG to channels based on OTA and channel data",
            "confirm": { "required": True, "title": "Apply Auto-Match?", "message": "This will automatically assign EPG data to channels. Existing EPG assignments will be overwritten. Continue?" }
        },
        {
            "id": "scan_missing_epg",
            "label": "🔎 Scan for Missing EPG",
            "description": "Find channels with EPG assignments but no program data",
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
            "description": "Add suffix to channels that were found missing program data in the last scan",
            "confirm": { "required": True, "title": "Add Bad EPG Suffix?", "message": "This will add the configured suffix to channels with missing EPG data. This action is irreversible. Continue?" }
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
    
    def __init__(self):
        self.results_file = "/data/epg_janitor_results.json"
        self.automatch_preview_file = "/data/epg_automatch_preview.csv"
        self.last_results = []
        self.scan_progress = {"current": 0, "total": 0, "status": "idle", "start_time": None}
        self.pending_status_message = None
        self.completion_message = None

        # Initialize fuzzy matcher with channel databases
        plugin_dir = os.path.dirname(__file__)
        self.fuzzy_matcher = FuzzyMatcher(
            plugin_dir=plugin_dir,
            match_threshold=FUZZY_MATCH_THRESHOLD,
            logger=LOGGER
        )

        LOGGER.info(f"{PLUGIN_NAME}: Plugin v{self.version} initialized")


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
            
            # Initialize progress
            self.scan_progress = {"current": 0, "total": total_channels, "status": "running", "start_time": time.time()}
            
            match_results = []
            matched_count = 0
            
            # Process each channel
            for i, channel in enumerate(channels):
                self.scan_progress["current"] = i + 1
                progress_pct = int((i + 1) / total_channels * 100)
                
                # Log progress every 10 channels or at completion
                if (i + 1) % 10 == 0 or (i + 1) == total_channels:
                    logger.info(f"{PLUGIN_NAME}: Auto-match progress: {progress_pct}% ({i + 1}/{total_channels} channels processed)")
                
                matched_name = None
                match_method = None
                confidence_score = 0
                epg_match = None
                extracted_callsign = None

                # Phase 1: Try broadcast (OTA) channel matching by callsign
                callsign, station_data = self.fuzzy_matcher.match_broadcast_channel(channel.name)
                if callsign and station_data:
                    matched_name = callsign
                    match_method = "OTA-Callsign"
                    confidence_score = 100
                    extracted_callsign = callsign

                # Phase 2: If no OTA match, try premium channel fuzzy matching
                if not matched_name and self.fuzzy_matcher.premium_channels:
                    fuzzy_match, score, match_type = self.fuzzy_matcher.fuzzy_match(
                        channel.name,
                        self.fuzzy_matcher.premium_channels
                    )
                    if fuzzy_match:
                        matched_name = fuzzy_match
                        match_method = f"Premium-{match_type}"
                        confidence_score = score

                # Extract callsign for reporting even if no match found
                if not extracted_callsign:
                    extracted_callsign = self.fuzzy_matcher.extract_callsign(channel.name)

                # Phase 3: Search EPG data for matched name
                if matched_name:
                    epg_match = self._search_epg_data(matched_name, epg_data_list, logger)
                    if epg_match:
                        matched_count += 1
                        if (i + 1) % 50 == 0:
                            logger.info(f"{PLUGIN_NAME}: Matched so far: {matched_count} channels")
                    else:
                        # If we matched a channel but didn't find EPG data, clear the match
                        match_method = None
                        matched_name = None
                        confidence_score = 0

                # Store result
                result = {
                    "channel_id": channel.id,
                    "channel_name": channel.name,
                    "channel_number": float(channel.channel_number) if channel.channel_number else None,
                    "channel_group": channel.channel_group.name if channel.channel_group else "No Group",
                    "match_method": match_method or "None",
                    "matched_name": matched_name or "N/A",
                    "confidence_score": confidence_score if confidence_score else 0,
                    "extracted_callsign": extracted_callsign or "N/A",
                    "in_channel_db": "Yes" if matched_name and station_data else "No" if extracted_callsign else "N/A",
                    "epg_source_name": None,
                    "epg_data_id": None,
                    "epg_channel_name": None,
                    "current_epg_id": channel.epg_data.id if channel.epg_data else None,
                    "current_epg_name": channel.epg_data.name if channel.epg_data else None
                }
                
                if epg_match:
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
            
            logger.info(f"{PLUGIN_NAME}: Auto-match completed: {callsigns_extracted} callsigns extracted, {epg_found} EPG matches found out of {total_channels} channels")
            
            # Export results to CSV
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_filename = f"epg_janitor_automatch_{'preview' if dry_run else 'applied'}_{timestamp}.csv"
            csv_filepath = os.path.join("/data/exports", csv_filename)
            os.makedirs("/data/exports", exist_ok=True)
            
            with open(csv_filepath, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'channel_id', 'channel_name', 'channel_number', 'channel_group',
                    'match_method', 'matched_name', 'confidence_score',
                    'extracted_callsign', 'in_channel_db',
                    'epg_source_name', 'epg_data_id', 'epg_channel_name',
                    'current_epg_id', 'current_epg_name'
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
                f"Auto-match {mode_text}: {epg_found}/{total_channels} channels matched to EPG data{group_filter_info}",
                f"• Callsigns extracted: {callsigns_extracted}/{total_channels}",
                f"• EPG data found: {epg_found}/{total_channels}",
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
                message_parts.append("Use 'Apply Auto-Match EPG Assignments' to apply these matches.")
            else:
                message_parts.append("")
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

    def _validate_and_filter_groups(self, settings, logger, channels_query, token):
        """Validate group settings and filter channels accordingly"""
        selected_groups_str = settings.get("selected_groups", "").strip()
        ignore_groups_str = settings.get("ignore_groups", "").strip()
        channel_profile_name = settings.get("channel_profile_name", "").strip()
        
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
        
        # Handle Channel Profile filtering
        if channel_profile_name:
            try:
                logger.info(f"{PLUGIN_NAME}: Filtering by Channel Profile: {channel_profile_name}")
                # Fetch all channel profiles
                profiles = self._get_api_data("/api/channels/profiles/", token, settings, logger)
                
                # Find the matching profile
                profile_id = None
                for profile in profiles:
                    if profile.get('name', '').strip().upper() == channel_profile_name.upper():
                        profile_id = profile.get('id')
                        break
                
                if not profile_id:
                    raise ValueError(f"Channel Profile '{channel_profile_name}' not found. Available profiles: {', '.join([p.get('name', '') for p in profiles])}")
                
                # Fetch the profile details to get visible channel IDs
                profile_details = self._get_api_data(f"/api/channels/profiles/{profile_id}/", token, settings, logger)
                
                # The API returns 'channels' not 'visible_channels'
                visible_channel_ids = profile_details.get('channels', [])
                
                if not visible_channel_ids:
                    raise ValueError(f"Channel Profile '{channel_profile_name}' has no visible channels.")
                
                logger.info(f"{PLUGIN_NAME}: Found {len(visible_channel_ids)} visible channels in profile '{channel_profile_name}'")
                
                # Filter channels to only those visible in the profile
                channels_query = channels_query.filter(id__in=visible_channel_ids)
                
                profile_filter_info = f" in profile '{channel_profile_name}'"
                
            except ValueError as e:
                # Re-raise ValueError for proper error handling
                raise
            except Exception as e:
                logger.error(f"{PLUGIN_NAME}: Error filtering by Channel Profile: {e}")
                import traceback
                logger.error(f"{PLUGIN_NAME}: Traceback: {traceback.format_exc()}")
                raise ValueError(f"Error filtering by Channel Profile '{channel_profile_name}': {e}")
        
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
        
        return channels_query, combined_filter_info, selected_groups_str or ignore_groups_str or channel_profile_name

    def _get_api_token(self, settings, logger):
        """Get an API access token using username and password."""
        dispatcharr_url = settings.get("dispatcharr_url", "").strip().rstrip('/')
        username = settings.get("dispatcharr_username", "")
        password = settings.get("dispatcharr_password", "")

        if not all([dispatcharr_url, username, password]):
            return None, "Dispatcharr URL, Username, and Password must be configured in the plugin settings."

        try:
            url = f"{dispatcharr_url}/api/accounts/token/"
            payload = {"username": username, "password": password}
            
            logger.info(f"{PLUGIN_NAME}: Attempting to authenticate with Dispatcharr at: {url}")
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
            
            logger.info(f"{PLUGIN_NAME}: Successfully obtained API access token")
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

    def run(self, action, params, context):
        """Main plugin entry point"""
        LOGGER.info(f"{PLUGIN_NAME}: run called with action: {action}")
        
        try:
            # Get settings from context
            settings = context.get("settings", {})
            logger = context.get("logger", LOGGER)
            
            action_map = {
                "preview_auto_match": self.preview_auto_match_action,
                "apply_auto_match": self.apply_auto_match_action,
                "scan_missing_epg": self.scan_missing_epg_action,
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
            if action in ["scan_missing_epg", "preview_auto_match", "apply_auto_match"]:
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
            return {"status": "error", "message": "No scan results found. Please run 'Scan for Missing EPG' first."}
        
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
            return {"status": "error", "message": "No scan results found. Please run 'Scan for Missing EPG' first."}
        
        try:
            # Get API token first
            token, error = self._get_api_token(settings, logger)
            if error:
                return {"status": "error", "message": error}
            
            bad_epg_suffix = settings.get("bad_epg_suffix", " [BadEPG]")
            if not bad_epg_suffix:
                return {"status": "error", "message": "Please configure a Bad EPG Suffix in the plugin settings."}
            
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
            
            # Prepare bulk update payload to add suffix
            payload = []
            channels_to_update = []
            
            for channel in channels_with_missing_data:
                channel_id = channel['channel_id']
                current_name = channel_id_to_name.get(channel_id, channel['channel_name'])
                
                # Only add suffix if it is not already present
                if not current_name.endswith(bad_epg_suffix):
                    new_name = f"{current_name}{bad_epg_suffix}"
                    payload.append({
                        'id': channel_id,
                        'name': new_name
                    })
                    channels_to_update.append({
                        'id': channel_id,
                        'old_name': current_name,
                        'new_name': new_name
                    })
                else:
                    logger.info(f"{PLUGIN_NAME}: Channel '{current_name}' already has the suffix, skipping")
            
            if not payload:
                return {"status": "success", "message": f"No channels needed the suffix '{bad_epg_suffix}' - all channels already have it or no channels found."}
            
            logger.info(f"{PLUGIN_NAME}: Adding suffix '{bad_epg_suffix}' to {len(payload)} channels...")
            
            # Perform bulk update via API
            self._patch_api_data("/api/channels/channels/edit/bulk/", token, payload, settings, logger)
            logger.info(f"{PLUGIN_NAME}: Successfully added suffix to {len(payload)} channels")
            
            # Trigger M3U refresh to update the GUI
            self._trigger_frontend_refresh(settings, logger)
            
            # Create summary message with examples
            message_parts = [
                f"Successfully added suffix '{bad_epg_suffix}' to {len(payload)} channels with missing EPG data.",
                "",
                "Sample renamed channels:"
            ]
            
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
            return {"status": "error", "message": "No results to export. Run 'Scan for Missing EPG' first."}
        
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
            return {"status": "error", "message": "No results available. Run 'Scan for Missing EPG' first."}
        
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

# Export fields and actions for Dispatcharr plugin system
fields = Plugin.fields
actions = Plugin.actions

# Additional exports for Dispatcharr plugin system compatibility
plugin = Plugin()
plugin_instance = Plugin()

# Alternative export names in case Dispatcharr looks for these
epg_janitor = Plugin()
EPG_JANITOR = Plugin()