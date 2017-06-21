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
import functools
from typing import Any, Callable, cast, Dict, get_type_hints, Iterable, TypeVar, Union

import flask
try:
    from flask_restful import Api as FlaskRestfulApi
except ImportError:
    FlaskRestfulApi = None
try:
    import flask_restplus
except ImportError:
    flask_restplus = None
from injector import Binder, Injector, inject
from flask import Config, Request
from werkzeug.local import Local, LocalManager, LocalProxy
from werkzeug.wrappers import Response
from injector import Module, Provider, Scope, ScopeDecorator, singleton


__author__ = 'Alec Thomas <alec@swapoff.org>'
__version__ = '0.10.0'
__all__ = ['request', 'RequestScope', 'Config', 'Request', 'FlaskInjector', ]

T = TypeVar('T', LocalProxy, Callable)


def wrap_fun(fun: T, injector: Injector) -> T:
    if isinstance(fun, LocalProxy):
        return fun  # type: ignore

    # Important: this block needs to stay here so it's executed *before* the
    # hasattr(fun, '__call__') block below - otherwise things may crash.
    if hasattr(fun, '__bindings__'):
        return wrap_function(fun, injector)

    if hasattr(fun, '__call__') and not isinstance(fun, type):
        try:
            type_hints = get_type_hints(fun)
        except (AttributeError, TypeError):
            # Some callables aren't introspectable with get_type_hints,
            # let's assume they don't have anything to inject. The exception
            # types handled here are what I encountered so far.
            # It used to be AttributeError, then https://github.com/python/typing/pull/314
            # changed it to TypeError.
            wrap_it = False
        except NameError:
            wrap_it = True
        else:
            type_hints.pop('return', None)
            wrap_it = type_hints != {}
        if wrap_it:
            return wrap_fun(inject(fun), injector)

    if hasattr(fun, 'view_class'):
        return wrap_class_based_view(fun, injector)

    return fun


def wrap_function(fun: Callable, injector: Injector) -> Callable:
    @functools.wraps(fun)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return injector.call_with_injection(callable=fun, args=args, kwargs=kwargs)
    return wrapper


def wrap_class_based_view(fun: Callable, injector: Injector) -> Callable:
    cls = cast(Any, fun).view_class
    name = fun.__name__

    closure_contents = (c.cell_contents for c in cast(Any, fun).__closure__)
    fun_closure = dict(zip(fun.__code__.co_freevars, closure_contents))
    try:
        class_kwargs = fun_closure['class_kwargs']
    except KeyError:
        # Most likely flask_restful resource, we'll see in a second
        flask_restful_api = fun_closure['self']
        # flask_restful wraps ResourceClass.as_view() result in its own wrapper
        # the as_view() result is available under 'resource' name in this closure
        fun = fun_closure['resource']
        fun_closure = {}
        class_kwargs = {}
        # if the lines above succeeded we're quite sure it's flask_restful resource
    else:
        flask_restful_api = None
        class_args = fun_closure.get('class_args')
        assert not class_args, 'Class args are not supported, use kwargs instead'

    if (
        flask_restful_api and
        flask_restplus and
        isinstance(flask_restful_api, flask_restplus.Api)
    ):
        # This is flask_restplus' add_resource implementation:
        #
        #     def add_resource(self, resource, *urls, **kwargs):
        #     (...)
        #     args = kwargs.pop('resource_class_args', [])
        #     if isinstance(args, tuple):
        #         args = list(args)
        #     args.insert(0, self)
        #     kwargs['resource_class_args'] = args
        #
        #     super(Api, self).add_resource(resource, *urls, **kwargs)
        #
        # Correspondingly, flask_restplus.Resource's constructor expects
        # flask_restplus.Api instance in its first argument; since we detected
        # that we're very likely dealing with flask_restplus we'll provide the Api
        # instance as keyword argument instead (it'll work just as well unless
        # flask_restplus changes the name of the parameter; also
        # Injector.create_object doesn't support extra positional arguments anyway).
        if 'api' in class_kwargs:
            raise AssertionError('api keyword argument is reserved')

        class_kwargs['api'] = flask_restful_api

    # This section is flask.views.View.as_view code modified to make the injection
    # possible without relying on modifying view function in place
    # Copyright (c) 2014 by Armin Ronacher and Flask contributors, see Flask
    # license for details

    def view(*args: Any, **kwargs: Any) -> Any:
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
    cast(Any, view).view_class = cls
    view.__name__ = name
    view.__doc__ = cls.__doc__
    view.__module__ = cls.__module__
    cast(Any, view).methods = cls.methods

    fun = view

    if flask_restful_api:
        return wrap_flask_restful_resource(fun, flask_restful_api, injector)

    return fun


