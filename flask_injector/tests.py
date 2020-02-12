import gc
import json
import warnings
from functools import partial
from typing import NewType

import flask_restful
import flask_restplus
import flask_restx
from eventlet import greenthread
from injector import __version__ as injector_version, CallableProvider, inject, Scope
from flask import Blueprint, Flask
from flask.templating import render_template_string
from flask.views import View
from nose.tools import eq_

from flask_injector import request, FlaskInjector


def test_injections():
    l = [1, 2, 3]
    counter = [0]

    def inc():
        counter[0] += 1

    def conf(binder):
        binder.bind(str, to="something")
        binder.bind(list, to=l)

    app = Flask(__name__)

    @app.route('/view1')
    def view1(content: str):
        inc()
        return render_template_string(content)

    class View2(View):
        @inject
        def __init__(self, *args, content: list, **kwargs):
            self.content = content
            super().__init__(*args, **kwargs)

        def dispatch_request(self):
            inc()
            return render_template_string('%s' % self.content)

    @app.before_request
    def br(c: list):
        inc()
        eq_(c, l)

    @app.before_first_request
    def bfr(c: list):
        inc()
        eq_(c, l)

    @app.after_request
    def ar(response_class, c: list):
        inc()
        eq_(c, l)
        return response_class

    @app.context_processor
    def cp(c: list):
        inc()
        eq_(c, l)
        return {}

    @app.teardown_request
    def tr(sender, exc=None, c: list = None):
        inc()
        eq_(c, l)

    app.add_url_rule('/view2', view_func=View2.as_view('view2'))

    FlaskInjector(app=app, modules=[conf])

    with app.test_client() as c:
        response = c.get('/view1')
        eq_(response.get_data(as_text=True), "something")

    with app.test_client() as c:
        response = c.get('/view2')
        eq_(response.get_data(as_text=True), '%s' % (l,))

    eq_(counter[0], 11)


def test_resets():
    app = Flask(__name__)

    counter = [0]

    class OurScope(Scope):
        def __init__(self, injector):
            pass

        def prepare(self):
            pass

        def cleanup(self):
            counter[0] += 1

    @app.route('/')
    def index():
        return 'asd'

    FlaskInjector(app, request_scope_class=OurScope)

    eq_(counter[0], 0)

    with app.test_client() as c:
        c.get('/')

    eq_(counter[0], 1)


def test_memory_leak():
    # The RequestScope holds references to GreenThread objects which would
    # cause memory leak

    # More explanation below
    #
    # In Werkzeug locals are indexed using values returned by ``get_ident`` function:
    #
    # try:
    #    from greenlet import getcurrent as get_ident
    # except ImportError:
    #     try:
    #         from thread import get_ident
    #     except ImportError:
    #         from _thread import get_ident
    #
    # This is what LocalManager.cleanup runs indirectly (__ident_func__
    # points to get_ident unless it's overridden):
    #
    # self.__storage__.pop(self.__ident_func__(), None)

    # If something's assigned in local storage *after* the cleanup is done an entry
    # in internal storage under "the return value of get_ident()" key is recreated
    # and a reference to the key will be kept forever.
    #
    # This is not strictly related to Eventlet/GreenThreads but that's how
    # the issue manifested itself so the test reflects that.
    app = Flask(__name__)

    FlaskInjector(app)

    @app.route('/')
    def index():
        return 'test'

    def get_request():
        with app.test_client() as c:
            c.get('/')

    green_thread = greenthread.spawn(get_request)
    green_thread.wait()
    # Delete green_thread so the GreenThread object is dereferenced
    del green_thread
    # Force run garbage collect to make sure GreenThread object is collected if
    # there is no memory leak
    gc.collect()
    greenthread_count = len([obj for obj in gc.get_objects() if type(obj) is greenthread.GreenThread])

    eq_(greenthread_count, 0)


