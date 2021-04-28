import os
from importlib import resources
from pathlib import Path

from flask import Flask, abort, render_template, send_file, Response
from flask_socketio import SocketIO, emit

from .. import core as c
from .. import resources as res_mod

join = os.path.join

config = c.load_config()
asset_dir = Path(config.save_path) / "assets"

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)

@app.route('/')
def index():
    return render_template("index.html", asset_dir="/assets/")


@app.route('/assets/<path:file>')
def assets(file):
    file = asset_dir.joinpath(file)
    if file.exists():
        return send_file(file)
    else:
        return abort(404)


@app.route('/res/<file>')
def res(file):
    data = resources.read_text(res_mod, file)
    return Response(data, mimetype="text/css")


@socketio.event
def test_event(*args):
    print('received args:')
    for a in args:
        print(a)


@socketio.event
def get_notes(pattern, group, tags):
    rows = c.filter_files(pattern, group, tags)
    emit("notes", [(row.id, row.title) for row in rows])


@socketio.event
def get_note(id):
    htmlpath = c.html_path(id, config)
    path = c.md_path(id, config)
    if (not htmlpath.exists()) or htmlpath.stat().st_mtime < path.stat().st_mtime:
        htmlpath.write_text(c.make_html(path.read_text()))
    html = htmlpath.read_text()
    search_str = '<body class="body">'
    start = html.find(search_str)
    assert start != -1
    end = html.find("</body>")
    assert end != -1
    emit("note", html[start + len(search_str): end])


def run():
    socketio.run(app)
