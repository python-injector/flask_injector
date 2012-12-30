
from injector import inject, Injector
from flask import Blueprint, Flask

from flask_injector import FlaskInjector

def test_injection_in_preconfigured_views():
    pages = Blueprint('pages', __name__)

    @pages.route('/')
    @inject(content=str)
    def index(content):
        return content

    app = Flask(__name__)
    app.register_blueprint(pages)

    def conf(binder):
        binder.bind(str, to="something")

    flask_injector = FlaskInjector(modules=[conf], inject_native_views=True)
    flask_injector.init_app(app)

    with app.test_client() as c:
        response = c.get('/')
        assert (response.data == "something")
