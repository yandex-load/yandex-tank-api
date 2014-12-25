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

class RunHandler(tornado.web.RequestHandler):
    def initialize(self, out_queue, sessions):
        self.out_queue = out_queue
        self.sessions = sessions

    def post(self):

        test_id = self.request.arguments.get("test", uuid.uuid4().hex)
        breakpoint = self.request.arguments.get("break", "none")
        session_id = uuid.uuid4().hex
        config = self.request.body

        # TODO: test for existing test with this id
        # TODO: answer 409 if exists finished test
        # TODO: answer 503 if exists and running
        # TODO: answer 503 if other test is running

        # TODO: post run command to manager queue
        print config

        self.set_status(200)
        self.set_header("Content-type", "application/json")
        self.finish(json.dumps(
            {
                "test": test_id,
                "session": session_id,
                "breakpoint": breakpoint,
            }
        ))

    def get(self):
        breakpoint = self.request.arguments.get("break", "none")
        session_id = self.request.arguments.get("session")

        # TODO: find session in db
        # TODO: 404 if no such session
        # TODO: 418 if in higher state
        # TODO: 500 if failed
        # TODO: post run command to manager queue

        self.set_status(200)
        self.set_header("Content-type", "application/json")
        self.finish(json.dumps(
            {
                # "test": test_id,
                "session": session_id,
                "breakpoint": breakpoint,
            }
        ))


class ApiServer(object):
    def __init__(self):
        self.in_queue = None # TODO: pass it as a parameter
        self.out_queue = None # TODO: pass it as a parameter
        self.sessions = {}
        handler_params = dict(out_queue=self.out_queue, sessions=self.sessions)
        self.app = tornado.web.Application(
            [
                (r"/run", RunHandler, handler_params),
                #   (r"/stop", StopHandler),
                #   (r"/status", StatusHandler),
                #   (r"/artifact", ArtifactHandler),
            ],
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            debug=True,
        )

    def serve(self):
        self.app.listen(8888)
        tornado.ioloop.IOLoop.instance().start()


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
    pass

if __name__ == '__main__':
    # main()
    ApiServer().serve()
