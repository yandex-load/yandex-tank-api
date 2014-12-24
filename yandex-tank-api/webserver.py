#!/usr/bin/env python

import logging
import tornado.ioloop
import tornado.web
import os.path
import json
import uuid

import common

from tornado import template
from pyjade.ext.tornado import patch_tornado
patch_tornado()

class JsonHandler(tornado.web.RequestHandler):
    def initialize(self, reportUUID, cacher):
        self.reportUUID = reportUUID
        self.cacher = cacher

    def get(self):
        if self.cacher is not None:
            cached_data = {
              'data': self.cacher.get_all_data(),
              'uuid': self.reportUUID,
            }
        else:
            cached_data = {
              'data':{},
              'uuid': self.reportUUID,
            }
        self.set_status(200)
        self.set_header("Content-type", "application/json")
        self.finish(json.dumps(cached_data))


class ApiServer(object):
    def __init__(self, cacher):
        router = TornadioRouter(Client)
        self.cacher = cacher
        self.reportUUID = uuid.uuid4().hex
        self.app = tornado.web.Application(
            router.apply_routes([
              (r"/data\.json$", JsonHandler, dict(reportUUID=self.reportUUID, cacher=cacher)),
            ]),
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            debug=True,
            )

    def serve(self):
        def run_server(server):
            tornado.ioloop.IOLoop.instance().start()

        self.server = SocketServer(self.app, auto_start = False)
        th = Thread(target=run_server, args=(self.server,))
        th.start()

    def stop(self):
        self.server.stop()


def main(webserver_queue, manager_queue, test_directory):
    """Target for webserver process.
    The only function ever used by the Manager.

    webserver_queue
        Read statuses from Manager here.

    manager_queue
        Write commands for Manager there.

    test_directory
        Directory where tests are

    """
    raise NotImplementedError("Webserver not implemented")

if __name__ == '__main__':
    main()
