Flask-Injector
==============

.. image:: https://secure.travis-ci.org/alecthomas/flask_injector.png?branch=master
   :alt: Build status
   :target: https://travis-ci.org/alecthomas/flask_injector
.. image:: https://coveralls.io/repos/github/alecthomas/flask_injector/badge.svg?branch=master
   :alt: Coverage status
   :target: https://coveralls.io/github/alecthomas/flask_injector?branch=master


Adds `Injector <https://github.com/alecthomas/injector>`_ support to Flask,
this way there's no need to use global Flask objects, which makes testing simpler.

Injector is a dependency-injection framework for Python, inspired by Guice. You
can `find Injector on PyPI <https://pypi.org/project/injector/>`_ and `Injector
documentation on Read the Docs <https://injector.readthedocs.io/en/latest/>`_.

`Flask-Injector` is compatible with CPython 3.5+.
As of version 0.12.0 it requires Injector version 0.13.2 or greater and Flask
1.0 or greater.

GitHub project page: https://github.com/alecthomas/flask_injector

PyPI package page: https://pypi.org/project/Flask-Injector/

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
* Flask-RESTX Resource constructors

Flask-Injector supports defining types using function annotations (Python 3),
see below.

Documentation
-------------

As Flask-Injector uses Injector under the hood you should find the
`Injector documentation <https://injector.readthedocs.io/en/latest/>`_,
including the `Injector API reference <https://injector.readthedocs.io/en/latest/api.html>`_,
helpful. The `Injector README <https://github.com/alecthomas/injector/blob/master/README.md>`_
provides a tutorial-level introduction to using Injector.

The Flask-Injector public API consists of the following:

* `FlaskInjector` class with the constructor taking the following parameters:

  * `app`, an instance of`flask.Flask` [mandatory] – the Flask application to be used
  * `modules`, an iterable of
    `Injector modules <https://injector.readthedocs.io/en/latest/api.html#injector.Binder.install>`_ [optional]
    – the Injector modules to be used.
  * `injector`, an instance of
    `injector.Injector <https://injector.readthedocs.io/en/latest/api.html#injector.Injector>`_ [optional]
    – an instance of Injector to be used if, for some reason, it's not desirable
    for `FlaskInjector` to create a new one. You're likely to not need to use this.
  * `request_scope_class`, an `injector.Scope <https://injector.readthedocs.io/en/latest/api.html#injector.Scope>`_
    subclass [optional] – the scope to be used instead of `RequestScope`. You're likely to need to use this
    except for testing.
* `RequestScope` class – an `injector.Scope <https://injector.readthedocs.io/en/latest/api.html#injector.Scope>`_
  subclass to be used for storing and reusing request-scoped dependencies
* `request` object – to be used as a class decorator or in explicit
  `bind() <https://injector.readthedocs.io/en/latest/api.html#injector.Binder.bind>`_ calls in
  Injector modules.
  
Creating an instance of `FlaskInjector` performs side-effectful configuration of the Flask
application passed to it. The following bindings are applied (if you want to modify them you
need to do it in one of the modules passed to the `FlaskInjector` constructor):

* `flask.Flask` is bound to the Flask application in the (scope: singleton)
* `flask.Config` is bound to the configuration of the Flask application
* `flask.Request` is bound to the current Flask request object, equivalent to the thread-local
  `flask.request` object (scope: request)
 
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
    def foo(db: sqlite3.Connection):
        users = db.execute('SELECT * FROM users').all()
        return render("foo.html")


    # Class-based view with injected constructor
    class Waz(View):
        @inject
        def __init__(self, db: sqlite3.Connection):
            self.db = db

        def dispatch_request(self, key):
            users = self.db.execute('SELECT * FROM users WHERE name=?', (key,)).all()
            return 'waz'

    app.add_url_rule('/waz/<key>', view_func=Waz.as_view('waz'))


    # In the Injector world, all dependency configuration and initialization is
    # performed in modules (https://injector.readthedocs.io/en/latest/terminology.html#module).
    # The same is true with Flask-Injector. You can see some examples of configuring
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

    from injector import Module

    class MyModule(Module):
        @provider
        @singleton
        def provide_ext(self, app: Flask) -> ExtClass:
            return ExtClass(app)

    def main():
        app = Flask(__name__)
        app.config.update(
            EXT_CONFIG_VAR='some_value',
        )

        # attach your views etc. here

        FlaskInjector(app=app, modules=[MyModule])

        app.run()

*Make sure to bind extension objects as singletons.*