def test_doesnt_raise_deprecation_warning():
    app = Flask(__name__)

    def provide_str():
        return 'this is string'

    def configure(binder):
        binder.bind(str, to=CallableProvider(provide_str), scope=request)

    @app.route('/')
    def index(s: str):
        return s

    FlaskInjector(app=app, modules=[configure])

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        with app.test_client() as c:
            c.get('/')
        eq_(len(w), 0, map(str, w))


def test_jinja_env_globals_support_injection():
    app = Flask(__name__)

    def configure(binder):
        binder.bind(str, to='xyz')

    def do_something_helper(s: str):
        return s

    app.jinja_env.globals['do_something'] = do_something_helper

    @app.route('/')
    def index():
        return render_template_string('{{ do_something() }}')

    FlaskInjector(app=app, modules=[configure])

    with app.test_client() as c:
        eq_(c.get('/').get_data(as_text=True), 'xyz')


def test_error_handlers_support_injection():
    app = Flask(__name__)

    class CustomException(Exception):
        pass

    @app.route('/custom-exception')
    def custom_exception():
        raise CustomException()

    @app.errorhandler(404)
    def handle_404(error, s: str):
        return s, 404

    @app.errorhandler(CustomException)
    def handle_custom_exception(error, s: str):
        return s, 500

    def configure(binder):
        binder.bind(str, to='injected content')

    FlaskInjector(app=app, modules=[configure])

    with app.test_client() as c:
        response = c.get('/this-page-does-not-exist')
        eq_((response.status_code, response.get_data(as_text=True)), (404, 'injected content'))

        response = c.get('/custom-exception')
        eq_((response.status_code, response.get_data(as_text=True)), (500, 'injected content'))


def test_view_functions_arent_modified_globally():
    # Connected to GH #6 "Doing multiple requests on a flask test client on an injected route
    # fails for all but the first request"
    # The code would modify view functions generated by View.as_view(), it wasn't an issue with
    # views added directly to an application but if function was added to a blueprint and
    # that blueprint was used in multiple applications it'd raise an error

    class MyView(View):
        pass

    blueprint = Blueprint('test', __name__)
    blueprint.add_url_rule('/', view_func=MyView.as_view('view'))

    app = Flask(__name__)
    app.register_blueprint(blueprint)
    FlaskInjector(app=app)

    app2 = Flask(__name__)
    app2.register_blueprint(blueprint)

    # it'd fail here
    FlaskInjector(app=app2)


def test_view_args_and_class_args_are_passed_to_class_based_views():
    class MyView(View):
        def __init__(self, class_arg):
            self.class_arg = class_arg

        def dispatch_request(self, dispatch_arg):
            return '%s %s' % (self.class_arg, dispatch_arg)

    app = Flask(__name__)
    app.add_url_rule('/<dispatch_arg>', view_func=MyView.as_view('view', class_arg='aaa'))

    FlaskInjector(app=app)

    client = app.test_client()
    response = client.get('/bbb')
    print(response.data)
    eq_(response.data, b'aaa bbb')


def test_flask_restful_integration_works():
    class HelloWorld(flask_restful.Resource):
        @inject
        def __init__(self, *args, int: int, **kwargs):
            self._int = int
            super().__init__(*args, **kwargs)

        def get(self):
            return {'int': self._int}

    app = Flask(__name__)
    api = flask_restful.Api(app)

    api.add_resource(HelloWorld, '/')

    FlaskInjector(app=app)

    client = app.test_client()
    response = client.get('/')
    data = json.loads(response.data.decode('utf-8'))
    eq_(data, {'int': 0})


