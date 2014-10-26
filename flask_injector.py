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
import warnings

import flask
from injector import Injector
from flask import Config, Request
from werkzeug.local import Local, LocalManager, LocalProxy
from injector import Module, Provider, Scope, ScopeDecorator, singleton, InstanceProvider


__author__ = 'Alec Thomas <alec@swapoff.org>'
__version__ = '0.4.0'
__all__ = ['request', 'RequestScope', 'Config', 'Request', 'FlaskInjector', ]


def wrap_fun(fun, injector):
    if isinstance(fun, LocalProxy):
        return fun

    if hasattr(fun, '__bindings__'):
        @functools.wraps(fun)
        def wrapper(*args, **kwargs):
            injections = injector.args_to_inject(
                function=fun,
                bindings=fun.__bindings__,
                owner_key=fun.__module__,
            )
            return fun(*args, **dict(injections, **kwargs))

        return wrapper
    elif hasattr(fun, 'view_class'):
        current_class = fun.view_class

        def cls(**kwargs):
            return injector.create_object(
                current_class, additional_kwargs=kwargs)

        fun.view_class = cls

    return fun


class CachedProviderWrapper(Provider):
    def __init__(self, old_provider):
        self._old_provider = old_provider
        self._cache = {}

    def get(self, injector):
        key = id(injector)
        try:
            return self._cache[key]
        except KeyError:
            instance = self._cache[key] = self._old_provider.get(injector)
            return instance


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

    try:
        from injector import BoundProvider  # noqa
    except ImportError:
        def get(self, key, provider):
            try:
                return self._locals.scope[key]
            except KeyError:
                provider = InstanceProvider(provider.get())
                self._locals.scope[key] = provider
                return provider
    else:
        def get(self, key, provider):
            try:
                return self._locals.scope[key]
            except KeyError:
                new_provider = self._locals.scope[key] = CachedProviderWrapper(provider)
                return new_provider


request = ScopeDecorator(RequestScope)


class FlaskInjector(object):
    def __init__(self, app, modules=[], injector=None, request_scope_class=RequestScope):
        """Initializes Injector for the application.

        .. note::

            Needs to be called *after* all views, signal handlers, template globals
            and context processors are registered.

        :param app: Application to configure
        :param modules: Configuration for newly created :class:`injector.Injector`
        :param injector: Injector to initialize app with, if not provided
            a new instance will be created.
        :type app: :class:`flask.Flask`
        :type modules: Iterable of configuration modules
        :rtype: :class:`injector.Injector`
        """
        injector = injector or Injector()
        for module in (
                [FlaskModule(app=app, request_scope_class=request_scope_class)] +
                list(modules)):
            injector.binder.install(module)

        for container in (
                app.view_functions,
                app.before_request_funcs,
                app.after_request_funcs,
                app.teardown_request_funcs,
                app.template_context_processors,
                app.jinja_env.globals,
        ):
            process_dict(container, injector)

        process_error_handler_spec(app.error_handler_spec, injector)

        def reset_request_scope(*args, **kwargs):
            injector.get(request_scope_class).reset()

        app.before_request_funcs.setdefault(None, []).insert(0, reset_request_scope)
        app.teardown_request(reset_request_scope)

        self.injector = injector
        self.app = app


def process_dict(d, injector):
    for key, value in d.items():
        if isinstance(value, list):
            value[:] = [wrap_fun(fun, injector) for fun in value]
        elif hasattr(value, '__call__'):
            d[key] = wrap_fun(value, injector)


def process_error_handler_spec(spec, injector):
    for subspec in spec.values():
        try:
            custom_handlers = subspec[None]
        except KeyError:
            pass
        else:
            custom_handlers[:] = [(error, wrap_fun(fun, injector)) for (error, fun) in custom_handlers]

        process_dict(subspec, injector)


class FlaskModule(Module):
    def __init__(self, app, request_scope_class=RequestScope):
        self.app = app
        self.request_scope_class = request_scope_class

    def configure(self, binder):
        binder.bind_scope(self.request_scope_class)
        binder.bind(flask.Flask, to=self.app, scope=singleton)
        binder.bind(Config, to=self.app.config, scope=singleton)
        binder.bind(Request, to=lambda: flask.request)
