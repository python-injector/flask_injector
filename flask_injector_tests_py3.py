import json
import warnings

import flask_restful
import flask_restplus
from injector import CallableProvider
from flask import Flask
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

    FlaskInjector(app=app, modules=[conf], use_annotations=True)

    with app.test_client() as c:
        response = c.get('/view1')
        eq_(response.get_data(as_text=True), "something")

    with app.test_client() as c:
        response = c.get('/view2')
        eq_(response.get_data(as_text=True), '%s' % (l,))

    eq_(counter[0], 10)


def test_doesnt_raise_deprecation_warning():
    app = Flask(__name__)

    def provide_str():
        return 'this is string'

    def configure(binder):
        binder.bind(str, to=CallableProvider(provide_str), scope=request)

    @app.route('/')
    def index(s: str):
        return s

    FlaskInjector(app=app, modules=[configure], use_annotations=True)

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

    FlaskInjector(app=app, modules=[configure], use_annotations=True)

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

    FlaskInjector(app=app, modules=[configure], use_annotations=True)

    with app.test_client() as c:
        response = c.get('/this-page-does-not-exist')
        eq_((response.status_code, response.get_data(as_text=True)),
            (404, 'injected content'))

        response = c.get('/custom-exception')
        eq_((response.status_code, response.get_data(as_text=True)),
            (500, 'injected content'))


def test_flask_restful_integration_works():

    class HelloWorld(flask_restful.Resource):
        def __init__(self, *args, int: int, **kwargs):
            self._int = int
            super().__init__(*args, **kwargs)

        def get(self):
            return {'int': self._int}

    app = Flask(__name__)
    api = flask_restful.Api(app)

    api.add_resource(HelloWorld, '/')

    FlaskInjector(app=app, use_annotations=True)

    client = app.test_client()
    response = client.get('/')
    data = json.loads(response.data.decode('utf-8'))
    eq_(data, {'int': 0})


def test_flask_restplus_integration_works():
    class HelloWorld(flask_restplus.Resource):
        def __init__(self, *args, int: int, **kwargs):
            self._int = int
            super().__init__(*args, **kwargs)

        def get(self):
            return {'int': self._int}

    app = Flask(__name__)
    api = flask_restplus.Api(app)

    api.add_resource(HelloWorld, '/hello')

    FlaskInjector(app=app, use_annotations=True)

    client = app.test_client()
    response = client.get('/hello')
    data = json.loads(response.data.decode('utf-8'))
    eq_(data, {'int': 0})
