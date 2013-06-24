from injector import inject, Injector
from flask import Flask
from flask.templating import render_template_string
from flask.views import View
from nose.tools import eq_

from flask_injector import init_app, post_init_app


def test_injections():
    l = [1, 2, 3]
    counter = [0]

    def inc():
        counter[0] += 1

    def conf(binder):
        binder.bind(str, to="something")
        binder.bind(list, to=l)

    app = Flask(__name__)
    injector = init_app(app=app, modules=[conf])

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

    post_init_app(app, injector)

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

    injector = init_app(app=app, request_scope_class=Scope)

    @app.route('/')
    def index():
        eq_(counter[0], 1)
        return 'asd'

    post_init_app(app, injector, request_scope_class=Scope)

    eq_(counter[0], 0)

    with app.test_client() as c:
        c.get('/')

    eq_(counter[0], 2)
