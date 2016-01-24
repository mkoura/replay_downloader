import unittest
import os
import replay_downloader as rd


class TestDownloads(unittest.TestCase):
    def test_parse_downloads_list(self):
        l = [' # foo', 'bar', 'http://baz', ' foo1', 'http://bar1 ']
        self.assertEqual(rd.Downloads.parse_downloads_list(l),
                         [rd.Fileinfo(path='bar', type=0),
                          rd.Fileinfo(path='http://baz', type=1),
                          rd.Fileinfo(path='foo1', type=0),
                          rd.Fileinfo(path='http://bar1', type=1)])

    def test_set_destdir(self):
        msg = rd.Msgs()
        conf = rd.Config('test.ini')
        downloads = rd.Downloads(msg, conf)
        destdir = 'destdir'

        downloads.set_destdir(destdir)
        self.assertEqual(downloads.destination, destdir)
        self.assertTrue(os.path.isdir(destdir))
        try:
            os.rmdir(destdir)
        except OSError:
            if os.path.isdir(destdir):
                raise
