"""
Dispatcharr EPG Janitor Plugin
Scans for channels with EPG assignments but no program data
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

# Django model imports
from apps.channels.models import Channel
from apps.epg.models import ProgramData

# Setup logging using Dispatcharr's format
LOGGER = logging.getLogger("plugins.epg_janitor")
if not LOGGER.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(levelname)s %(name)s %(message)s")
    handler.setFormatter(formatter)
    LOGGER.addHandler(handler)
LOGGER.setLevel(logging.INFO)

class Plugin:
    """Dispatcharr EPG Janitor Plugin"""
    
    name = "EPG Janitor"
    version = "0.2.1"
    description = "Scan for channels with EPG assignments but no program data in the next 12 hours (or the time you specify). Includes option to remove EPG assignments from problematic channels."
    
    # Settings rendered by UI
    fields = [
        {
            "id": "dispatcharr_url",
            "label": "Dispatcharr URL",
            "type": "string",
            "default": "",
            "placeholder": "http://192.168.1.10:9191",
            "help_text": "URL of your Dispatcharr instance (from your browser's address bar). Example: http://127.0.0.1:9191",
        },
        {
            "id": "dispatcharr_username",
            "label": "Dispatcharr Admin Username",
            "type": "string",
            "help_text": "Your admin username for the Dispatcharr UI. Required for API access.",
        },
        {
            "id": "dispatcharr_password",
            "label": "Dispatcharr Admin Password",
            "type": "string",
            "input_type": "password",
            "help_text": "Your admin password for the Dispatcharr UI. Required for API access.",
        },
        {
            "id": "check_hours",
            "label": "Hours to Check Ahead",
            "type": "number",
            "default": 12,
            "help_text": "How many hours ahead to check for missing EPG data",
        },
        {
            "id": "selected_groups",
            "label": "Channel Groups (comma-separated)",
            "type": "string",
            "default": "",
            "placeholder": "Sports, News, Entertainment",
            "help_text": "Specific channel groups to check or remove EPG from, or leave empty for all groups. Must be blank if using 'Ignore Groups' below.",
        },
        {
            "id": "ignore_groups",
            "label": "Ignore Groups (comma-separated)",
            "type": "string",
            "default": "",
            "placeholder": "Premium Sports, Kids",
            "help_text": "Channel groups to exclude from operations. Works on all groups except these. Requires 'Channel Groups' field above to be blank.",
        },
        {
            "id": "epg_regex_to_remove",
            "label": "EPG Name REGEX to Remove",
            "type": "string",
            "default": "",
            "placeholder": "e.g., (US)$|\\[BACKUP\\]",
            "help_text": "A regular expression to match against EPG channel names within the specified groups. Matching EPG assignments will be removed.",
        },
        {
            "id": "bad_epg_suffix",
            "label": "Bad EPG Suffix",
            "type": "string",
            "default": " [BadEPG]",
            "placeholder": " [BadEPG]",
            "help_text": "Suffix to add to channels with missing EPG program data.",
        },
    ]
    
    # Actions for Dispatcharr UI
    actions = [
        {
            "id": "scan_missing_epg",
            "label": "Scan for Missing EPG",
            "description": "Find channels with EPG assignments but no program data",
        },
        {
            "id": "export_results",
            "label": "Export Results to CSV",
            "description": "Export the last scan results to a CSV file",
        },
        {
            "id": "get_summary",
            "label": "View Last Results",
            "description": "Display summary of the last EPG scan results",
        },
        {
            "id": "remove_epg_assignments",
            "label": "Remove EPG Assignments",
            "description": "Remove EPG assignments from channels that were found missing program data in the last scan",
            "confirm": { "required": True, "title": "Remove EPG Assignments?", "message": "This will remove EPG assignments from channels with missing program data. This action is irreversible. Continue?" }
        },
        {
            "id": "remove_epg_by_regex",
            "label": "Remove EPG Assignments matching REGEX within Group(s)",
            "description": "Removes EPG from channels in the specified groups if the EPG name matches the REGEX.",
            "confirm": { "required": True, "title": "Remove EPG Assignments by REGEX?", "message": "This will remove EPG assignments from channels in the specified groups where the EPG name matches the REGEX. This action is irreversible. Continue?" }
        },
        {
            "id": "remove_all_epg_from_groups",
            "label": "Remove ALL EPG Assignments from Group(s)",
            "description": "Removes EPG from all channels in the group(s) specified in 'Channel Groups' or all except 'Ignore Groups'",
            "confirm": { "required": True, "title": "Remove ALL EPG Assignments?", "message": "This will remove EPG assignments from ALL channels in the specified groups, regardless of whether they have program data. This action is irreversible. Continue?" }
        },
        {
            "id": "add_bad_epg_suffix",
            "label": "Add Bad EPG Suffix to Channels",
            "description": "Add suffix to channels that were found missing program data in the last scan",
            "confirm": { "required": True, "title": "Add Bad EPG Suffix?", "message": "This will add the configured suffix to channels with missing EPG data. This action is irreversible. Continue?" }
        },
    ]
    
    def __init__(self):
        self.results_file = "/data/epg_janitor_results.json"
        self.last_results = []
        self.scan_progress = {"current": 0, "total": 0, "status": "idle", "start_time": None}
        self.pending_status_message = None
        self.completion_message = None
        
        LOGGER.info(f"{self.name} Plugin v{self.version} initialized")

    def _validate_and_filter_groups(self, settings, logger, channels_query, token):
        """Validate group settings and filter channels accordingly"""
        selected_groups_str = settings.get("selected_groups", "").strip()
        ignore_groups_str = settings.get("ignore_groups", "").strip()
        
        # Validation: both cannot be used together
        if selected_groups_str and ignore_groups_str:
            raise ValueError("Cannot use both 'Channel Groups' and 'Ignore Groups' at the same time. Please use only one.")
        
        # Try to get channel groups via API first
        try:
            logger.info("Attempting to fetch channel groups via API...")
            api_groups = self._get_api_data("/api/channels/groups/", token, settings, logger)
            logger.info(f"Successfully fetched {len(api_groups)} groups via API")
            group_name_to_id = {g['name']: g['id'] for g in api_groups if 'name' in g and 'id' in g}
        except Exception as api_error:
            logger.warning(f"API request failed, falling back to Django ORM: {api_error}")
            group_name_to_id = {}
        
        group_filter_info = ""
        
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
            
            logger.info(f"Filtering to groups: {', '.join(selected_groups)}")
            group_filter_info = f" in groups: {', '.join(selected_groups)}"
        
        # Handle ignore groups (exclude these)
        elif ignore_groups_str:
            ignore_groups = [g.strip() for g in ignore_groups_str.split(',') if g.strip()]
            if group_name_to_id:
                ignore_group_ids = [group_name_to_id[name] for name in ignore_groups if name in group_name_to_id]
                if ignore_group_ids:
                    channels_query = channels_query.exclude(channel_group_id__in=ignore_group_ids)
                else:
                    logger.warning(f"None of the ignore groups were found: {', '.join(ignore_groups)}")
            else:
                channels_query = channels_query.exclude(channel_group__name__in=ignore_groups)
            
            logger.info(f"Ignoring groups: {', '.join(ignore_groups)}")
            group_filter_info = f" (ignoring: {', '.join(ignore_groups)})"
        
        return channels_query, group_filter_info, selected_groups_str or ignore_groups_str

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
            
            logger.info(f"Attempting to authenticate with Dispatcharr at: {url}")
            response = requests.post(url, json=payload, timeout=15)

            if response.status_code == 401:
                logger.error("Authentication failed - invalid credentials")
                return None, "Authentication failed. Please check your username and password in the plugin settings."
            elif response.status_code == 404:
                logger.error(f"API endpoint not found - check Dispatcharr URL: {dispatcharr_url}")
                return None, f"API endpoint not found. Please verify your Dispatcharr URL: {dispatcharr_url}"
            elif response.status_code >= 500:
                logger.error(f"Server error from Dispatcharr: {response.status_code}")
                return None, f"Dispatcharr server error ({response.status_code}). Please check if Dispatcharr is running properly."
            
            response.raise_for_status()
            token_data = response.json()
            access_token = token_data.get("access")

            if not access_token:
                logger.error("No access token returned from API")
                return None, "Login successful, but no access token was returned by the API."
            
            logger.info("Successfully obtained API access token")
            return access_token, None
            
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error: {e}")
            return None, f"Unable to connect to Dispatcharr at {dispatcharr_url}. Please check the URL and ensure Dispatcharr is running."
        except requests.exceptions.Timeout as e:
            logger.error(f"Request timeout: {e}")
            return None, "Request timed out while connecting to Dispatcharr. Please check your network connection."
        except requests.RequestException as e:
            logger.error(f"Request error: {e}")
            return None, f"Network error occurred while authenticating: {e}"
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response: {e}")
            return None, "Invalid response from Dispatcharr API. Please check if the URL is correct."
        except Exception as e:
            logger.error(f"Unexpected error during authentication: {e}")
            return None, f"Unexpected error during authentication: {e}"

    def _get_api_data(self, endpoint, token, settings, logger):
        """Helper to perform GET requests to the Dispatcharr API."""
        dispatcharr_url = settings.get("dispatcharr_url", "").strip().rstrip('/')
        url = f"{dispatcharr_url}{endpoint}"
        headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
        
        try:
            logger.info(f"Making API request to: {endpoint}")
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 401:
                logger.error("API token expired or invalid")
                raise Exception("API authentication failed. Token may have expired.")
            elif response.status_code == 403:
                logger.error("API access forbidden")
                raise Exception("API access forbidden. Check user permissions.")
            elif response.status_code == 404:
                logger.error(f"API endpoint not found: {endpoint}")
                raise Exception(f"API endpoint not found: {endpoint}")
            
            response.raise_for_status()
            json_data = response.json()
            
            if isinstance(json_data, dict):
                return json_data.get('results', json_data)
            elif isinstance(json_data, list):
                return json_data
            return []
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed for {endpoint}: {e}")
            raise Exception(f"API request failed: {e}")

    def _post_api_data(self, endpoint, token, payload, settings, logger):
        """Helper to perform POST requests to the Dispatcharr API."""
        dispatcharr_url = settings.get("dispatcharr_url", "").strip().rstrip('/')
        url = f"{dispatcharr_url}{endpoint}"
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        
        try:
            logger.info(f"Making API POST request to: {endpoint}")
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 401:
                logger.error("API token expired or invalid")
                raise Exception("API authentication failed. Token may have expired.")
            elif response.status_code == 403:
                logger.error("API access forbidden")
                raise Exception("API access forbidden. Check user permissions.")
            elif response.status_code == 404:
                logger.error(f"API endpoint not found: {endpoint}")
                raise Exception(f"API endpoint not found: {endpoint}")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API POST request failed for {endpoint}: {e}")
            raise Exception(f"API POST request failed: {e}")

    def _patch_api_data(self, endpoint, token, payload, settings, logger):
        """Helper to perform PATCH requests to the Dispatcharr API."""
        dispatcharr_url = settings.get("dispatcharr_url", "").strip().rstrip('/')
        url = f"{dispatcharr_url}{endpoint}"
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        
        try:
            logger.info(f"Making API PATCH request to: {endpoint}")
            response = requests.patch(url, headers=headers, json=payload, timeout=60)
            
            if response.status_code == 401:
                logger.error("API token expired or invalid")
                raise Exception("API authentication failed. Token may have expired.")
            elif response.status_code == 403:
                logger.error("API access forbidden")
                raise Exception("API access forbidden. Check user permissions.")
            elif response.status_code == 404:
                logger.error(f"API endpoint not found: {endpoint}")
                raise Exception(f"API endpoint not found: {endpoint}")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API PATCH request failed for {endpoint}: {e}")
            raise Exception(f"API PATCH request failed: {e}")

    def _trigger_m3u_refresh(self, token, settings, logger):
        """Triggers a global M3U refresh to update the GUI via WebSockets."""
        logger.info("Triggering M3U refresh to update the GUI...")
        try:
            self._post_api_data("/api/m3u/refresh/", token, {}, settings, logger)
            logger.info("M3U refresh triggered successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to trigger M3U refresh: {e}")
            return False

    def run(self, action, params, context):
        """Main plugin entry point"""
        LOGGER.info(f"EPG Janitor run called with action: {action}")
        
        try:
            # Get settings from context
            settings = context.get("settings", {})
            logger = context.get("logger", LOGGER)
            
            action_map = {
                "scan_missing_epg": self.scan_missing_epg_action,
                "export_results": self.export_results_action,
                "get_summary": self.get_summary_action,
                "remove_epg_assignments": self.remove_epg_assignments_action,
                "remove_epg_by_regex": self.remove_epg_by_regex_action,
                "remove_all_epg_from_groups": self.remove_all_epg_from_groups_action,
                "add_bad_epg_suffix": self.add_bad_epg_suffix_action,
            }
            
            if action not in action_map:
                return {
                    "status": "error",
                    "message": f"Unknown action: {action}",
                    "available_actions": list(action_map.keys())
                }
            
            # Pass context to actions that need it
            if action in ["scan_missing_epg"]:
                return action_map[action](settings, logger, context)
            else:
                return action_map[action](settings, logger)
                
        except Exception as e:
            self.scan_progress['status'] = 'idle'
            LOGGER.error(f"Error in plugin run: {str(e)}")
            return {"status": "error", "message": str(e)}

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
            
            logger.info(f"Starting EPG scan for next {check_hours} hours...")
            
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
            logger.info(f"Found {total_channels} channels with EPG assignments")
            
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
            
            logger.info(f"EPG scan complete. Found {len(channels_with_no_data)} channels with missing program data")
            
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
            logger.error(f"Error during EPG scan: {str(e)}")
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
            
            logger.info(f"Removing EPG assignments from {len(channel_ids_to_update)} channels...")
            
            # Prepare bulk update payload to remove EPG assignments (set epg_data_id to null)
            payload = []
            for channel_id in channel_ids_to_update:
                payload.append({
                    'id': channel_id,
                    'epg_data_id': None  # This removes the EPG assignment
                })
            
            # Perform bulk update via API
            if payload:
                logger.info(f"Sending bulk update to remove EPG assignments for {len(payload)} channels")
                self._patch_api_data("/api/channels/channels/edit/bulk/", token, payload, settings, logger)
                logger.info(f"Successfully removed EPG assignments from {len(payload)} channels")
                
                # Trigger M3U refresh to update the GUI
                self._trigger_m3u_refresh(token, settings, logger)
                
                return {
                    "status": "success",
                    "message": f"Successfully removed EPG assignments from {len(payload)} channels with missing program data.\n\nGUI refresh triggered - the changes should be visible in the interface shortly."
                }
            else:
                return {"status": "success", "message": "No channels needed EPG assignment removal."}
                
        except Exception as e:
            logger.error(f"Error removing EPG assignments: {str(e)}")
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
                logger.warning(f"Could not fetch current channel names via API: {api_error}")
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
                    logger.info(f"Channel '{current_name}' already has the suffix, skipping")
            
            if not payload:
                return {"status": "success", "message": f"No channels needed the suffix '{bad_epg_suffix}' - all channels already have it or no channels found."}
            
            logger.info(f"Adding suffix '{bad_epg_suffix}' to {len(payload)} channels...")
            
            # Perform bulk update via API
            self._patch_api_data("/api/channels/channels/edit/bulk/", token, payload, settings, logger)
            logger.info(f"Successfully added suffix to {len(payload)} channels")
            
            # Trigger M3U refresh to update the GUI
            self._trigger_m3u_refresh(token, settings, logger)
            
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
            logger.error(f"Error adding Bad EPG suffix: {str(e)}")
            return {"status": "error", "message": f"Error adding Bad EPG suffix: {str(e)}"}

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
            self._trigger_m3u_refresh(token, settings, logger)

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
            logger.error(f"Error removing EPG by REGEX: {e}")
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
            
            logger.info(f"Found {total_channels} channels with EPG assignments{group_filter_info}")
            
            # Extract channel IDs that need EPG removal
            channel_ids_to_update = [channel.id for channel in channels_with_epg]
            
            logger.info(f"Removing EPG assignments from {len(channel_ids_to_update)} channels...")
            
            # Prepare bulk update payload to remove EPG assignments (set epg_data_id to null)
            payload = []
            for channel_id in channel_ids_to_update:
                payload.append({
                    'id': channel_id,
                    'epg_data_id': None  # This removes the EPG assignment
                })
            
            # Perform bulk update via API
            if payload:
                logger.info(f"Sending bulk update to remove EPG assignments for {len(payload)} channels")
                self._patch_api_data("/api/channels/channels/edit/bulk/", token, payload, settings, logger)
                logger.info(f"Successfully removed EPG assignments from {len(payload)} channels")
                
                # Trigger M3U refresh to update the GUI
                self._trigger_m3u_refresh(token, settings, logger)
                
                return {
                    "status": "success",
                    "message": f"Successfully removed EPG assignments from {len(payload)} channels{group_filter_info}.\n\nGUI refresh triggered - the changes should be visible in the interface shortly."
                }
            else:
                return {"status": "success", "message": "No channels needed EPG assignment removal."}
                
        except Exception as e:
            logger.error(f"Error removing all EPG assignments from groups: {str(e)}")
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
            
            logger.info(f"Results exported to {filepath}")
            
            return {
                "status": "success", 
                "message": f"Results exported to {filepath}\n\nExported {len(channels)} channels with missing EPG data.",
                "file_path": filepath,
                "total_channels": len(channels)
            }
        except Exception as e:
            logger.error(f"Error exporting CSV: {str(e)}")
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
            logger.error(f"Error reading results: {str(e)}")
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