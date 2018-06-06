# Moved to https://gitlab.com/mkourim/replay_downloader [![Build Status](https://api.travis-ci.org/mkoura/replay_downloader.svg?branch=master)](https://travis-ci.org/mkoura/replay_downloader)


Downloads list of available replay files and download the actual files from user-supplied list.

Workflow:
- download list of available files
- edit the list (delete lines with files you don't want to download)
- download the files

Works with both classic replay and mobile replay.

Requires `ffmpeg` and `rtpmdump` commands.

Tested on Linux only.

Basic configuration:
- fill in you credentials to the `replay_downloader.ini` config file.
