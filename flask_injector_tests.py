import warnings

from injector import CallableProvider, inject
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

        def reset(self):
            counter[0] += 1

    @app.route('/')
    def index():
        eq_(counter[0], 1)
        return 'asd'

    FlaskInjector(app, request_scope_class=Scope)

    eq_(counter[0], 0)

    with app.test_client() as c:
        c.get('/')

    eq_(counter[0], 2)


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
