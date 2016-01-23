import unittest
import os
import replay_downloader as rd


class TestDownloads(unittest.TestCase):
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
