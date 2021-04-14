import difflib

from flask import (Blueprint, flash, g, redirect, render_template, request,
                   url_for)
from flask.helpers import make_response
from werkzeug.exceptions import abort

from flaskr.auth import login_required
from flaskr.ccc import search, update_devices
from flaskr.db import get_db

bp = Blueprint("devices", __name__)


@bp.route("/dnacs/<int:id>/devices", methods=("GET", "POST"))
@login_required
def index(id):
    """Show all the posts, most recent first."""
    if request.method == "POST":
        a = request.form["a"]
        a_ver = request.form["a"+a]
        b = request.form["b"]
        b_ver = request.form["b"+b]
        
        error = None

        if not a:
            error = "Title is required."

        if error is not None:
            flash(error)
        elif "view" in request.form:
            return redirect(url_for("devices.view_backup", id=a_ver))
        elif "restore" in request.form:
            return redirect(url_for("devices.view_backup", id=a_ver))
        elif "compare" in request.form:
            old = (
                get_db()
                .execute(
                    "SELECT *"
                    " FROM backup"
                    " WHERE id = ?",
                    (a_ver,),
                )
                .fetchone()
            )
            new = (
                get_db()
                .execute(
                    "SELECT *"
                    " FROM backup"
                    " WHERE id = ?",
                    (b_ver,),
                )
                .fetchone()
            )
            hd = difflib.HtmlDiff()
            
            return hd.make_file(old['content'].splitlines(), new['content'].splitlines())
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
    
    dnac = (
        db
        .execute(
            "SELECT *"
            " FROM dnac"
            " WHERE id = ?",
            (id,),
        )
        .fetchone()
    )

    update_devices(dnac, user_dnac)

    devices = db.execute(
        "SELECT *"
        " FROM device"
        " WHERE dnac_id = ?"
        " ORDER BY hostname",
        (id,),
    ).fetchall()
    backups = db.execute(
        "SELECT b.id, dnac_id, device_id, created, config_type, content"
        " FROM backup b JOIN device d ON b.device_id = d.id"
        " WHERE dnac_id = ?"
        " ORDER BY created DESC",
        (id,),
    ).fetchall()
    
    return render_template("devices/index.html", id=id, devices=devices, backups=backups)


def get_device(id, check_author=True):
    """Get a post and its author by id.

    Checks that the id exists and optionally that the current user is
    the author.

    :param id: id of post to get
    :param check_author: require the current user to be the author
    :return: the post with author information
    :raise 404: if a post with the given id doesn't exist
    :raise 403: if the current user isn't the author
    """
    device = (
        get_db()
        .execute(
            "SELECT *"
            " FROM device"
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
            (g.user["id"], device["dnac_id"]),
        )
        .fetchone()
    )

    if device is None:
        abort(404, f"Device id {id} doesn't exist.")

    if check_author and user_dnac is None:
        abort(403)

    return device


@bp.route("/dnacs/<int:id>/devices/search", methods=("GET", "POST"))
@login_required
def search_in_backups(id):
    """Create a new post for the current user."""
    if request.method == "POST":
        query = request.form["query"]
        selection = request.form["selection"]
        config_type = request.form["type"]
        error = None

        if not query:
            error = "Query is required."

        if error is not None:
            flash(error)
        else:
            return render_template("devices/results.html", results=search(selection, config_type, query, id))
    
    return render_template("devices/search.html", id=id)


@bp.route("/backups/<int:id>")
@login_required
def view_backup(id):
    """Show all the posts, most recent first."""
    db = get_db()
    backup = (
        db
        .execute(
            "SELECT *"
            " FROM backup"
            " WHERE id = ?",
            (id,),
        )
        .fetchone()
    )
    if backup is None:
        abort(404)
    
    device = (
        db
        .execute(
            "SELECT *"
            " FROM device"
            " WHERE id = ?",
            (backup['device_id'],),
        )
        .fetchone()
    )

    user_dnac = (
        db
        .execute(
            "SELECT *"
            " FROM user_dnac"
            " WHERE user_id = ? AND dnac_id = ?",
            (g.user["id"], device['dnac_id']),
        )
        .fetchone()
    )
    if user_dnac is None:
        abort(403)
    
    response = make_response(backup['content'], 200)
    response.mimetype = "text/plain"
    return response
