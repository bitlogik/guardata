
guardata history
----------------

0.2.2 - 2021-03-30
^^^^^^^^^^^^^^^^^^

* Updates in the GUI

  * Fix crash when next device page
  * Fix can't quit before login when minimize enabled
  * Safe quit during reencryption
  * Fixes startup on MacOS
  * Final update for dark on MacOS
  * Child modals stay on top
  * More stable mountpoints on Linux and MacOS

* Updated WebSocket client library
* Improved offline behavior


0.2.0 - 2021-01-15
^^^^^^^^^^^^^^^^^^

* Updates in the GUI

  * Update for dark on Mac
  * Fix text escaping some buttons
  * In Windows : workspaces open Explorer
  * Files list preview removed
  * Password change is now in "user" logout menu
  * Fix a code syntax in French translation
  * Fix tab closing issue
  * Default changes : don't start in full screen, hide temp files
  * Close without confirmation when no login

* Update code quality control
* Fix uncatch exception on mounting (Linux)
* pyInstaller updated on MacOS


0.1.6 - 2020-11-16
^^^^^^^^^^^^^^^^^^

* Updates in the GUI

  * Fix crash when loading >2GB file
  * Improve loading file link
  * Email address in sharing list
  * Refine calendar for time machine
  * Copy/paste between worspaces
  * Catch no more remaining drives on Windows
  * All dialogs are non-blocking
  * UX improved for machine greeting

* Works on MacOS 11 (untested on ARM)
* Better stability on Mac
* URL scheme now works on Mac
* various small improvements


0.1.4 - 2020-10-16
^^^^^^^^^^^^^^^^^^

* Updates in the GUI

  * Modal stability fix (blank, hidden error, input disabled,...)
  * Various UI improvements on group activation modal
  * Fix dialog crash when closing on Mac
  * More friendly group join data input
  * Nicer widget for snapshot workspaces
  * Show user role in workspace GUI
  * Save GUI window size and position
  * Spinner on GUI directory loading
  * Fix and improve login tabs
  * Version update check on Mac
  * Display data size of the group in the GUI

* Logs on Mac
* Possible args on Mac
* Some Python dependencies updated
* Improve mountpoint cancelling
* Better error display
* Improve server queries handling


0.1.2 - 2020-09-22
^^^^^^^^^^^^^^^^^^

* First MacOSX version
* Fix Snap building
* GUI : refresh login list when logout
* GUI : don't ask to select account if only 1
* Cleanups (pkg, files)
* Windows installer simplified
* Script for dev to add devices/users much faster
* many dependencies updated
* Improve backend management of websocket


0.1.0 - 2020-09-12
^^^^^^^^^^^^^^^^^^

* Updates in the GUI

  * Many fixes and improvements
  * Spinners for tiles queries
  * Smaller user/devices tiles
  * Blue tone changed for the official guardata
  * Pagination for users and devices
  * Works when offline or network errors
  * Much faster reencryption
  * Sharing roles change ack
  * Searching for users or devices improved

* Windows data path is local (no roaming)
* Fix Windows path handling
* No more inopportune warnings about resources usage
* Remove all old APIs methods
* Testing env improve (compatibility, UI)
* Python3 specified everywhere
* Network buffer of the backend server improved (send once, receive more)
* Update invitation style
* Add a copy button to redirect invite
* Redirect invite page has automatic internationalization
* Client messages have more buffer
* CI/CD pipelines strenghten and cleanup
* Python package for Windows updated to 3.7.9
* Fix a closing file bug


0.0.4 - 2020-08-30
^^^^^^^^^^^^^^^^^^

* Updates in the GUI

  * Filtering in workspace preview
  * Improve device adding
  * Fix bad message with wrong name during claim user
  * Improve Return key detection at login
  * Add spinner when querying the server

* Better handling of Parsec link
* Update Windows installer, restore app icon
* Snap package available
* Improve CI pipelines
* Tests scripts for developers are now working

0.0.2 - 2020-08-25
^^^^^^^^^^^^^^^^^^

* First version
