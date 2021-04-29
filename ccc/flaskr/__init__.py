#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Configuration Compliance Check

Copyright (c) 2021 Cisco and/or its affiliates.

This software is licensed to you under the terms of the Cisco Sample
Code License, Version 1.1 (the "License"). You may obtain a copy of the
License at

               https://developer.cisco.com/docs/licenses

All use of the material herein must be in accordance with the terms of
the License. All rights not expressly granted by the License are
reserved. Unless required by applicable law or agreed to separately in
writing, software distributed under the License is distributed on an "AS
IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
or implied.

"""


from __future__ import absolute_import, division, print_function

__author__ = "Héctor Cavalcanti Saavedra <hcavalca@cisco.com>"
__contributors__ = [
    "Sarah Louise Justin <sajustin@cisco.com>"
]
__copyright__ = "Copyright (c) 2021 Cisco and/or its affiliates."
__license__ = "Cisco Sample Code License, Version 1.1"


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
