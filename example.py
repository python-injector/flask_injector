# -*- coding: utf-8 -*-
import logging

from injector import Module, inject, singleton
from flask import Flask, Request, jsonify
from flask_injector import init_app, post_init_app
from flask.ext.cache import Cache
from flask.ext.sqlalchemy import SQLAlchemy
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy import Column, String

il = logging.getLogger('injector')
il.addHandler(logging.StreamHandler())
il.level = logging.DEBUG

"""
This is an example of using Injector (https://github.com/alecthomas/injector) and Flask.

Flask provides a lot of very nice features, but also requires a lot of globals
and tightly bound code. Flask-Injector seeks to remedy this.
"""


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


def configure_views(app, cached):
    @app.route('/<key>')
    @inject(db=SQLAlchemy)
    def get(key, db):
        try:
            kv = db.session.query(KeyValue).filter(KeyValue.key == key).one()
        except NoResultFound:
            response = jsonify(status='No such key', context=key)
            response.status = '404 Not Found'
            return response
        return jsonify(key=kv.key, value=kv.value)

    @cached(timeout=1)
    @app.route('/')
    @inject(db=SQLAlchemy)
    def list(db):
        data = [i.key for i in db.session.query(KeyValue).order_by(KeyValue.key)]
        return jsonify(keys=data)

    @app.route('/', methods=['POST'])
    @inject(request=Request, db=SQLAlchemy)
    def create(request, db):
        kv = KeyValue(request.form['key'], request.form['value'])
        db.session.add(kv)
        db.session.commit()
        response = jsonify(status='OK')
        response.status = '201 CREATED'
        return response

    @app.route('/<key>', methods=['DELETE'])
    @inject(db=SQLAlchemy)
    def delete(db, key):
        db.session.query(KeyValue).filter(KeyValue.key == key).delete()
        db.session.commit()
        response = jsonify(status='OK')
        response.status = '200 OK'
        return response


@inject(app=Flask)
class AppModule(Module):
    """Configure the application."""
    def configure(self, binder):
        # We configure the DB here, explicitly, as Flask-SQLAlchemy requires
        # the DB to be configured before request handlers are called.
        db = self.configure_db(self.app)
        binder.bind(SQLAlchemy, to=db, scope=singleton)
        binder.bind(Cache, to=Cache(self.app), scope=singleton)

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
    injector = init_app(app=app, modules=[AppModule])

    configure_views(app=app, cached=injector.get(Cache).cached)

    post_init_app(app, injector)

    client = app.test_client()

    response = client.get('/')
    print('%s\n%s%s' % (response.status, response.headers, response.data))
    response = client.post('/', data={'key': 'foo', 'value': 'bar'})
    print('%s\n%s%s' % (response.status, response.headers, response.data))
    response = client.get('/')
    print('%s\n%s%s' % (response.status, response.headers, response.data))
    response = client.get('/hello')
    print('%s\n%s%s' % (response.status, response.headers, response.data))
    response = client.delete('/hello')
    print('%s\n%s%s' % (response.status, response.headers, response.data))
    response = client.get('/')
    print('%s\n%s%s' % (response.status, response.headers, response.data))
    response = client.get('/hello')
    print('%s\n%s%s' % (response.status, response.headers, response.data))
    response = client.delete('/hello')
    print('%s\n%s%s' % (response.status, response.headers, response.data))


if __name__ == '__main__':
    main()
