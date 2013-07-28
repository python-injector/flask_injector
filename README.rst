Flask-Injector
==============

.. image:: https://secure.travis-ci.org/alecthomas/flask_injector.png?branch=master
   :alt: Build status
   :target: https://travis-ci.org/alecthomas/flask_injector


Adds `Injector <https://github.com/alecthomas/injector>`_ support to Flask.

Injector is a dependency-injection framework for Python, inspired by Guice.

This way there's no need to use global Flask objects, which makes testing simpler.

`Flask-Injector` is compatible with CPython 2.5-2.6, 3.3+ and PyPy 1.9+.


Example application using flask_injector
----------------------------------------

Create your Flask application:

.. code:: python

    import sqlite3
    from flask import Flask, Config
    from flask.views import View
    from flask_injector import init_app, post_init_app
    from injector import Injector, inject

    app = Flask(__name__)

Update the `Flask` app configuration as normal, additionally passing in any
configuration for modules:

.. code:: python

    app.config.update(
        DB_CONNECTION_STRING=':memory:',
    )

In the Injector world, all dependency configuration and initialization is
performed in `modules <http://packages.python.org/injector/#module>`_. The
same is true with Flask-Injector. You can see some examples of configuring
Flask extensions through modules below.

Accordingly, the next step is to create modules for any objects we want made
available to the application. Note that in this example we also use the
injector to gain access to the `flask.Config`:

.. code:: python

    # Configure our SQLite connection object
    @inject(config=Config)
    def configure(binder, config):
        binder.bind(
            sqlite3.Connection,
            to=sqlite3.Connection(config['DB_CONNECTION_STRING']),
            scope=request,
        )

Now perform Injector Flask application integration initialization. This needs to
be run before any views, handlers, etc. are configured for the application:

.. code:: python

    injector = init_app(app=app, modules=[configure])

Configure your application by attaching views, handlers, context processors etc.:

.. code:: python

    # Putting all views configuration in a function is an example of how can
    # you stop depending on global app object
    def configure_views(app):
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

    configure_views(app)

Run the post-initialization step. This needs to be run only after you attached all
views, handlers etc.:

.. code:: python

    post_init_app(app=app, injector=injector)

Run the Flask application as normal:

.. code:: python

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

        injector = init_app(app=app, modules=[configure_ext])
        # attach your views etc. here
        post_init_app(app=app, injector=injector)

        app.run()

*Make sure to bind extension objects as singletons.*

Working Example 1: Flask-SQLAlchemy integration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This is a full working example of integrating Flask-SQLAlchemy.

We use standard SQLAlchemy models rather than the Flask-SQLAlchemy magic.

.. code:: python

    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy import Column, String

    Base = declarative_base()


    class KeyValue(Base):
        __tablename__ = 'data'

        key = Column(String, primary_key=True)
        value = Column(String)

        def __init__(self, key, value):
            self.key = key
            self.value = value

And to register the Flask-SQLAlchemy extension.

.. code:: python

    from flast.ext.sqlalchemy import SQLAlchemy

    @inject(app=Flask)
    class FlaskSQLAlchemyModule(Module):
        def configure(self, binder):
            db = self.configure_db(self.app)
            binder.bind(SQLAlchemy, to=db, scope=singleton)

        def configure_db(self, app):
            db = SQLAlchemy(app)
            Base.metadata.create_all(db.engine)
            db.session.add_all([
                KeyValue('hello', 'world'),
                KeyValue('goodbye', 'cruel world'),
            ])
            db.session.commit()
            return db

Working Example 2: Flask-Cache integration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code:: python

    @inject(app=Flask)
    class CacheModule(Module):
        """Configure the application."""
        def configure(self, binder):
            binder.bind(Cache, to=Cache(self.app), scope=singleton)
