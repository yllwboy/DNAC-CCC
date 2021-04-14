import os
import threading

from flask import Flask
from flask.helpers import url_for
from werkzeug.serving import is_running_from_reloader
from werkzeug.utils import redirect

from flaskr.ccc import job_service


def create_app(test_config=None):
    """Create and configure an instance of the Flask application."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        # a default secret that should be overridden by instance config
        SECRET_KEY="dev",
        # store the database in the instance folder
        DATABASE=os.path.join(app.instance_path, "flaskr.sqlite"),
    )

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile("config.py", silent=True)
    else:
        # load the test config if passed in
        app.config.update(test_config)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # register the database commands
    from flaskr import db

    db.init_app(app)

    # apply the blueprints to the app
    from flaskr import auth, devices, dnacs, jobs

    app.register_blueprint(auth.bp)
    app.register_blueprint(dnacs.bp)
    app.register_blueprint(jobs.bp)
    app.register_blueprint(devices.bp)

    @app.route("/")
    def index():
        return redirect(url_for("dnacs.index"))
    
    app.add_url_rule("/", endpoint="index")
    
    if is_running_from_reloader():
        job_thread = threading.Thread(target=job_service, args=(jobs.actionqueue,))
        job_thread.start()
    
    return app
