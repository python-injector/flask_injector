from injector import inject
from flask import Blueprint, Flask

from flask_injector import FlaskInjector, route


def test_injection_in_preconfigured_views():
    pages = Blueprint('pages', __name__)

    @pages.route('/')
    @inject(content=str)
    def index(content):
        return content

    app = Flask(__name__)
    app.register_blueprint(pages)
    app.debug = True

    def conf(binder):
        binder.bind(str, to="something")

    flask_injector = FlaskInjector(modules=[conf], inject_native_views=True)
    flask_injector.init_app(app)

    with app.test_client() as c:
        response = c.get('/')
        assert (response.data == "something"), response.data


def test_multiple_routes():
    @route('/', defaults={'page': 'none'})
    @route('/<page>')
    def index(page=None):
        return page

    app = Flask(__name__)
    flask_injector = FlaskInjector([index])
    flask_injector.init_app(app)

    with app.test_client() as c:
        response = c.get('/')
        assert response.data == 'none', response.data
        response = c.get('/boom')
        assert response.data == 'boom', response.data
