Django InformixDB
==================

A database driver for Django to connect to an Informix database via
informixdb python module.

**Some limitations**:
- Do not support default values


Configure local environment
---------------------------

The following environment variables should exist:

INFORMIXDIR
    The path to the Informix client install directory

INFORMIXSERVER
    The name of the Informix service to which we need to connect

INFORMIXSQLHOSTS
    The path to the ``sqlhosts`` file that the Informix driver should use

LD_LIBRARY_PATH
    The path(s) to the various Informix library files: Usually $INFORIMIXDIR/lib:$INFORMIXDIR/lib/cli:$IMFORMIXDIR/lib/esql


You will also need to add an entry within your ``sqlhosts`` file for each remote/local Informix server connection in the following format:

.. code-block:: bash

    <INFORMIX_SERVER_NAME>    onsoctcp     <INFORMIX_HOST_NAME>    <INFORMIX_SERVICE_NAME>
    # e.g.
    dev    onsoctcp    localhost    sqlexec


Finally, you need to ensure that the service name is in the ``/etc/services`` file:

.. code-block:: bash

    sqlexec    9088/tcp


Configure settings.py
---------------------

Django’s settings.py require the following format to connect to an Informix database:

.. code-block:: python

    'default': {
        'ENGINE': 'django_informixdb',
        'NAME': 'myproject',
        'SERVER': 'ifxserver',
        'USER' : 'testuser',
        'PASSWORD': 'passw0rd',
        'OPTIONS': {
            'DRIVER': '/path/to/iclit09b.so'. # Or iclit09b.dylib on macOS
        }
    }

.. note:
    The ``DRIVER`` option is optional, default locations will be used per platform if it is not provided.

Using with the Docker Informix Dev Database
-------------------------------------------

The docker image from IBM for the Informix developer database image behaves a little differently compared to other images. As such it needs a little extra handling, and doesn't seem to work with docker-compose

Firstly we need to download and getting it running:

.. code-block:: bash

    $ docker run -itd --name iif_developer_edition --privileged -p 9088:9088 -p 9089:9089 -p 27017:27017 \
    -p 27018:27018 -p 27883:27883 -e LICENSE=accept ibmcom/informix-developer-database:latest

This will download the image if it doesn't exist, and then run it with the name ``iif_developer_edition``. The first time this run, the image will do a bunch of initial setup stuff. As we used the ``-d`` option, it will run in the background as a detached process. So don't be concerned that you do not see anything in the output.

You can stop and restart the container with:

.. code-block:: bash

    docker stop iif_developer_edition
    docker start iif_developer_edition

It seems that the Informix ODBC driver does not currently support creating databases. So we will need to do that manually, by attaching to the running container

.. code-block:: bash

    docker attach iif_developer_edition


This will give you a shell on the running container, and you can therefore use dbaccess to create your database. You can exit this shell using ``Ctrl-p`` ``Ctrl-q`` without shutting down the whole container.

This Django database adaptor for Informix requires transaction support to be enabled in our database. This is not the default within the Informix Developer image.  So you need to enable it on a per database basis:

.. code-block:: bash

    $ docker attach iif_developer_edition
    $ ontape -s -B <DB_NAME>

Again, you can detach using ``Ctrl-p`` ``Ctrl-q``.

Finally you need to ensure that our local dev database is included in the ``sqlhosts`` file. e.g.:

.. code-block:: bash

    dev    onsoctcp    localhost    sqlexec

and also in ``/etc/services``:

.. code-block:: bash

    sqlexec    9088/tcp

You should now be able to point Django to our local test database using the syntax detailed above.


Using Django InformixDB with docker-compose
-------------------------------------------

It is possible to use the Informix developer docker image with docker-compose with a little effort.

Example docker-compose.yml

.. code-block:: yaml

    version: '3'

    services:
        db:
            image: ibmcom/informix-developer-database
            tty: true # Needed to ensure container doesn't self terminate
            environment:
                LICENSE: accept
            privileged: true
            ports:
                - "9088:9088"
                - "9089:9089"
                - "27017:27017"
                - "27018:27018"
                - "27883:27883"


The key entry in the compose file which is out of the ordinary is `tty: true`. This allocates a (virtual) TTY to the container. The Informix developer database container expects a `tty` and terminates without one when run inside docker-compose.

Once it is up and running with `docker-compose up` you can run a `bash` shell on the running container with:

.. code-block:: bash

    docker exec -it informix_db_1 bash


Where `informix_db_1` is the name of the running container. From this shell you can create your DB with `dbaccess` etc.

.. warning::

    This approach still requires the SDK to installed locally and the appropriate environmental variables to be set up. Along with entries in `sqlhosts` and `/etc/services`


Testing against an Informix Database
------------------------------------

Due to a bug in the Informix ODBC driver, it is not currently possible to run Django tests normally. Specifically, it is not possible for Django to create a test database. As such, you will need to do it manually. By default Django will attempt to create a database with a name equal to the default database name with a ``test_`` prefix. e.g. if you database name is ``my_database``, the test database name would be ``test_my_database``.

You can follow the steps above, in the section on using Informix locally with Docker to create a test database. Then when running the test you can tell Django to re-use an existing database, rather than trying to create a new one with the ``-k`` parameter:

.. code-block:: bash

    ./manage.py test -k


