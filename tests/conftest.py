import pytest
from app import create_app
from app.extensions import db
from app.models import User, CompanySettings

@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        # Seed initial data needed for tests
        settings = CompanySettings(company_name='Test Company', base_currency='USD')
        db.session.add(settings)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def runner(app):
    return app.test_cli_runner()

@pytest.fixture
def session(app):
    with app.app_context():
        yield db.session
