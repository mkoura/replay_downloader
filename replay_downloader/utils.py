# -*- coding: utf-8 -*-
"""
Common utility functions.
"""

import os


def remove_ext(filename: str):
    """Removes file extension if it really looks like file extension."""
    fname, fext = os.path.splitext(filename)
    return fname if len(fext) == 4 else fname + fext


def get_list_from_file(list_file: str) -> list:
    """Returns list of lines in file."""
    with open(list_file) as ifl:
        return ifl.read().splitlines()
