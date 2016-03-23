Flask-Injector
==============

.. image:: https://secure.travis-ci.org/alecthomas/flask_injector.png?branch=master
   :alt: Build status
   :target: https://travis-ci.org/alecthomas/flask_injector


Adds `Injector <https://github.com/alecthomas/injector>`_ support to Flask,
this way there's no need to use global Flask objects, which makes testing simpler.

Injector is a dependency-injection framework for Python, inspired by Guice.

`Flask-Injector` is compatible with CPython 2.7/3.3+, PyPy 1.9+ and PyPy 3 2.4+.
As of version 0.3.0 it requires Injector version 0.7.4 or greater.

GitHub project page: https://github.com/alecthomas/flask_injector

PyPI package page: https://pypi.python.org/pypi/Flask-Injector

Changelog: https://github.com/alecthomas/flask_injector/blob/master/CHANGELOG.rst

Features
--------

Flask-Injector lets you inject dependencies into:

* views (functions and class-based)
* `before_request` handlers
* `after_request` handlers
* `teardown_request` handlers
* template context processors
* error handlers
* Jinja environment globals (functions in `app.jinja_env.globals`)
* Flask-RESTFul Resource constructors
* Flask-RestPlus Resource constructors

Flask-Injector supports defining types using function annotations (Python 3),
see below.

Example application using Flask-Injector
----------------------------------------

.. code:: python

    import sqlite3
    from flask import Flask, Config
    from flask.views import View
    from flask_injector import FlaskInjector
    from injector import inject

    app = Flask(__name__)

    # Configure your application by attaching views, handlers, context processors etc.:

    @app.route("/bar")
    def bar():
        return render("bar.html")


    # Route with injection
    @app.route("/foo")
    @inject(db=sqlite3.Connection)
    def foo(db):
        users = db.execute('SELECT * FROM users').all()
        return render("foo.html")


    # Class-based view with injected constructor
    class Waz(View):
        @inject(db=sqlite3.Connection)
        def __init__(self, db):
            self.db = db

        def dispatch_request(self, key):
            users = self.db.execute('SELECT * FROM users WHERE name=?', (key,)).all()
            return 'waz'

    app.add_url_rule('/waz/<key>', view_func=Waz.as_view('waz'))


    # In the Injector world, all dependency configuration and initialization is
    # performed in modules (http://packages.python.org/injector/#module). The
    # same is true with Flask-Injector. You can see some examples of configuring
    # Flask extensions through modules below.

    # Accordingly, the next step is to create modules for any objects we want made
    # available to the application. Note that in this example we also use the
    # Injector to gain access to the `flask.Config`:

    def configure(binder):
        binder.bind(
            sqlite3.Connection,
            to=sqlite3.Connection(':memory:'),
            scope=request,
        )
    
    # Initialize Flask-Injector. This needs to be run *after* you attached all
    # views, handlers, context processors and template globals.

    FlaskInjector(app=app, modules=[configure])

    # All that remains is to run the application

    app.run()

See `example.py` for a more complete example, including `Flask-SQLAlchemy` and
`Flask-Cache` integration.

Supporting Flask Extensions
---------------------------

Typically, Flask extensions are initialized at the global scope using a
pattern similar to the following.

.. code:: python

    app = Flask(__name__)
    ext = ExtClass(app)

    @app.route(...)
    def view():
        # Use ext object here...

As we don't have these globals with Flask-Injector we have to configure the
extension the Injector way - through modules. Modules can either be subclasses
of `injector.Module` or a callable taking an `injector.Binder` instance.

.. code:: python

    @inject(app=Flask)
    def configure_ext(binder, app):
        binder.bind(ExtClass, to=ExtClass(app), scope=singleton)

    def main():
        app = Flask(__name__)
        app.config.update(
            EXT_CONFIG_VAR='some_value',
        )

        # attach your views etc. here

        FlaskInjector(app=app, modules=[configure_ext])

        app.run()

*Make sure to bind extension objects as singletons.*


Using Python 3+ function annotations
------------------------------------

If you want to use function annotations you can either pass
``use_annotations=True`` in the ``FlaskInjector`` constructor or provide an
already configured ``Injector`` instance with ``use_annotations`` enabled,
for example:

.. code:: python

    from flask import Flask
    from flask_injector import FlaskInjector

    app = Flask(__name__)

    @app.route("/")
    def index(s: str):
        return s

    def configure(binder):
        binder.bind(str, to='this is a test')

    FlaskInjector(app=app, modules=[configure], use_annotations=True)

    # Alternatively:
    from injector import Injector
    injector = Injector(..., use_annotations=True)
    FlaskInjector(app=app, injector=injector)
