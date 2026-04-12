# EPG-Janitor Project Overview

## Purpose
EPG-Janitor is a Dispatcharr plugin that manages Electronic Program Guide (EPG) data for TV channels. It identifies channels with EPG assignments but missing program data (showing "No Program Information Available"), provides auto-matching capabilities, and includes tools for EPG management and cleanup.

## Key Features
- Scans channels with EPG assignments but no program data
- Auto-matches EPG to channels using OTA (Over-The-Air) and regular channel data
- Removes EPG from hidden channels
- Manages EPG assignments with various actions
- Group filtering capabilities
- CSV exports and detailed analytics
- Fuzzy matching for channel name normalization

## Tech Stack
- **Language**: Python 3.13.8
- **Platform**: Windows
- **Framework**: Dispatcharr plugin system
- **Key Dependencies**: Standard Python libraries (logging, json, re, unicodedata, glob, os)

## Repository
https://github.com/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin

## Plugin Configuration
- **Name**: EPG Janitor
- **Key**: epg-janitor
- **Module**: epg_janitor.plugin
- **Class**: Plugin
- **Actions**: run