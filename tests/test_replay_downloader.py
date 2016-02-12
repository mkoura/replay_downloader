#!/usr/bin/env python3
# encoding: utf-8

import unittest
import os
import time
import replay_downloader as rd


class TestDownloads(unittest.TestCase):
    def test_parse_todownload_list(self):
        l = [' # foo', 'bar', 'http://baz', ' foo1', 'http://bar1 ']
        self.assertEqual(rd.Download.parse_todownload_list(l),
                         [rd.Fileinfo(path='bar', type=rd.Rtypes.RTMP),
                          rd.Fileinfo(path='http://baz', type=rd.Rtypes.HTTP),
                          rd.Fileinfo(path='foo1', type=rd.Rtypes.RTMP),
                          rd.Fileinfo(path='http://bar1', type=rd.Rtypes.HTTP)])

    def test_set_destdir(self):
        conf = rd.Config()
        downloads = rd.Download(conf, [])
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
        self.assertEqual(rd.get_list_from_file('test_replay_list'),
                         ['20151205_TS_ChNN_Atiyoga_Teachings_Tashigar_South.mp3',
                          '20151205_TS_ChNN_Atiyoga_Teachings_Tashigar_South_es.mp3',
                          '20151206_TS_ChNN_Atiyoga_Teachings_Tashigar_South.mp3',
                          '20151206_TS_ChNN_Atiyoga_Teachings_Tashigar_South_es.mp3',
                          '',
                          '# TEST',
                          '20151207_TS_ChNN_Atiyoga_Teachings_Tashigar_South.mp3',
                          '20151207_TS_ChNN_Atiyoga_Teachings_Tashigar_South_es_parcial.mp3',
                          '20151208_TS_ChNN_Atiyoga_Teachings_Tashigar_South.mp3'])

    def test_spawn_http(self):
        conf = rd.Config()
        conf.COMMANDS.rtmpdump = '/bin/true'
        downloads = rd.Download(conf, [])

        proc = downloads.spawn(rd.Fileinfo('replay/mp4:20150816.mp4/playlist.m3u8',
                               rd.Rtypes.HTTP))
        self.assertEqual(proc, rd.Procinfo(proc.proc_o, '20150816.mp4',
                         rd.Ftypes.MP4))

    def test_spawn_unknown_type(self):
        conf = rd.Config()
        conf.COMMANDS.rtmpdump = '/bin/true'
        downloads = rd.Download(conf, [])

        ret = downloads.spawn(rd.Fileinfo('foo', 20))
        self.assertEqual(ret, None)

    def test_spawn_file_exists(self):
        conf = rd.Config()
        conf.COMMANDS.rtmpdump = '/bin/true'
        downloads = rd.Download(conf, [])

        os.chdir(os.path.dirname(__file__))
        ret = downloads.spawn(rd.Fileinfo('existing_file', rd.Rtypes.RTMP))
        self.assertEqual(ret, None)

    def test_finished_rtmp(self):
        conf = rd.Config()
        conf.COMMANDS.rtmpdump = '/bin/true'
        downloads = rd.Download(conf, [])

        proc = downloads.spawn(rd.Fileinfo('foo', rd.Rtypes.RTMP))
        self.assertEqual(proc, rd.Procinfo(proc.proc_o, 'foo.flv',
                                           rd.Ftypes.FLV))
        while (proc.proc_o.proc.poll() is None):
            time.sleep(0.05)

        ret = downloads.finished_handler(proc)
        self.assertEqual(ret, 0)
        self.assertEqual(downloads.out[rd.MsgTypes.finished].msglist[0][0], 'foo.flv')
        self.assertEqual(downloads.finished_ready[0],
                         rd.Fileinfo('foo.flv', rd.Ftypes.FLV))


class TestDecodings(unittest.TestCase):
    def test_set_destdir(self):
        conf = rd.Config()
        decodings = rd.Decode(conf, [])
        destdir = 'destdir'

        decodings.set_destdir(destdir)
        self.assertEqual(decodings.destination, destdir)
        self.assertTrue(os.path.isdir(destdir))
        try:
            os.rmdir(destdir)
        except OSError:
            if os.path.isdir(destdir):
                raise

    def test_spawn(self):
        conf = rd.Config()
        conf.COMMANDS.ffmpeg = '/bin/true'
        decodings = rd.Decode(conf, [])

        proc = decodings.spawn(rd.Fileinfo('20150816.mp3.flv',
                               rd.Ftypes.FLV))
        self.assertEqual(proc, rd.Procinfo(proc.proc_o, '20150816.mp3',
                         rd.Ftypes.MP3))

    def test_spawn_unknown_type(self):
        conf = rd.Config()
        conf.COMMANDS.ffmpeg = '/bin/true'
        decodings = rd.Decode(conf, [])

        ret = decodings.spawn(rd.Fileinfo('20150816.mp3', 'mp3'))
        self.assertEqual(ret, None)

    def test_spawn_file_exists(self):
        conf = rd.Config()
        conf.COMMANDS.ffmpeg = '/bin/true'
        decodings = rd.Decode(conf, [])

        os.chdir(os.path.dirname(__file__))
        ret = decodings.spawn(rd.Fileinfo('existing_file.flv.flv', rd.Ftypes.FLV))
        self.assertEqual(ret, None)
