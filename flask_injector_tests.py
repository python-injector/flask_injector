import gc
import json
import warnings

import flask_restful
import flask_restplus
from eventlet import greenthread
from injector import CallableProvider, inject
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
    @inject(content=str)
    def view1(content):
        inc()
        return render_template_string(content)

    @inject(content=list)
    class View2(View):
        def dispatch_request(self):
            inc()
            return render_template_string('%s' % self.content)

    @app.before_request
    @inject(c=list)
    def br(c):
        inc()
        eq_(c, l)

    @app.after_request
    @inject(c=list)
    def ar(response_class, c):
        inc()
        eq_(c, l)
        return response_class

    @app.context_processor
    @inject(c=list)
    def cp(c):
        inc()
        eq_(c, l)
        return {}

    @app.teardown_request
    @inject(c=list)
    def tr(sender, exc=None, c=None):
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

    eq_(counter[0], 10)


def test_resets():
    app = Flask(__name__)

    counter = [0]

    class Scope(object):
        def __init__(self, injector):
            pass

        def prepare(self):
            pass

        def cleanup(self):
            counter[0] += 1

    @app.route('/')
    def index():
        return 'asd'

    FlaskInjector(app, request_scope_class=Scope)

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
    greenthread_count = len([
        obj for obj in gc.get_objects()
        if type(obj) is greenthread.GreenThread])

    eq_(greenthread_count, 0)


def test_doesnt_raise_deprecation_warning():
    app = Flask(__name__)

    def provide_str():
        return 'this is string'

    def configure(binder):
        binder.bind(str, to=CallableProvider(provide_str), scope=request)

    @app.route('/')
    @inject(s=str)
    def index(s):
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

    @inject(s=str)
    def do_something_helper(s):
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
    @inject(s=str)
    def handle_404(error, s):
        return s, 404

    @app.errorhandler(CustomException)
    @inject(s=str)
    def handle_custom_exception(error, s):
        return s, 500

    def configure(binder):
        binder.bind(str, to='injected content')

    FlaskInjector(app=app, modules=[configure])

    with app.test_client() as c:
        response = c.get('/this-page-does-not-exist')
        eq_((response.status_code, response.get_data(as_text=True)),
            (404, 'injected content'))

        response = c.get('/custom-exception')
        eq_((response.status_code, response.get_data(as_text=True)),
            (500, 'injected content'))


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

    @inject(_int=int)
    class HelloWorld(flask_restful.Resource):
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
    @inject(_int=int)
    class HelloWorld(flask_restplus.Resource):
        def get(self):
            return {'int': self._int}

    app = Flask(__name__)
    api = flask_restplus.Api(app)

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
