Flask-Injector
==============

Adds `Injector <https://github.com/alecthomas/injector>`_ support to Flask.

Injector is a dependency-injection framework for Python, inspired by Guice.

This brings several benefits to Flask:

 - No need for a global "app" object, or globals in general. This makes testing simpler.
 - Explicit assignment of routes at app construction time.
 - Class-based routes with injected arguments.


Typical application layout
--------------------------

The first step is generally to create views. Views are global functions or
classes marked with the `@route` decorator (t has the same arguments as
Flask's `@app.route` decorator). Views can have dependencies injected into
them as keyword arguments by using the `Injector.inject` decorator::

    import sqlite3
    from flask.ext.injector import FlaskInjector, route
    from flask import Config
    from injector import inject

    @route("/bar")
    def bar():
        return render("bar.html")


    # Route with injection
    @route("/foo")
    @inject(db=sqlite3.Connection)
    def foo(db):
        users = db.execute('SELECT * FROM users').all()
        return render("foo.html")


    # Class-based route with injected constructor
    @route('/waz')
    class Waz(object):
        @inject(db=sqlite3.Connection)
        def __init__(self, db):
            self.db = db

        @route("/waz/<key>")
        def waz(self, key):
            users = db.execute('SELECT * FROM users WHERE name=?', (key,)).all()
            return 'waz'

In the Injector world, all dependency configuration and initialization is
performed in `modules <http://packages.python.org/injector/#module>`_. The
same is true with Flask-Injector. You can see some examples of configuring
Flask extensions through modules below.

Accordingly, the next step is to create modules for any objects we want made
available to the application. Note that in this example we also use the
injector to gain access to the `flask.Config`, which is bound by `FlaskInjector`::

    # Configure our SQLite connection object
    def configure(binder):
        config = binder.injector.get(Config)
        binder.bind(
            sqlite3.Connection,
            to=sqlite3.Connection(config['DB_CONNECTION_STRING']),
            scope=request,
            )

Instantiate the `Flask` instance in `main()`::

    def main():
        app = Flask(__name__)

Update the `Flask` app configuration as normal, additionally passing in any
configuration for modules::

        app.config.update(
            DB_CONNECTION_STRING=':memory:',
            )

Create a list of view functions and classes to install into the application::

        views = [foo, bar, Waz]

Create a list of `Injector` modules  to use for configuring the application state::

        modules = [configure]

Construct a `FlaskInjector` instance, passing the view list and module list to
the constructor, and initialize the application with it::

        flask_injector = FlaskInjector(views, modules)
        injector = flask_injector.init_app(app)

Run the Flask application as normal::

        app.run()

See `example.py` for a more complete example, including `Flask-SQLAlchemy` and
`Flask-Cache` integration.

Supporting Flask Extensions
---------------------------

Typically, Flask extensions are initialized at the global scope using a
pattern similar to the following.

::

    app = Flask(__name__)
    ext = ExtClass(app)

    @app.route(...)
    def view():
        # Use ext object here...

As we don't have these globals with Flask-Injector we have to configure the
extension the Injector way - through modules. Modules can either be subclasses
of `injector.Module` or a callable taking an `injector.Binder` instance.

::

    def configure_ext(binder):
        app = binder.get(Flask)
        binder.bind(ExtClass, to=ExtClass(app), scope=singleton)

    def main():
        app = Flask(__name__)
        app.config.update(
            EXT_CONFIG_VAR='some_value',
        )
        fi = FlaskInjector([view], [configure_ext])
        app.run()

*Make sure to bind extension objects as singletons.*

Working Example 1: Flask-SQLAlchemy integration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This is a full working example of integrating Flask-SQLAlchemy.

We use standard SQLAlchemy models rather than the Flask-SQLAlchemy magic.

::

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

::

    from flast.ext.sqlalchemy import SQLAlchemy

    class SQLAlchemyModule(Module):
        def configure(self, binder):
            app = binder.injector.get(Flask)
            db = self.configure_db(app)
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

::

    class CacheModule(Module):
        """Configure the application."""
        def configure(self, binder):
            app = binder.injector.get(Flask)
            binder.bind(Cache, to=Cache(app), scope=singleton)


