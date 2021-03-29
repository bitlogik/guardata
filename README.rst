
.. image:: https://raw.githubusercontent.com/bitlogik/guardata/master/guardata/client/gui/rc/images/logos/guardata_vert.png
    :align: center

|
|

guardata is a secure and trustless cloud storage service, to share and sync your files with on-premise modern encryption.

|

Homepage: https://guardata.app

Key features :

- Cloud storage
- Virtual drive
- Time machine
- Local encryption, Trust no one
- Share & sync securely
- Access control and logging
- open source

guardata is based on the `Parsec technology <https://www.youtube.com/watch?v=Ds89nhbO0yk>`_ developed by Scille. The code base is a fork from `parsec-cloud <https://github.com/Scille/parsec-cloud>`_. The cryptographic routines are provided by the `libsodium library <https://doc.libsodium.org/>`_.


Differences with the Parsec reference implementation :

- The encryption stream cipher algorithm is updated from Salsa20 to Chacha20. guardata is using XChaCha20-Poly1305 which has an `IETF draft standard <https://tools.ietf.org/html/draft-irtf-cfrg-xchacha-03>`_, and is `used by NordPass <https://nordpass.com/features/xchacha20-encryption/>`_ and by `CloudFlare <https://blog.cloudflare.com/do-the-chacha-better-mobile-performance-with-cryptography/>`_.
- The password key derivation algorithm is setup to be 6 times stronger
- Password strength required in the GUI is much higher
- The debug monitoring telemetry is fully removed, for a full hassle-free privacy
- Files blocks cut size is bigger, optimised for internet synchronization
- SHA2 hash is replaced everywhere by Blake2b
- More secure short codes for 2-way auth : from 40 bits with hmac-sha2 to 50 bits with argon2id
- Improve server socket management (parsec-cloud sends header separated from data)
- Data (encrypted) are local only in Windows, not shared with Microsoft through roaming
- UX improved (invitation redirect, offline, non-blocking modals)


Install
-------

| Get the guardata client software on
| https://guardata.app/get
|


Documentation
-------------

| Documentation is available at
| https://docs.guardata.app
|

