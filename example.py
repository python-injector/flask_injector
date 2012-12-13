from injector import Module, inject, singleton
from flask import Flask, Request, jsonify
from flask.ext.cache import Cache
from flask.ext.injector import FlaskInjector, route, decorator
from flask.ext.sqlalchemy import SQLAlchemy
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy import Column, String

"""
This is an example of using Injector (https://github.com/alecthomas/injector) and Flask.

Flask provides a lot of very nice features, but also requires a lot of globals
and tightly bound code. Flask-Injector seeks to remedy this.
"""


# Create an adapter for the Flask-Cache decorator.
cached = decorator(Cache.cached)

# We use standard SQLAlchemy models rather than the Flask-SQLAlchemy magic, as
# it requires a global Flask app object and SQLAlchemy db object.
Base = declarative_base()


class KeyValue(Base):
    __tablename__ = 'data'

    key = Column(String, primary_key=True)
    value = Column(String)

    def __init__(self, key, value):
        self.key = key
        self.value = value

    def serializable(self):
        return


@route('/api/store', methods=['GET'])
class KeyValueStore(object):
    @inject(db=SQLAlchemy, request=Request)
    def __init__(self, db, request):
        self.db = db
        self.request = request

    @route('/<key>')
    def get(self, key):
        try:
            kv = self.db.session.query(KeyValue).filter(KeyValue.key == key).one()
        except NoResultFound:
            response = jsonify(status='No such key', context=key)
            response.status = '404 Not Found'
            return response
        return jsonify(key=kv.key, value=kv.value)

    @cached(timeout=1)
    @route('/')
    def list(self):
        data = [i.key for i in self.db.session.query(KeyValue).order_by(KeyValue.key)]
        return jsonify(keys=data)

    @route('/', methods=['POST'])
    def create(self):
        kv = KeyValue(self.request.form['key'], self.request.form['value'])
        self.db.session.add(kv)
        self.db.session.commit()
        response = jsonify(status='OK')
        response.status = '201 CREATED'
        return response

    @route('/<key>', methods=['DELETE'])
    def delete(self, key):
        self.db.session.query(KeyValue).filter(KeyValue.key == key).delete()
        self.db.session.commit()
        response = jsonify(status='OK')
        response.status = '200 OK'
        return response


class AppModule(Module):
    """Configure the application."""
    def configure(self, binder):
        app = binder.injector.get(Flask)
        # We configure the DB here, explicitly, as Flask-SQLAlchemy requires
        # the DB to be configured before request handlers are called.
        db = self.configure_db(app)
        binder.bind(SQLAlchemy, to=db, scope=singleton)
        binder.bind(Cache, to=Cache(app), scope=singleton)

    def configure_db(self, app):
        db = SQLAlchemy(app)
        Base.metadata.create_all(db.engine)
        db.session.add_all([
            KeyValue('hello', 'world'),
            KeyValue('goodbye', 'cruel world'),
        ])
        db.session.commit()
        return db


def main():
    app = Flask(__name__)
    app.config.update(
        DB_CONNECTION_STRING=':memory:',
        CACHE_TYPE='simple',
        SQLALCHEMY_DATABASE_URI='sqlite://',
    )
    app.debug = True
    builder = FlaskInjector([KeyValueStore], [AppModule()])
    injector = builder.init_app(app)

    client = app.test_client()

    response = client.get('/api/store/')
    print('%s\n%s%s' % (response.status, response.headers, response.data))
    response = client.post('/api/store/', data={'key': 'foo', 'value': 'bar'})
    print('%s\n%s%s' % (response.status, response.headers, response.data))
    response = client.get('/api/store/')
    print('%s\n%s%s' % (response.status, response.headers, response.data))
    response = client.get('/api/store/hello')
    print('%s\n%s%s' % (response.status, response.headers, response.data))
    response = client.delete('/api/store/hello')
    print('%s\n%s%s' % (response.status, response.headers, response.data))
    response = client.get('/api/store/')
    print('%s\n%s%s' % (response.status, response.headers, response.data))
    response = client.get('/api/store/hello')
    print('%s\n%s%s' % (response.status, response.headers, response.data))
    response = client.delete('/api/store/hello')
    print('%s\n%s%s' % (response.status, response.headers, response.data))


if __name__ == '__main__':
    main()
