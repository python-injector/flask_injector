# encoding: utf-8
#
# Copyright (C) 2012 Alec Thomas <alec@swapoff.org>
# Copyright (C) 2015 Smarkets Limited <support@smarkets.com>
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
from werkzeug.local import Local, LocalManager, LocalProxy
from werkzeug.wrappers import Response
from injector import Module, Provider, Scope, ScopeDecorator, singleton


__author__ = 'Alec Thomas <alec@swapoff.org>'
__version__ = '0.5.0'
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
        cls = fun.view_class
        name = fun.__name__

        closure_contents = (c.cell_contents for c in fun.__closure__)
        fun_closure = dict(zip(fun.__code__.co_freevars, closure_contents))
        try:
            class_kwargs = fun_closure['class_kwargs']
        except KeyError:
            # Most likely flask_restful resource, we'll see in a second
            flask_restful = fun_closure['self']
            # flask_restful wraps ResourceClass.as_view() result in its own wrapper
            # the as_view() result is available under 'resource' name in this closure
            fun = fun_closure['resource']
            fun_closure = {}
            class_kwargs = {}
            # if the lines above succeeded we're quite sure it's flask_restful resource
        else:
            flask_restful = None
            class_args = fun_closure['class_args']
            assert not class_args, 'Class args are not supported, use kwargs instead'

        # This section is flask.views.View.as_view code modified to make the injection
        # possible without relying on modifying view function in place
        # Copyright (c) 2014 by Armin Ronacher and Flask contributors, see Flask
        # license for details

        def view(*args, **kwargs):
            self = injector.create_object(cls, additional_kwargs=class_kwargs)
            return self.dispatch_request(*args, **kwargs)

        if cls.decorators:
            view.__name__ = name
            view.__module__ = cls.__module__
            for decorator in cls.decorators:
                view = decorator(view)

        # We attach the view class to the view function for two reasons:
        # first of all it allows us to easily figure out what class-based
        # view this thing came from, secondly it's also used for instantiating
        # the view class so you can actually replace it with something else
        # for testing purposes and debugging.
        view.view_class = cls
        view.__name__ = name
        view.__doc__ = cls.__doc__
        view.__module__ = cls.__module__
        view.methods = cls.methods

        fun = view

        if flask_restful:
            from flask_restful.utils import unpack

            # The following fragment of code is copied from flask_restful project

            """
            Copyright (c) 2013, Twilio, Inc.
            All rights reserved.

            Redistribution and use in source and binary forms, with or without
            modification, are permitted provided that the following conditions are met:

            - Redistributions of source code must retain the above copyright notice, this
              list of conditions and the following disclaimer.
            - Redistributions in binary form must reproduce the above copyright notice,
              this list of conditions and the following disclaimer in the documentation
              and/or other materials provided with the distribution.
            - Neither the name of the Twilio, Inc. nor the names of its contributors may be
              used to endorse or promote products derived from this software without
              specific prior written permission.

            THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
            ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
            WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
            DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
            FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
            DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
            SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
            CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
            OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
            OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
            """

            # we need separate variable for the closure to work correctly
            # after we assign to fun below
            original_fun = fun

            @functools.wraps(original_fun)
            def wrapper(*args, **kwargs):
                resp = original_fun(*args, **kwargs)
                if isinstance(resp, Response):  # There may be a better way to test
                    return resp
                data, code, headers = unpack(resp)
                return flask_restful.make_response(data, code, headers=headers)

            # end of flask_restful code

            fun = wrapper

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
