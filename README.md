# Dispatcharr EPG Janitor Plugin

## Keep your Electronic Program Guide clean, accurate, and complete

> [!TIP]
> **New to Dispatcharr plugins?** Start with the **[Dispatcharr Plugin Workflow guide](https://piratesirc.github.io/Dispatcharr-Plugin-Workflow/)**.
> It explains what each plugin and tool does, where they overlap, and what order to use them in.

[![Dispatcharr plugin](https://img.shields.io/badge/Dispatcharr-plugin-8A2BE2)](https://github.com/Dispatcharr/Dispatcharr)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin)
[![Workflow Guide](https://img.shields.io/badge/%F0%9F%93%96-Workflow_Guide-1F6FEB?style=flat)](https://piratesirc.github.io/Dispatcharr-Plugin-Workflow/workflow/04-epg-janitor/)
[![Discord](https://img.shields.io/badge/Discord-Discussion-5865F2?logo=discord&logoColor=white)](https://discord.gg/Sp45V5BcxU)
[![Sponsor](https://img.shields.io/badge/Sponsor-%E2%9D%A4-db61a2?logo=githubsponsors&logoColor=white)](https://github.com/sponsors/PiratesIRC)

[![GitHub Release](https://img.shields.io/github/v/release/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin?include_prereleases&logo=github)](https://github.com/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin/releases)
[![Downloads](https://img.shields.io/github/downloads/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin/total?color=success&label=Downloads&logo=github)](https://github.com/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin/releases)

![Top Language](https://img.shields.io/github/languages/top/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin)
![Repo Size](https://img.shields.io/github/repo-size/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin)
![Last Commit](https://img.shields.io/github/last-commit/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin)
![License](https://img.shields.io/github/license/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin)

## Warning: back up your database

Before installing or using this plugin, it is **highly recommended** that you
create a backup of your Dispatcharr database. This plugin modifies EPG
assignments on channels and can rename channels.

**[Click here for instructions on how to back up your database.](https://dispatcharr.github.io/Dispatcharr-Docs/troubleshooting/?h=backup#how-can-i-make-a-backup-of-the-database)**

## What it does

Dispatcharr can assign a programme guide to a channel, but nothing checks
whether that assignment actually works. EPG Janitor finds the channels where it
does not, and fixes them.

**Assign a guide to channels that have none.** Auto-match scores every channel
against every eligible EPG entry using two independent methods and takes the
better result: weighted structural signals over US callsign, state, city and
network, and a fuzzy name pipeline running alias lookup, then exact, then
substring, then token-sort comparison. Every run has a preview that writes a CSV
and changes nothing.

**Repair guides that are assigned but empty.** Scan & Heal finds channels whose
EPG assignment carries no actual programme data, searches for a working
replacement among the sources you allow, and only commits one that has real
programme data in the window you set.

**Recognise US over-the-air stations properly.** Callsigns are matched in
parentheses (`ABC (WABC)`), at the end of a name (`WABC-DT`), and in the leading
`CALLSIGN (NETWORK)` form used by feeds such as jesmann-US. A shared
high-confidence callsign anchors the match and a disagreement rejects it. Every
callsign the FCC licenses is shipped with the plugin, so a real station is
recognised even when it is absent from the channel databases, while
callsign-shaped English words such as `KILN` and `WHIP` are not mistaken for
stations.

**Avoid the mistakes that look like successes.** Numbered and time-shifted
siblings do not cross-match, so `Fox Sports 1` does not take `Fox Sports 2`'s
guide and `ITV2` does not take `ITV2 +1`'s. Regional variants route to the
correct regional feed. Number words fold to digits, CamelCase splits, and dotted
compounds split, while radio frequencies are left alone.

**Clean up in bulk.** Remove EPG assignments by regular expression, from hidden
channels, or from whole groups. Tag channels with missing programme data with a
visible suffix. Export any run to CSV with the score, the method and the
reasoning for every row.

**Watch for guides going stale, if you want it.** An optional freshness watchdog
checks every EPG source on a schedule and refreshes any that has errored or is
running out of guide data. It is off by default and writes system events only.

Everything runs inside Dispatcharr against its database directly, so there are
no API credentials to configure. There are no required dependencies.

## Documentation

- **[User guide](docs/USER-GUIDE.md)**: every setting, every action, how matching works, and troubleshooting by symptom
- **[Changelog](docs/CHANGELOG.md)**: what changed in each version
- **[All documentation](docs/README.md)**: the index

**Read [the warning about East to Pacific reassignment](docs/USER-GUIDE.md#foreign-or-wrong-country-epg-on-a-channel)
before your first bulk apply on cable or premium channels.** A channel whose
name carries no regional marker can be moved from an East feed to a Pacific one,
shifting its whole guide by two to three hours.

## Requirements

- Dispatcharr v0.20.0 or newer
- Python 3.13+ (bundled with Dispatcharr)
- No **required** dependencies, standard library only. Optionally uses `rapidfuzz` for faster matching if it happens to be installed in the environment; if absent, a corrected pure-Python scorer computes the identical score

## Installation

1. Download the latest `EPG-Janitor.zip` from the [Releases](https://github.com/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin/releases) page.
2. Log in to Dispatcharr's web UI.
3. Navigate to **Plugins** then **Import Plugin** and upload the zip.
4. Enable the plugin after installation.

### Updating

1. **Remove the old plugin**. Navigate to **Plugins**, click the trash icon next to EPG Janitor, confirm.
2. **Restart Dispatcharr**. Log out, then `docker restart dispatcharr` (or equivalent).
3. **Install the new version**. Log back in, import the new zip, enable.
4. **Your settings are preserved**. Dispatcharr stores plugin settings in its database separately from plugin code. Updates do not clear your configuration.

## Official Plugin Hub

EPG Janitor is published in the [Dispatcharr Plugins](https://github.com/Dispatcharr/Plugins)
official repository, so you can install and update it directly from
Dispatcharr's Plugin Hub without downloading the zip manually.

## Credits

- Fuzzy matching pipeline ported from the [Lineuparr](https://github.com/PiratesIRC/Dispatcharr-Lineuparr-Plugin) plugin
- Weighted structural scoring over callsign, state, city and network is EPG Janitor original
- Alias table seeded from Lineuparr's community-curated channel aliases
- Station callsign data derived from the FCC Licensing and Management System public database

## Sponsor

This plugin is free and always will be. If it saves you time and you would like
to support the work, you can sponsor it at
[github.com/sponsors/PiratesIRC](https://github.com/sponsors/PiratesIRC).

Sponsoring buys no priority, no private support and no influence over what gets
built. Bug reports and pull requests are just as welcome from everyone.

## Contributing

See **[CONTRIBUTING.md](CONTRIBUTING.md)**.

## License

MIT. See [LICENSE](LICENSE).

---

*All product names, trademarks, and registered trademarks mentioned in this project are the property of their respective owners. Channel alias data is community-compiled from publicly available information and is not affiliated with or endorsed by any broadcaster.*
