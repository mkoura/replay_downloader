# -*- coding: utf-8 -*-
"""
Configuration options.
"""

import configparser
import os


class Config:
    """Configuration options."""
    class CoptsContainer:
        pass

    def __init__(self, cfg_path: str = ''):
        """
        Args:
            cfg_path (str): Path to config file.
        """
        # default values
        self.cfg = configparser.ConfigParser()
        self.cfg['RUN'] = {'concurrency': '3',
                           'destination_dir': '',
                           'work_dir': ''}
        self.cfg['AUTH'] = {'login': '', 'password': ''}
        self.cfg['COMMANDS'] = {'rtmpdump': 'rtmpdump', 'ffmpeg': 'ffmpeg'}
        self.cfg['RTMP'] = {'replay_url': 'http://webcast.dzogchen.net/index.php?id=replay',
                            'login_url': 'http://webcast.dzogchen.net/login-exec.php',
                            'list_regex': r'so.addVariable\(\'file\',\'/([^\']*.mp3)\'\);',
                            'replay_rtmp': 'rtmp://78.129.190.44/replay',
                            'player_url': 'http://webcast.dzogchen.net/player.swf',
                            'referer': 'http://webcast.dzogchen.net/index.php?id=replay'}
        self.cfg['HTTP'] = {'replay_url': 'http://webcast.dzogchen.net/index.php?id=mobilereplay',
                            'login_url': 'http://webcast.dzogchen.net/login-exec.php',
                            'list_regex': r'<a href=\"(http:[^\"]*playlist.m3u8)\"'}

        # read config file and override default values
        if os.path.isfile(cfg_path):
            self.cfg.read(cfg_path)

        # create configuration structure with all config values so that it's
        # independent of specific source of configuration (e.g. ini file)
        # Example: self.RUN.concurrency
        for section in self.cfg.sections():
            setattr(self, section, self.CoptsContainer())
            for key in self.cfg[section]:
                setattr(self.__dict__[section], key, self.cfg[section][key])

        # make sure that concurrency is int
        self.RUN.concurrency = self.cfg.getint('RUN', 'concurrency')


def get_config_file(cmdarg):
    """Finds configuration file."""
    # config file specified on command line
    if cmdarg:
        cflist = (cmdarg, )
    else:
        # otherwise find config file in default locations
        cflist = ('replay_downloader.ini',
                  os.path.expanduser('~/.config/replay_downloader/replay_downloader.ini'))

    config_file = ''
    for cfile in cflist:
        try:
            with open(cfile):
                config_file = cfile
                break
        except EnvironmentError:
            pass

    if not config_file:
        if cmdarg:
            raise EnvironmentError("cannot open config file '{}'".format(cmdarg))
        else:
            raise EnvironmentError("no config file found")

    return Config(config_file)
