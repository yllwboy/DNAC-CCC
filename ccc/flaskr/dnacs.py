from flask import (Blueprint, flash, g, redirect, render_template, request,
                   url_for)
from werkzeug.exceptions import abort

from flaskr.auth import login_required
from flaskr.ccc import backup
from flaskr.db import get_db

bp = Blueprint("dnacs", __name__)


@bp.route("/dnacs")
@login_required
def index():
    db = get_db()
    dnacs = db.execute(
        "SELECT id, addr, dnac_user, dnac_pass, restconf_user, restconf_pass"
        " FROM dnac d JOIN user_dnac ud ON d.id = ud.dnac_id"
        " WHERE user_id = ?"
        " ORDER BY addr",
        (g.user["id"],),
    ).fetchall()
    return render_template("dnacs/index.html", dnacs=dnacs)


def get_dnac(id):
    dnac = (
        get_db()
        .execute(
            "SELECT id, addr, dnac_user, dnac_pass, restconf_user, restconf_pass"
            " FROM dnac d JOIN user_dnac ud ON d.id = ud.dnac_id"
            " WHERE id = ? AND user_id = ?",
            (id, g.user["id"]),
        )
        .fetchone()
    )

    if dnac is None:
        abort(404, f"DNAC id {id} doesn't exist.")

    return dnac


@bp.route("/dnacs/<int:id>/globalbackup")
@login_required
def globalbackup(id):
    dnac = get_dnac(id)
    backup(dnac, True, False)
    flash("Global backup completed successfully!")
    return redirect(url_for("dnacs.index"))


@bp.route("/dnacs/create", methods=("GET", "POST"))
@login_required
def create():
    if request.method == "POST":
        addr = request.form["addr"]
        dnac_user = request.form["dnac_user"]
        dnac_pass = request.form["dnac_pass"]
        restconf_user = request.form["restconf_user"]
        restconf_pass = request.form["restconf_pass"]
        error = None

        if not addr:
            error = "Address is required."
        elif not dnac_user:
            error = "DNAC username is required."
        elif not dnac_pass:
            error = "DNAC password is required."
        
        if error is not None:
            flash(error)
        else:
            db = get_db()
            db.execute(
                "INSERT INTO dnac (addr) VALUES (?)",
                (addr,),
            )
            db.commit()
            dnac = (
                db
                .execute(
                    "SELECT id"
                    " FROM dnac d"
                    " WHERE addr = ?",
                    (addr,),
                )
                .fetchone()
            )
            if dnac is None:
                abort(500, f"DNAC {addr} doesn't exist.")
            if not restconf_user or not restconf_pass:
                db.execute(
                    "INSERT INTO user_dnac VALUES (?, ?, ?, ?)",
                    (g.user["id"], dnac["id"], dnac_user, dnac_pass),
                )
            else:
                db.execute(
                    "INSERT INTO user_dnac VALUES (?, ?, ?, ?, ?, ?)",
                    (g.user["id"], dnac["id"], dnac_user, dnac_pass, restconf_user, restconf_pass),
                )
            db.commit()
            return redirect(url_for("dnacs.index"))

    return render_template("dnacs/create.html")


@bp.route("/dnacs/<int:id>/update", methods=("GET", "POST"))
@login_required
def update(id):
    dnac = get_dnac(id)

    if request.method == "POST":
        addr = request.form["addr"]
        error = None

        if not addr:
            error = "Address is required."

        if error is not None:
            flash(error)
        else:
            db = get_db()
            db.execute(
                "UPDATE dnac SET addr = ? WHERE id = ?", (addr, id)
            )
            db.commit()
            return redirect(url_for("dnacs.index"))

    return render_template("dnacs/update.html", dnac=dnac)


@bp.route("/dnacs/<int:id>/delete", methods=("POST",))
@login_required
def delete(id):
    get_dnac(id)
    db = get_db()
    db.execute("DELETE FROM dnac WHERE id = ?", (id,))
    db.commit()
    return redirect(url_for("dnacs.index"))