def wrap_flask_restful_resource(
    fun: Callable,
    flask_restful_api: FlaskRestfulApi,
    injector: Injector,
) -> Callable:
    """
    This is needed because of how flask_restful views are registered originally.

    :type flask_restful_api: :class:`flask_restful.Api`
    """
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

    @functools.wraps(fun)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        resp = fun(*args, **kwargs)
        if isinstance(resp, Response):  # There may be a better way to test
            return resp
        data, code, headers = unpack(resp)
        return flask_restful_api.make_response(data, code, headers=headers)

    # end of flask_restful code

    return wrapper


class CachedProviderWrapper(Provider):
    def __init__(self, old_provider: Provider) -> None:
        self._old_provider = old_provider
        self._cache = {}  # type: Dict[int, Any]

    def get(self, injector: Injector) -> Any:
        key = id(injector)
        try:
            return self._cache[key]
        except KeyError:
            instance = self._cache[key] = self._old_provider.get(injector)
            return instance


class RequestScope(Scope):
    """A scope whose object lifetime is tied to a request.

    @request
    class Session:
        pass
    """

    # We don't want to assign here, just provide type hints
    if False:
        _local_manager = None  # type: LocalManager
        _locals = None  # type: Any

    def cleanup(self) -> None:
        self._local_manager.cleanup()

    def prepare(self) -> None:
        self._locals.scope = {}

    def configure(self) -> None:
        self._locals = Local()
        self._local_manager = LocalManager([self._locals])
        self.prepare()

    def get(self, key: Any, provider: Provider) -> Any:
        try:
            return self._locals.scope[key]
        except KeyError:
            new_provider = self._locals.scope[key] = CachedProviderWrapper(provider)
            return new_provider


request = ScopeDecorator(RequestScope)


_ModuleT = Union[Callable[[Binder], Any], Module]


class FlaskInjector:
    def __init__(
        self,
        app: flask.Flask,
        modules: Iterable[_ModuleT] = [],
        injector: Injector = None,
        request_scope_class: type = RequestScope,
    ) -> None:
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
        if not injector:
            injector = Injector()

        modules = list(modules)
        modules.insert(0, FlaskModule(app=app, request_scope_class=request_scope_class))
        for module in modules:
            injector.binder.install(module)

        for container in (
                app.view_functions,
                app.before_request_funcs,
                app.after_request_funcs,
                app.teardown_request_funcs,
                app.template_context_processors,
                app.jinja_env.globals,
                app.error_handler_spec,
        ):
            process_dict(container, injector)

        # This is to make sure that mypy sees a non-nullable variable
        # in the closures below, otherwise it'd complain that injector
        # union may not have get attribute
        injector_not_null = injector

        def reset_request_scope_before(*args: Any, **kwargs: Any) -> None:
            injector_not_null.get(request_scope_class).prepare()

        def reset_request_scope_after(*args: Any, **kwargs: Any) -> None:
            injector_not_null.get(request_scope_class).cleanup()

        app.before_request_funcs.setdefault(
            None, []).insert(0, reset_request_scope_before)
        app.teardown_request(reset_request_scope_after)

        self.injector = injector_not_null
        self.app = app


def process_dict(d: Dict, injector: Injector) -> None:
    for key, value in d.items():
        if isinstance(value, list):
            value[:] = [wrap_fun(fun, injector) for fun in value]
        elif hasattr(value, '__call__'):
            d[key] = wrap_fun(value, injector)
        elif isinstance(value, dict):
            process_dict(value, injector)


class FlaskModule(Module):
    def __init__(self, app: flask.Flask, request_scope_class: type = RequestScope) -> None:
        self.app = app
        self.request_scope_class = request_scope_class

    def configure(self, binder: Binder) -> None:
        binder.bind_scope(self.request_scope_class)
        binder.bind(flask.Flask, to=self.app, scope=singleton)
        binder.bind(Config, to=self.app.config, scope=singleton)
        binder.bind(Request, to=lambda: flask.request)
