# -*- coding: utf-8 -*-
"""
Records history of transformations.
"""

from replay_downloader import mappings


class FileRecord:
    """Records complete history of file transformations."""
    def __init__(self, file_info: mappings.Fileinfo):
        self.rec = [file_info]

    def __str__(self):
        return str(self.rec)

    def __len__(self):
        return len(self.rec)

    def __getitem__(self, position):
        return self.rec[position]

    def add(self, file_info: mappings.Fileinfo):
        self.rec.append(file_info)

    def delete(self):
        try:
            self.rec.pop()
        except AttributeError:
            pass
