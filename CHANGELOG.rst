
guardata history
----------------

0.1.2 - 2020-XX ?
^^^^^^^^^^^^^^^^^

* Fix Snap building
* GUI : refresh login list when logout
* Cleanups (pkg, files)
* Windows installer simplified
* Script for dev to add devices/users much faster
* msgpack dependency updated
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
