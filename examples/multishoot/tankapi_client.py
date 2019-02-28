import json
import urllib2
import logging
logging.basicConfig(level=logging.DEBUG)


class tankapi_client(object):
    def __init__(self, api_server, api_port=8888):
        self.api_server = api_server
        self.api_port = api_port

    def slurp(self, filename):
        f = open(filename, 'r')
        return f.read()

    def get_as_json(self, url):
        response = urllib2.urlopen(url)
        json_response = response.read()
        logging.debug("API returned %s" % (json_response))
        r = json.loads(json_response)
        return r

    def get_as_str(self, url):
        response = urllib2.urlopen(url)
        str_response = response.read()
        return str_response

    def run_new(self, config_contents, stage='finished'):
        """{"test": test_id, "session": session_id}"""
        url = 'http://%s:%s/run?break=%s' % (
            self.api_server, self.api_port, stage)
        req = urllib2.Request(url, config_contents)
        response = urllib2.urlopen(req)
        json_response = response.read()
        logging.debug("API returned %s" % (json_response))
        r = json.loads(json_response)
        return r

    def run_given(self, session, stage='finished'):
        """{"test": test_id, "session": session_id}"""
        url = 'http://%s:%s/run?session=%s&break=%s' % (
            self.api_server, self.api_port, session, stage)
        r = self.get_as_json(url)
        return r

    def destination_reached(self, session, stage='finished'):
        url = 'http://%s:%s/status?session=%s' % (
            self.api_server, self.api_port, session)
        r = self.get_as_json(url)
        if r['status'] != 'starting' and r['current_stage'] == stage and (
                r['stage_completed'] or r['current_stage'] == 'finished'):
            return True
        return False

    def artifact_list(self, test_id):
        """['filename1', 'filename2', ...]"""
        url = 'http://%s:%s/artifact?test=%s' % (
            self.api_server, self.api_port, test_id)
        # return get_as_json(url) # doesn't work yet

        str_response = self.get_as_str(url)
        logging.debug("API returned %s" % (str_response))
        str_response = str_response.replace('"[', '')
        str_response = str_response.replace(']"', '')
        str_response = str_response.replace(' ', '')
        str_response = str_response.replace('\\"', '')
        files = str_response.split(',')
        return files

    def artifact_store(self, test_id, remote_filename, local_filename):
        url = 'http://%s:%s/artifact?test=%s&filename=%s' % (
            self.api_server, self.api_port, test_id, remote_filename)
        contents = self.get_as_str(url)
        f = open(local_filename, 'w')
        f.write(contents)
