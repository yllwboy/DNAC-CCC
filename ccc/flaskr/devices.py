import difflib

from flask import (Blueprint, flash, g, redirect, render_template, request,
                   url_for)
from flask.helpers import make_response
from werkzeug.exceptions import abort

from flaskr.auth import login_required
from flaskr.ccc import search, update_devices, restconf_restore
from flaskr.db import get_db

bp = Blueprint("devices", __name__)


@bp.route("/dnacs/<int:id>/devices", methods=("GET", "POST"))
@login_required
def index(id):
    if request.method == "POST":
        a = request.form["a"]
        a_ver = request.form["a"+a]
        b = request.form["b"]
        b_ver = request.form["b"+b]
        
        error = None

        if not a:
            error = "Selection of the left version is required."
        elif not a_ver:
            error = "Left version is required."
        elif not b:
            error = "Selection of the right version is required."
        elif not b_ver:
            error = "Right version is required."
        

        if error is not None:
            flash(error)
        elif "view" in request.form:
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
        elif "restore" in request.form:
            device = (
                get_db()
                .execute(
                    "SELECT *"
                    " FROM device"
                    " WHERE id = ?",
                    (a,),
                )
                .fetchone()
            )
            backup = (
                get_db()
                .execute(
                    "SELECT *"
                    " FROM backup"
                    " WHERE id = ? AND config_type = 'RESTCONF'",
                    (a_ver,),
                )
                .fetchone()
            )
            if backup is None:
                abort(403, 'Invalid configuration version. Did you pick a RESTCONF version?')
            user_dnac = (
                get_db()
                .execute(
                    "SELECT *"
                    " FROM user_dnac"
                    " WHERE user_id = ? AND dnac_id = ?",
                    (g.user["id"], id),
                )
                .fetchone()
            )
            
            return "Response status code: {}".format(restconf_restore(device['addr'], backup['content'], user_dnac, None))

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


def get_device(id, check_owner=True):
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

    if check_owner and user_dnac is None:
        abort(403)

    return device


@bp.route("/dnacs/<int:id>/devices/search", methods=("GET", "POST"))
@login_required
def search_in_backups(id):
    if request.method == "POST":
        query = request.form["query"]
        selection = request.form["selection"]
        config_type = request.form["type"]
        error = None

        if not query:
            error = "Query is required."
        elif not selection:
            error = "Selection choice is required."
        elif not config_type:
            error = "Configuration type selection is required."
        
        if error is not None:
            flash(error)
        else:
            return render_template("devices/search.html", id=id, results=search(selection, config_type, query, id))
    
    return render_template("devices/search.html", id=id)


@bp.route("/backups/<int:id>")
@login_required
def view_backup(id):
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

@bp.route("/dnacs/<int:id>/devices/purge", methods=("GET", "POST"))
@login_required
def purge(id):
    db = get_db()
    if request.method == "POST":
        old = request.form["old"]

        if "disconnected" in request.form:
            db.execute("DELETE FROM backup WHERE id IN (SELECT b.id FROM backup b JOIN device d ON b.device_id = d.id WHERE dnac_id = ? AND connected = 0)", (id,))
            db.execute("DELETE FROM device WHERE dnac_id = ? AND connected = 0", (id,))
        
        if "backups" in request.form and old is not None:
            db.execute("DELETE FROM backup WHERE id IN (SELECT b.id FROM backup b JOIN device d ON b.device_id = d.id WHERE dnac_id = ? AND created < ?)", (id,old))
        
        db.commit()
        return redirect(url_for("devices.index", id=id))

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

    return render_template("devices/purge.html", dnac=dnac)