# encoding: utf-8
#
# Copyright (C) 2012 Alec Thomas <alec@swapoff.org>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution.
#
# Author: Alec Thomas <alec@swapoff.org>

from __future__ import absolute_import, division, print_function, unicode_literals

import functools

import flask
from injector import Injector
from flask import Config, Request
from werkzeug.local import Local, LocalManager
from injector import Module, Scope, ScopeDecorator, singleton, InstanceProvider


__author__ = 'Alec Thomas <alec@swapoff.org>'
__version__ = '0.2.0'
__all__ = ['request', 'RequestScope', 'Config', 'Request', ]


def wrap_fun(fun, injector):
    @functools.wraps(fun)
    def wrapper(*args, **kwargs):
        injections = injector.args_to_inject(
            function=fun,
            bindings=fun.__bindings__,
            owner_key=fun.__module__,
        )
        return fun(*args, **dict(injections, **kwargs))

    return wrapper


class RequestScope(Scope):
    """A scope whose object lifetime is tied to a request.

    @request
    class Session(object):
        pass
    """

    def reset(self):
        self._local_manager.cleanup()
        self._locals.scope = {}

    def configure(self):
        self._locals = Local()
        self._local_manager = LocalManager([self._locals])
        self.reset()

    def get(self, key, provider):
        try:
            return self._locals.scope[key]
        except KeyError:
            provider = InstanceProvider(provider.get())
            self._locals.scope[key] = provider
            return provider


request = ScopeDecorator(RequestScope)


def init_app(app, modules=[], request_scope_class=RequestScope):
    '''
    Initializes Injector for the application.

    .. note:: Needs to be called right after an application is created (eg. before
        any views, signal handlers etc. are registered).

    :param app: Application to configure
    :param modules: Configuration for newly created :class:`injector.Injector`
    :type app: :class:`flask.Flask`
    :type modules: Iterable of configuration modules
    :rtype: :class:`injector.Injector`
    '''
    injector = Injector(
        [FlaskModule(app=app, request_scope_class=request_scope_class)] +
        list(modules))

    @app.before_request
    def before_request():
        injector.get(request_scope_class).reset()

    return injector


def post_init_app(app, injector, request_scope_class=RequestScope):
    '''
    Needs to be called after all views, signal handlers, etc. are registered.

    :type app: :class:`flask.Flask`
    :type injector: :class:`injector.Injector`
    '''

    def w(fun):
        if hasattr(fun, '__bindings__'):
            fun = wrap_fun(fun, injector)
        elif hasattr(fun, 'view_class'):
            current_class = fun.view_class

            def cls(**kwargs):
                return injector.create_object(
                    current_class, additional_kwargs=kwargs)

            fun.view_class = cls

        return fun

    def process_dict(d):
        for key, value in d.items():
            if isinstance(value, list):
                value[:] = [w(fun) for fun in value]
            elif hasattr(value, '__call__'):
                d[key] = w(value)

    for container in (
            app.view_functions,
            app.before_request_funcs,
            app.after_request_funcs,
            app.teardown_request_funcs,
            app.template_context_processors,
    ):
        process_dict(container)

    def tearing_down(sender, exc=None):
        injector.get(request_scope_class).reset()

    app.teardown_request(tearing_down)


class FlaskModule(Module):
    def __init__(self, app, request_scope_class=RequestScope):
        self.app = app
        self.request_scope_class = request_scope_class

    def configure(self, binder):
        binder.bind_scope(self.request_scope_class)
        binder.bind(flask.Flask, to=self.app, scope=singleton)
        binder.bind(Config, to=self.app.config, scope=singleton)
        binder.bind(Request, to=lambda: flask.request)
