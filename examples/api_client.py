import json
import requests


class TankAPIClient(object):
    def __init__(self, api_address, api_port=8888):
        self.api_address = api_address
        self.api_port = api_port

    def run(self, config, breakpoint='finish', test_id=None):
        req = "http://{api_address}:{api_port}/run?break={breakpoint}".format(
            api_address=self.api_address,
            api_port=self.api_port,
            breakpoint=breakpoint, )
        if test_id:
            req += "&test=%s" % test_id
        resp = requests.post(req, data=config)
        if resp.status_code == 200:
            data = json.loads(resp.text)
            return data
        else:
            print resp.text
            return None

    def resume(self, session_id, breakpoint='finish'):
        req = "http://{api_address}:{api_port}/run?break={breakpoint}&session={session}".format(
            api_address=self.api_address,
            api_port=self.api_port,
            breakpoint=breakpoint,
            session=session_id, )
        resp = requests.get(req)
        if resp.status_code == 200:
            data = json.loads(resp.text)
            return data
        else:
            print resp.text
            return None

    def stop(self, session_id):
        req = "http://{api_address}:{api_port}/stop?session={session}".format(
            api_address=self.api_address,
            api_port=self.api_port,
            session=session_id)
        resp = requests.get(req)
        if resp.status_code == 200:
            data = json.loads(resp.text)
            return data
        else:
            print resp.text
            return None

    def list_artifacts(self, test_id):
        req = "http://{api_address}:{api_port}/artifact?test={test}".format(
            api_address=self.api_address, api_port=self.api_port, test=test_id)
        resp = requests.get(req)
        if resp.status_code == 200:
            data = json.loads(resp.text)
            return data
        else:
            print resp.text
            return None

    def get_artifact(self, test_id, filename):
        req = "http://{api_address}:{api_port}/artifact?test={test}&filename={filename}".format(
            api_address=self.api_address,
            api_port=self.api_port,
            test=test_id,
            filename=filename, )
        resp = requests.get(req)
        if resp.status_code == 200:
            data = resp.text
            return data
        else:
            print resp.text
            return None

    def status(self, session_id=None):
        req = "http://{api_address}:{api_port}/status".format(
            api_address=self.api_address,
            api_port=self.api_port, )
        if session_id:
            req += "?%s" % session_id
        resp = requests.get(req)
        if resp.status_code == 200:
            data = json.loads(resp.text)
            return data
        else:
            print resp.text
            return None
