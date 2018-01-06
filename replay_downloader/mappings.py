# -*- coding: utf-8 -*-
"""
Values mappings.
"""

import collections

from enum import Enum


# extension of file that is not ready yet
PART_EXT = '.part'

# file path, type, class that created the record, audio format, video format
Fileinfo = collections.namedtuple('Fileinfo', 'path type clname audio_f video_f')

# clname, audio_f and video_f are optional
Fileinfo.__new__.__defaults__ = ('', '', '')

# proc is an object returned by Popen, file_record is an instance of FileRecord
Procinfo = collections.namedtuple('Procinfo', 'proc file_record')


class ExitCodes:
    """Exit codes used in main program."""
    SUCCESS = 0
    FAIL = 1
    INCOMPLETE = 2
    INTERRUPTED = 3
    CONFIG = 4


class Rtypes(Enum):
    """Protocols used for downloading the remote file."""
    RTMP = 0
    HTTP = 1


class Ftypes(Enum):
    """File types that we expect and can work with."""
    FLV = 0
    MP3 = 1
    AAC = 2
    MP4 = 3


# mapping of known file types to file extensions
file_ext_d = {
    Ftypes.FLV.name: 'flv',
    Ftypes.MP3.name: 'mp3',
    Ftypes.AAC.name: 'aac',
    Ftypes.MP4.name: 'mp4',
}


class MsgTypes(Enum):
    """Types of message queues."""
    active = 0
    finished = 1
    skipped = 2
    failed = 3
    errors = 4
