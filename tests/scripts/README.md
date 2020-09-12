Test scripts
============

This directory contains all the scripts used for the manual testing of the application.
It has a single entry point called `run_testenv` that prepares a test environment
in the current shell:

    # On linux
    $ source tests/scripts/run_testenv.sh
    # On windows
    $ .\tests\scripts\run_testenv.bat


The requirements for running this script is a python virtualenv with a full installation
of guardata :

    $ pip install -e .[all]


Default behavior for `run_testenv`
-------------------------------------------

The `run_testenv` script starts by creating a temporary directory dedicated
to this test session. The environment variables are then set accordingly.
- On linux: `XDG_CACHE_HOME`, `XDG_DATA_HOME` and `XDG_CONFIG_HOME`
- On windows: `LOCALAPPDATA`

Check that the script has been properly sourced using:

    # On linux
    $ echo $XDG_CONFIG_HOME
    # On windows
    $ echo %LOCALAPPDATA%

It will then proceed to configure the MIME types of this environment in order to
support the `parsec://` schema properly (Linux only).

One can check that the schema is properly registered using `xdg-open`:

    $ xdg-open parsec://this-url-is-not-valid

It will then proceed to start a new backend server as a background task. If another
Parsec service backend is already running on the same port, the existing process will first
be killed.

Check that the backend is running using `netstat`:

    $ netstat -tlp | grep 6888

It will then proceed to the initialization of a test organization, using the
`guardata.test_utils.initialize_test_organization` function. More precisely, the
test organization has two registered users, Alice and Bob who both own two devices,
laptop and pc. They each have their own workspace, respectively `alice_workspace` and
`bob_workspace`, that they are sharing with each other.

* Alice is the administrator.
  * Devices Password : test
* Bob is a standard user.
  * Devices Password : test

Check that the test organization has been properly created using the guardata GUI :

    $ guardata client gui


Parameterize `run_testenv`
------------------------------------

The script can be customized with many options. The full list is available through
the `--help` option:

    $ source tests/scripts/run_testenv.sh --help
    [...]
    Options
        -B, --backend-address FROM_URL
        -p, --backend-port INTEGER      [default: 6888]
        -O, --organization-id ORGANIZATIONID
                                        [default: corp]
        -a, --alice-device-id DEVICEID  [default: alice@laptop]
        -b, --bob-device-id DEVICEID    [default: bob@laptop]
        -o, --other-device-name TEXT    [default: pc]
        -x, --alice-workspace TEXT      [default: alice_workspace]
        -y, --bob-workspace TEXT        [default: bob_workspace]
        -P, --password TEXT             [default: test]
        -T, --administration-token TEXT
                                        [default: V8VjaXrOz6gUC6ZEHPab0DSsjfq6DmcJ]
        --force / --no-force            [default: False]
        --add-users                     [default=0] Limited to 200
        --add-devices                   [default=0] Limited to 200
        -e, --empty

In particular:
 - `--backend-address` can be used to connect to an existing backend instead of
   starting a new one
 - `--backend-port` can be used to specify a backend port and prevent the script from
   killing the previously started backend
 - `--empty` that can be used to initialize and empty environment. This is especially
   useful for testing the invitation procedure.
 - `--add-users` can be used to add X random users. This is limited to 200 additionnal users.
 - `--add-devices` can be used to add X random devices. This is limited to 200 additionnal devices.


Example: testing the invitation procedure
-----------------------------------------

The following scenario shows how the Parsec invitation procedure can easily be tested
using the `run_testenv` script and two terminals.

In a first terminal, run the following commands:

    $ source tests/scripts/run_testenv.sh
    $ guardata client gui
    # Connect as bob@laptop (pwd=test) and register a new device called pc
    # Copy the URL


Then, in a second terminal:

    $ source tests/scripts/run_testenv.sh --empty
    $ xdg-open "<paste the URL here>"  # Or
    $ firefox --no-remote "<paste the URL here>"
    # A second instance of guardata pops-up
    # Enter the tokens to complete the registration

Note that the two GUI application do not conflict with one another as they're
running in different environments. It works exactly as if they were being run
on two different computers.
