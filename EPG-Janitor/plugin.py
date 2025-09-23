"""
Dispatcharr EPG Janitor Plugin
Scans for channels with EPG assignments but no program data
"""

import logging
import json
import csv
import os
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
    version = "0.1"
    description = "Scan for channels with EPG assignments but no program data in the next 12 hours (or the time you specify). NOTE: This plugin has READ ONLY access and will require manual intervention by the user."
    
    # Settings rendered by UI
    fields = [
        {
            "id": "check_hours",
            "label": "Hours to Check Ahead",
            "type": "number",
            "default": 12,
            "help_text": "How many hours ahead to check for missing EPG data",
        },
        {
            "id": "selected_groups",
            "label": "Channel Groups to Check (comma-separated)",
            "type": "string",
            "default": "",
            "placeholder": "Sports, News, Entertainment",
            "help_text": "Specific channel groups to check, or leave empty to check all groups. NOTE: Plugin has READ ONLY access.",
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
    ]
    
    def __init__(self):
        self.results_file = "/data/epg_janitor_results.json"
        self.last_results = []
        
        LOGGER.info(f"{self.name} Plugin v{self.version} initialized")

    def run(self, action, params, context):
        """Main plugin entry point"""
        LOGGER.info(f"EPG Janitor run called with action: {action}")
        
        try:
            # Get settings from context
            settings = context.get("settings", {})
            logger = context.get("logger", LOGGER)
            
            if action == "scan_missing_epg":
                return self.scan_missing_epg_action(settings, logger)
            elif action == "export_results":
                return self.export_results_action(settings, logger)
            elif action == "get_summary":
                return self.get_summary_action(settings, logger)
            else:
                return {
                    "status": "error",
                    "message": f"Unknown action: {action}",
                    "available_actions": [
                        "scan_missing_epg", "export_results", "get_summary"
                    ]
                }
        except Exception as e:
            LOGGER.error(f"Error in plugin run: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def scan_missing_epg_action(self, settings, logger):
        """Scan for channels with EPG but no program data"""
        try:
            check_hours = settings.get("check_hours", 12)
            selected_groups_str = settings.get("selected_groups", "").strip()
            now = timezone.now()
            end_time = now + timedelta(hours=check_hours)
            
            logger.info(f"Starting EPG scan for next {check_hours} hours...")
            
            # Get all channels that have EPG data assigned
            channels_query = Channel.objects.filter(
                epg_data__isnull=False
            ).select_related('epg_data', 'channel_group')
            
            # Filter by selected groups if specified
            if selected_groups_str:
                selected_groups = [g.strip() for g in selected_groups_str.split(',') if g.strip()]
                channels_query = channels_query.filter(
                    channel_group__name__in=selected_groups
                )
                logger.info(f"Filtering to groups: {', '.join(selected_groups)}")
            
            channels_with_epg = channels_query
            logger.info(f"Found {channels_with_epg.count()} channels with EPG assignments")
            
            channels_with_no_data = []
            
            # Check each channel for program data in the specified timeframe
            for channel in channels_with_epg:
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
            
            # Save results
            results = {
                "scan_time": datetime.now().isoformat(),
                "check_hours": check_hours,
                "selected_groups": selected_groups_str,
                "total_channels_with_epg": channels_with_epg.count(),
                "channels_missing_data": len(channels_with_no_data),
                "channels": channels_with_no_data
            }
            
            with open(self.results_file, 'w') as f:
                json.dump(results, f, indent=2)
            
            self.last_results = channels_with_no_data
            
            logger.info(f"EPG scan complete. Found {len(channels_with_no_data)} channels with missing program data")
            
            # Create summary message
            group_filter_info = f" in groups: {selected_groups_str}" if selected_groups_str else ""
            
            if channels_with_no_data:
                message_parts = [
                    f"EPG scan completed for next {check_hours} hours{group_filter_info}:",
                    f"• Total channels with EPG: {channels_with_epg.count()}",
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
                message_parts.append("NOTE: Plugin has READ ONLY access - manual intervention required.")
                
            else:
                message_parts = [
                    f"EPG scan completed for next {check_hours} hours{group_filter_info}:",
                    f"• Total channels with EPG: {channels_with_epg.count()}",
                    f"• All channels have program data - no issues found!"
                ]
            
            return {
                "status": "success",
                "message": "\n".join(message_parts),
                "results": {
                    "total_scanned": channels_with_epg.count(),
                    "missing_data": len(channels_with_no_data)
                }
            }
            
        except Exception as e:
            logger.error(f"Error during EPG scan: {str(e)}")
            return {"status": "error", "message": f"Error during EPG scan: {str(e)}"}
    
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
            total_with_epg = results.get('total_channels_with_epg', 0)
            
            # Group by EPG source
            source_summary = {}
            group_summary = {}
            
            for channel in channels:
                source = channel.get('epg_source', 'Unknown')
                group = channel.get('channel_group', 'No Group')
                
                source_summary[source] = source_summary.get(source, 0) + 1
                group_summary[group] = group_summary.get(group, 0) + 1
            
            group_filter_info = f" (filtered to: {selected_groups})" if selected_groups else " (all groups)"
            
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
                message_parts.append("NOTE: Plugin has READ ONLY access - manual intervention required.")
            
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