def test_flask_restplus_integration_works():
    app = Flask(__name__)
    api = flask_restplus.Api(app)

    class HelloWorld(flask_restplus.Resource):
        @inject
        def __init__(self, *args, int: int, **kwargs):
            self._int = int
            super().__init__(*args, **kwargs)

        # This decorator is crucial to have in this test. We need it to make sure that
        # the test fails with "AttributeError: 'NoneType' object has no attribute '_validate'"
        # if we don't pass the API instance to the Resource constructor correctly. The failure is
        # triggered by the presence of the __apidoc__ attribute on the method being called,
        # hence the decorator, which assigns it.
        @api.doc()
        def get(self):
            return {'int': self._int}

    api.add_resource(HelloWorld, '/hello')

    FlaskInjector(app=app)

    client = app.test_client()
    response = client.get('/hello')
    data = json.loads(response.data.decode('utf-8'))
    eq_(data, {'int': 0})


def test_flask_restx_integration_works():
    app = Flask(__name__)
    api = flask_restx.Api(app)

    class HelloWorld(flask_restx.Resource):
        @inject
        def __init__(self, *args, int: int, **kwargs):
            self._int = int
            super().__init__(*args, **kwargs)

        @api.doc()
        def get(self):
            return {'int': self._int}

    api.add_resource(HelloWorld, '/hello')

    FlaskInjector(app=app)

    client = app.test_client()
    response = client.get('/hello')
    data = json.loads(response.data.decode('utf-8'))
    eq_(data, {'int': 0})


def test_request_scope_not_started_before_any_request_made_regression():
    # Version 0.6.1 (patch cacaef6 specifially) broke backwards compatibility in
    # a relatively subtle way. The code used to support RequestScope even in
    # the thread that originally created the Injector object. After cacaef6 an
    # "AttributeError: scope" exception would be raised.
    #
    # For compatibility reason I'll restore the old behaviour, we can
    # deprecate it later if needed

    def configure(binder):
        binder.bind(str, to='this is string', scope=request)

    app = Flask(__name__)
    flask_injector = FlaskInjector(app=app, modules=[configure])
    eq_(flask_injector.injector.get(str), 'this is string')


def test_noninstrospectable_hooks_dont_crash_everything():
    app = Flask(__name__)

    def do_nothing():
        pass

    app.before_request(partial(do_nothing))

    # It'd crash here
    FlaskInjector(app=app)


def test_instance_methods():
    class HelloWorldService:
        def get_value(self):
            return "test message 1"

    class HelloWorld:
        def from_injected_service(self, service: HelloWorldService):
            return service.get_value()

        def static_value(self):
            return "test message 2"

    app = Flask(__name__)
    hello_world = HelloWorld()
    app.add_url_rule('/from_injected_service', 'from_injected_service', hello_world.from_injected_service)
    app.add_url_rule('/static_value', 'static_value', hello_world.static_value)

    FlaskInjector(app=app)

    client = app.test_client()
    response = client.get('/from_injected_service')
    eq_(response.data.decode('utf-8'), "test message 1")

    response = client.get('/static_value')
    eq_(response.data.decode('utf-8'), "test message 2")


if injector_version >= '0.12':

    def test_forward_references_work():
        app = Flask(__name__)

        @app.route('/')
        def index(x: 'X'):
            return x.message

        FlaskInjector(app=app)

        # The class needs to be module-global in order for the string -> object
        # resolution mechanism to work. I could make it work with locals but it
        # doesn't seem worth it.
        global X

        class X:
            def __init__(self) -> None:
                self.message = 'Hello World'

        try:
            client = app.test_client()
            response = client.get('/')
            eq_(response.data.decode(), 'Hello World')
        finally:
            del X


def test_request_scope_covers_teardown_request_handlers():
    app = Flask(__name__)
    UserID = NewType('UserID', int)

    @app.route('/')
    def index():
        return 'hello'

    @app.teardown_request
    def on_teardown(exc, user_id: UserID):
        eq_(user_id, 321)

    def configure(binder):
        binder.bind(UserID, to=321, scope=request)

    FlaskInjector(app=app, modules=[configure])
    client = app.test_client()
    response = client.get('/')
    eq_(response.data.decode(), 'hello')
