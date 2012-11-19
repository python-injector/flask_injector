Flask-Injector
--------------

Adds `Injector <https://github.com/alecthomas/injector>`_ support to Flask.

Injector is a dependency-injection framework for Python, inspired by Guice.

Here's a pseudo-example::

    import sqlite3
    from flask.ext.injector import Builder, route
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


    # Class-based view with injection
    @route('/waz')
    class Waz(object):
        @inject(db=sqlite3.Connection)
        def __init__(self, db):
            self.db = db

        @route("/waz")
        def waz(self):
            users = db.execute('SELECT * FROM users').all()
            return 'waz'


    def configure(binder):
        config = binder.injector.get(Config)
        binder.bind(
            sqlite3.Connection,
            to=sqlite3.Connection(config['DB_CONNECTION_STRING']),
            scope=request,
            )


    def main():
        views = [foo, bar, Waz]
        modules = [configure]
        app = Builder(views, modules, config={
            'DB_CONNECTION_STRING': ':memory:',
            }).build()
        app.run()

