Yandex.Tank API
===============

This is an HTTP server that controls Yandex.Tank execution. It allows the client to:

* set a breakpoint before an arbitrary test stage (and reset it later)
* launch Yandex.Tank and begin the test
* upload files into the test working directory
* terminate the launched Tank at an arbitrary moment
* obtain the test status
* download the artifacts in a safe manner, without interference to another tests

Start API server
----------------
by running ```yandex-tank-api-server [options...]``` in console


API-managed Tank
------------------

General information on Yandex.Tank installation and usage can be found in its [documentation](http://yandextank.readthedocs.org).
This section covers the difference between console Tank and API-managed Tank configuration and provides more details on the sequence of the test stages.

### Tank configuration

API-managed Tank is configured via configuration files only. They have the same syntax and options as the console Tank configs.

The configuration parameters are applied in the following order:

  1. common Yandex.Tank configuration files that reside in `/etc/yandex-tank/`
  2. Yandex.Tank API defaults in `/etc/yandex-tank-api/defaults`
  3. **the configuration file sent by the client when launching the test**
  4. Yandex.Tank API overriding configs in `/etc/yandex-tank-api/override`

### Test stages

When the client launches a new test, a new *session* is created and a separate *Tank worker* process is spawned. After this, the test stages are executed in the following order:
  1. **lock**

     Attempt to acquire the tank lock. This stage fails if another test started via console is running.

  2. **init**

     Logging is set up and tank configuration files are read at this stage.

  3. **configure**

     The *configure()* method is called for each module. Most of the dynamic configuration is done here.

  4. **prepare**

     The *prepare_test()* method is called for each module. Heavy and time-consuming tasks (such as stpd-file generation and monitoring agent setup) are done here.

  5. **start**

     The *start_test()* method is called for each module. This should take as little time as possible. Load generation begins at this moment.

  6. **poll**

     Once per second the *is_test_finished()* method is called for each module. This stage ends when any of the modules requests to stop the test.

  7. **end**

     The *end_test()* method is called for each module. This should take as little time as possible.

  8. **postprocess**

     The *post_process()* method is called for each module. Heavy and time-consuming tasks are performed here.

  9. **unlock**

     The tank lock is released and the Tank worker exits.

  10. **finished**

     This is a virtual stage. Reaching this stage means that the Tank worker has already terminated.

The last session status is temporarily stored after tank exit.
The test artifacts are stored forever and should be deleted by external means when not needed.

### Pausing the test sequence

When the session is started, the client can specify the test stage before which the test will be paused (the breakpoint) .
After completing the stages preceding the breakpoint, the Tank will wait until the breakpoint is moved further. You cannot move the breakpoint back.

The breakpoint can be set *before* any stage. One of the most frequent use cases is to set the breakpoint before the **start** stage to synchronize several tanks.
Another is setting the breakpoint before the unlock stage to download the artifacts without interference to other tests.
Third is setting the breakpoint before the init stage to upload additional files.
Beware that setting the breakpoint between the **init** and the **poll** stages can lead to very exotic behaviour.

API requests
-----------

All API requests are asynchronous: we do not wait the tank process to perform requested action.
HTTP code 200 is returned when no error occured while processing the request.
However, this does not necessarily mean that the requested action will be successfully performed.
The client should check the session status to detect Tank failures.

All handles, except for /artifact, return JSON. On errors this is a JSON object with a key 'reason'.

### List of API requests

1. **POST /validate**

  Request body: Yandex.Tank config in .yaml format (the same as for console Tank)

  Checks if config provided is valid within local defaults

  Reply on success:     
  ```javascript
  {
    "config": "<yaml string>", // your config
    "errors": [] // empty if valid
  }
  ```

  Error codes and corresponding reasons in the reply:

  * 400, 'Config is not a valid YAML.'

2. **POST /run?[test=...]&[break=...]**

  Request body: Yandex.Tank config in .yaml format (the same as for console Tank)

  Creates a new session with an unique *session ID* and launches a new Tank worker.

  Parameters:

  * test: Prefix of the session ID. Should be a valid directory name. *Default: current datetime in the %Y%m%d%H%M%S format*
  * break: the test stage before which the tank will stop and wait until the next break is set. *Default: "finished"*

  Reply on success:     
  ```javascript
  {
    "session": "20150625210015_0000000001", //ID of the launched session
    "test": "20150625210015_0000000001" //Deprecated, do not use
  }
  ```

  Error codes and corresponding reasons in the reply:

  * 400, 'Specified break is not a valid test stage name.'
  * 409, 'The test with this ID is already running.'
  * 409, 'The test with this ID has already finished.'
  * 503, 'Another session is already running.'

3. **GET /run?session=...&[break=...]**

  Sets a new break point for the running session.

  Parameters:

  * session: session ID
  * break: the test stage before which the tank will stop and wait until the next break is set. *Default: "finished"*

  Return codes and corresponding reasons:

  * 200, 'Will try to set break before [new break point]'
  * 400, 'Specified break is not a valid test stage name.'
  * 404, 'No session with this ID.'
  * 418, ... (returned when client tries to move the break point back)
  * 500, 'Session failed.'

4. **GET /stop?session=...**

  Terminates the current test.

  Parameters:

  * session: ID of the session to terminate

  Return codes and corresponding reasons:

  * 200, 'Will try to stop tank process.'
  * 404, 'No session with this ID.'
  * 409, 'This session is already stopped.'

5. **GET /status?session=...**

  Returns the status of the specified session.
  Parameters:

  * session: ID of the session.

  Status examples:
  ```javascript
  {
    "status": "running",
    "stage_completed": true,
    "break": "start",
    "current_stage": "prepare",
    "test": "9f43f3104c2549b98bf74b817dc71cef",
    "failures": []
  }
  ```

  ```javascript
  {
    "status": "failed", 
    "retcode": 1, 
    "stage_completed": true, 
    "break": "finished", 
    "current_stage": "finished", 
    "test": "9f43f3104c2549b98bf74b817dc71cef", 
    "failures": [
        {
            "reason": "Interrupted", 
            "stage": "prepare"
        }
    ]
  }
  ```

  Error code and the corresponding reason:

  * 404, 'No session with this ID.'

6. **GET /status?**

  Returns a JSON object where keys are known session IDs and values are the corresponding statuses.

7. **GET /artifact?session=...**

  Returns a JSON array of artifact filenames.

  Parameters:

  * test: ID of the test

  Error codes and the corresponding reasons:

  * 404, 'No test with this ID found.'
  * 404, 'Test was not performed, no artifacts.'

8. **GET /artifact?session=...&filename=...**

  Sends the specified artifact file to the client.

  Parameters:

  * session: ID of the session
  * filename: the artifact file name

  Error codes and the corresponding reasons:

  * 404, 'No session with this ID found'
  * 404, 'Test was not performed, no artifacts.'
  * 404, 'No such file'
  * 503, 'File is too large and test is running' (when the file size exceeds 128 kB and some test is running)

9. **POST /upload?session=...&filename=...**

  Stores the request body on the server in the tank working directory for the session under the specified filename.
  The session should be running.

  Parameters:

  * session: ID of the session
  * filename: the name to store the file under

  Error codes and the corresponding reasons:

  * 404, 'Specified session is not running'

### Writing plugins

Some custom plugins might need to know if they are wokring in the console Tank or under API.

API worker process uses a subclass of a standard TankCore as a tank core.
Thus, a plugin can detect execution under API by simply checking that
```python
str(self.core.__class__)=='yandex_tank_api.worker.TankCore'
```


