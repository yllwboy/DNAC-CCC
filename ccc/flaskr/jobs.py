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


import queue

from flask import (Blueprint, flash, g, redirect, render_template, request,
                   url_for)
from werkzeug.exceptions import abort

from flaskr.auth import login_required
from flaskr.db import get_db
from flaskr.dnacs import get_dnac

actionqueue = queue.Queue(maxsize=10)

bp = Blueprint("jobs", __name__)


@bp.route("/dnacs/<int:id>/jobs")
@login_required
def index(id):
    db = get_db()
    user_dnac = (
        db
        .execute(
            "SELECT *"
            " FROM user_dnac"
            " WHERE user_id = ? AND dnac_id = ?",
            (g.user["id"], id),
        )
        .fetchone()
    )
    if user_dnac is None:
        abort(403)
    jobs = db.execute(
        "SELECT j.id, author_id, dnac_id, title, addr, created, frequency, activated"
        " FROM job j JOIN dnac d ON j.dnac_id = d.id"
        " WHERE dnac_id = ?"
        " ORDER BY title",
        (id,),
    ).fetchall()
    return render_template("jobs/index.html", id=id, jobs=jobs)


def get_job(id, check_author=True):
    job = (
        get_db()
        .execute(
            "SELECT *"
            " FROM job"
            " WHERE id = ?",
            (id,),
        )
        .fetchone()
    )
    user_dnac = (
        get_db()
        .execute(
            "SELECT *"
            " FROM user_dnac"
            " WHERE user_id = ? AND dnac_id = ?",
            (g.user["id"], job["dnac_id"]),
        )
        .fetchone()
    )

    if job is None:
        abort(404, f"Job id {id} doesn't exist.")

    if check_author and user_dnac is None:
        abort(403)

    return job


@bp.route("/dnacs/<int:id>/jobs/create", methods=("GET", "POST"))
@login_required
def create(id):
    if request.method == "POST":
        title = request.form["title"]
        frequency = int(request.form["weeks"]) * 10080 + int(request.form["days"]) * 1440 + int(request.form["hours"]) * 60 + int(request.form["minutes"])
        activated = 0
        error = None
        
        if "activated" in request.form:
            activated = 1

        if not title:
            error = "Title is required."
        elif not frequency:
            error = "Frequency is required."

        if error is not None:
            flash(error)
        else:
            db = get_db()
            db.execute(
                "INSERT INTO job (author_id, dnac_id, title, frequency, activated) VALUES (?, ?, ?, ?, ?)",
                (g.user["id"], id, title, frequency, activated),
            )
            job = db.execute(
                "SELECT last_insert_rowid()",
            )
            db.commit()
            actionqueue.put({"action": "create", "job": job, "dnac": get_dnac(id), "frequency": frequency, "activated": activated})
            return redirect(url_for("jobs.index", id=id))

    return render_template("jobs/create.html")


@bp.route("/dnacs/<int:id>/jobs/<int:id_job>/update", methods=("GET", "POST"))
@login_required
def update(id, id_job):
    if request.method == "POST":
        get_job(id_job)

        frequency = int(request.form["weeks"]) * 10080 + int(request.form["days"]) * 1440 + int(request.form["hours"]) * 60 + int(request.form["minutes"])
        activated = 0
        error = None

        if not frequency:
            error = "Frequency is required."
        
        if "activated" in request.form:
            activated = 1

        if error is not None:
            flash(error)
        else:
            db = get_db()
            db.execute(
                "UPDATE job SET created = CURRENT_TIMESTAMP, frequency = ?, activated = ? WHERE id = ?",
                (frequency, activated, id_job)
            )
            db.commit()
            actionqueue.put({"action": "update", "job": id_job, "dnac": get_dnac(id), "frequency": frequency, "activated": activated})

    return redirect(url_for("jobs.index", id=id))


@bp.route("/dnacs/<int:id>/jobs/<int:id_job>/delete", methods=("POST",))
@login_required
def delete(id, id_job):
    get_job(id_job)
    db = get_db()
    db.execute("DELETE FROM job WHERE id = ?", (id_job,))
    actionqueue.put({"action": "delete", "job": id_job})
    db.commit()
    return redirect(url_for("jobs.index", id=id))
