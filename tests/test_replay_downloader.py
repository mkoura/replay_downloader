#!/usr/bin/env python3
# encoding: utf-8

import unittest
import os
import replay_downloader as rd


class TestDownloads(unittest.TestCase):
    def test_parse_downloads_list(self):
        l = [' # foo', 'bar', 'http://baz', ' foo1', 'http://bar1 ']
        self.assertEqual(rd.Download.parse_downloads_list(l),
                         [rd.Fileinfo(path='bar', type=rd.Rtypes.RTMP),
                          rd.Fileinfo(path='http://baz', type=rd.Rtypes.HTTP),
                          rd.Fileinfo(path='foo1', type=rd.Rtypes.RTMP),
                          rd.Fileinfo(path='http://bar1', type=rd.Rtypes.HTTP)])

    def test_set_destdir(self):
        msg = rd.Msgs()
        conf = rd.Config('/dev/null')
        downloads = rd.Download(msg, conf)
        destdir = 'destdir'

        downloads.set_destdir(destdir)
        self.assertEqual(downloads.destination, destdir)
        self.assertTrue(os.path.isdir(destdir))
        try:
            os.rmdir(destdir)
        except OSError:
            if os.path.isdir(destdir):
                raise

    def test_get_list_from_file(self):
        os.chdir(os.path.dirname(__file__))
        self.assertEqual(rd.Download.get_list_from_file('test_replay_list'),
                         ['20151205_TS_ChNN_Atiyoga_Teachings_Tashigar_South.mp3',
                          '20151205_TS_ChNN_Atiyoga_Teachings_Tashigar_South_es.mp3',
                          '20151206_TS_ChNN_Atiyoga_Teachings_Tashigar_South.mp3',
                          '20151206_TS_ChNN_Atiyoga_Teachings_Tashigar_South_es.mp3',
                          '',
                          '# TEST',
                          '20151207_TS_ChNN_Atiyoga_Teachings_Tashigar_South.mp3',
                          '20151207_TS_ChNN_Atiyoga_Teachings_Tashigar_South_es_parcial.mp3',
                          '20151208_TS_ChNN_Atiyoga_Teachings_Tashigar_South.mp3'])

    def test_spawn_rtmp(self):
        msg = rd.Msgs()
        conf = rd.Config('/dev/null')
        conf.COMMANDS.rtmpdump = '/bin/true'
        downloads = rd.Download(msg, conf)

        proc = downloads.spawn(rd.Fileinfo('foo', rd.Rtypes.RTMP))
        self.assertEqual(proc, rd.Procinfo(proc.proc_o, 'foo.flv', rd.Ftypes.FLV))

    def test_spawn_http(self):
        msg = rd.Msgs()
        conf = rd.Config('/dev/null')
        conf.COMMANDS.rtmpdump = '/bin/true'
        downloads = rd.Download(msg, conf)

        proc = downloads.spawn(rd.Fileinfo('replay/mp4:20150816.mp4/playlist.m3u8', rd.Rtypes.HTTP))
        self.assertEqual(proc, rd.Procinfo(proc.proc_o, '20150816.mp4', rd.Ftypes.MP4))

    def test_spawn_unknown_type(self):
        msg = rd.Msgs()
        conf = rd.Config('/dev/null')
        conf.COMMANDS.rtmpdump = '/bin/true'
        downloads = rd.Download(msg, conf)

        ret = downloads.spawn(rd.Fileinfo('foo', 20))
        self.assertEqual(ret, None)

    def test_spawn_file_exists(self):
        msg = rd.Msgs()
        conf = rd.Config('/dev/null')
        conf.COMMANDS.rtmpdump = '/bin/true'
        downloads = rd.Download(msg, conf)

        os.chdir(os.path.dirname(__file__))
        ret = downloads.spawn(rd.Fileinfo('existing_file', rd.Rtypes.RTMP))
        self.assertEqual(ret, None)
