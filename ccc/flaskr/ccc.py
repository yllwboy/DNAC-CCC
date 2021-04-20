import concurrent.futures
import os
import queue
import sqlite3
import time
from sqlite3.dbapi2 import Cursor

import pyzipper
import requests
import schedule
from requests.auth import HTTPBasicAuth

job_service_alive = False

class BackupError(RuntimeError):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


def producer(queue, products):
    for p in products:
        queue.put(p)


def backup_cons(queue, dnac, dnac_sess, restconf_sess):
    errors = []
    
    while True:
        d = queue.get()
        if d == "END":
            return errors

        folder = "Backups/{}/{}/".format(dnac['id'], d['id'])

        try:
            url = "https://{}/dna/intent/api/v1/network-device-archive/cleartext".format(dnac['addr'])
            payload='{"deviceId": ["'+d['id']+'"], "password": "W0AUH.nice.key"}'

            response = dnac_sess.request("POST", url, data=payload)

            url = "https://{}/dna/intent/api/v1/task/".format(dnac['addr']) + response.json()['response']['taskId']
            payload={}

            file_url = ''
            while file_url == '':
                response = dnac_sess.request("GET", url, data=payload)

                print(response.json()['response']['progress']+" => {}".format(response.json()['response']['isError']))

                if response.json()['response']['isError'] == True:
                    raise BackupError("[{}] {}".format(d['hostname'], response.json()['response']['progress']))
                
                if 'additionalStatusURL' in response.json()['response']:
                    file_url = response.json()['response']['additionalStatusURL']
                
                time.sleep(1)
            
            url = "https://{}/dna/intent".format(dnac['addr']) + file_url

            response = dnac_sess.request("GET", url, data=payload)

            try:
                os.makedirs(folder)
            except:
                print('Folder already created.')
            
            with open(os.path.join(folder, response.headers['fileName']), 'wb') as backup_file:
                print('Saving native config...')
                backup_file.write(response.content)
            
            db = sqlite3.connect(
                "instance/flaskr.sqlite", detect_types=sqlite3.PARSE_DECLTYPES
            )
            db.row_factory = sqlite3.Row
            
            device = db.execute(
                "SELECT *"
                " FROM device"
                " WHERE dnac_id = ? AND uuid = ?",
                (dnac["id"],d["id"]),
            ).fetchone()

            with pyzipper.AESZipFile(os.path.join(folder, response.headers['fileName'])) as zf:
                zf.setpassword(b'W0AUH.nice.key')
                files = zf.infolist()
                for f in files:
                    if 'STARTUP' in f.filename:
                        db.execute(
                            "INSERT INTO backup (device_id, config_type, content) VALUES (?, ?, ?)",
                            (device["id"], "CLI Startup", zf.read(f.filename).decode('ascii')),
                        )
                    elif 'RUNNING' in f.filename:
                        db.execute(
                            "INSERT INTO backup (device_id, config_type, content) VALUES (?, ?, ?)",
                            (device["id"], "CLI Running", zf.read(f.filename).decode('ascii')),
                        )

            db.commit()
            db.close()

            if restconf_sess is not None:
                url = "https://{}/restconf/data/Cisco-IOS-XE-native:native".format(d['managementIpAddress'])

                response = restconf_sess.request("GET", url, data=payload, timeout=5)

                # print(response.text)

                if response.status_code == 200:
                    db = sqlite3.connect(
                        "instance/flaskr.sqlite", detect_types=sqlite3.PARSE_DECLTYPES
                    )
                    db.row_factory = sqlite3.Row
                    db.execute(
                        "INSERT INTO backup (device_id, config_type, content) VALUES (?, ?, ?)",
                        (device["id"], "RESTCONF", response.text),
                    )
                    db.commit()
                    db.close()
                else:
                    url = "https://{}/restconf/data/netconf-state/capabilities".format(d['managementIpAddress'])
                    response = restconf_sess.request("GET", url, data=payload, timeout=5)
                    print(response.text)
            
        except BackupError as e:
            errors.append(e.args[0])
        except Exception as e:
            errors.append(e.args[0])


def backup(dnac, target, pubkey):
    processes = []
    
    dnac_sess = requests.Session()
    restconf_sess = None

    url = "https://{}/dna/system/api/v1/auth/token".format(dnac['addr'])

    payload={}
    dnac_sess.headers.update({'Content-Type': 'application/json'})
    dnac_sess.verify=pubkey

    if not dnac['restconf_user'] or not dnac['restconf_pass']:
        restconf_sess = requests.Session()

        restconf_sess.headers.update({
            'Content-Type': 'application/yang-data+json',
            'Accept': 'application/yang-data+json'
        })
        restconf_sess.verify=pubkey
        restconf_sess.auth=HTTPBasicAuth(dnac['restconf_user'], dnac['restconf_pass'])

    response = dnac_sess.request("POST", url, auth=HTTPBasicAuth(dnac['dnac_user'], dnac['dnac_pass']), data=payload)

    # print(response.text)

    dna_token = response.json()['Token']
    url = "https://{}/dna/intent/api/v1/network-device".format(dnac['addr'])
    dnac_sess.headers.update({'Content-Type': 'application/json', 'x-auth-token': dna_token})
    
    response = dnac_sess.request("GET", url, data=payload)
    
    # print(response.text)

    devices = []
    if target == True:
        devices = response.json()['response']
    else:
        for d in response.json()['response']:
            if d['id'] in target:
                devices.append(d)

    # print(devices)

    update_devices(dnac, dnac)

    pipeline = queue.Queue(maxsize=10)

    errors = "Errors: "

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        for i in range(9):
            devices.append("END")
            processes.append(executor.submit(backup_cons, pipeline, dnac, dnac_sess, restconf_sess))
        executor.submit(producer, pipeline, devices)

        for p in concurrent.futures.as_completed(processes):
            for e in p.result():
                errors += "{}, ".format(e)
        
    if errors == "Errors: ":
        return "Backup operation completed successfully!"
    else:
        return errors


def findall(p, s):
    '''Yields all the positions of
    the pattern p in the string s.'''
    i = s.find(p)
    while i != -1:
        yield i
        i = s.find(p, i+1)


def search_cons(queue, query):
    results = []

    while True:
        b = queue.get()
        if b == "END":
            return results

        # matches = list(re.finditer(re.escape(query), b['content']))
        matches = [(i, i+len(query)) for i in findall(query, b['content'])]
        if matches:
            results.append((b, matches))


def search(selection, config_type, query, dnac):
    pipeline = queue.Queue(maxsize=10)
    results = []
    processes = []
    filter = "config_type <> 'RESTCONF'"
    backups = Cursor

    if config_type == "running":
        filter = "config_type = 'CLI Running'"
    elif config_type == "startup":
        filter = "config_type = 'CLI Startup'"

    db = sqlite3.connect(
        "instance/flaskr.sqlite", detect_types=sqlite3.PARSE_DECLTYPES
    )
    db.row_factory = sqlite3.Row
    if selection == 'all':
        backups = db.execute(
            "SELECT b.id, device_id, created, config_type, content, dnac_id, uuid, hostname"
            " FROM backup b JOIN device d ON b.device_id = d.id"
            " WHERE dnac_id = ? AND {}".format(filter),
            (dnac,),
        ).fetchall()
    else:
        backups = db.execute(
            "SELECT b.id, device_id, MAX(created) AS created, config_type, content, dnac_id, uuid, hostname"
            " FROM backup b JOIN device d ON b.device_id = d.id"
            " WHERE dnac_id = ? AND {}"
            " GROUP BY device_id".format(filter),
            (dnac,),
        ).fetchall()
    db.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        for i in range(4):
            backups.append("END")
            processes.append(executor.submit(search_cons, pipeline, query))
        executor.submit(producer, pipeline, backups)
        
        for p in concurrent.futures.as_completed(processes):
            results.extend(p.result())
    
    results.sort(key=lambda x: x[0]['hostname'])
    return results


def update_devices(dnac, user_dnac):
    dnac_sess = requests.Session()

    url = "https://{}/dna/system/api/v1/auth/token".format(dnac["addr"])
    
    payload={}
    dnac_sess.headers.update({'Content-Type': 'application/json'})
    dnac_sess.verify=False

    response = dnac_sess.request("POST", url, auth=HTTPBasicAuth(user_dnac["dnac_user"], user_dnac["dnac_pass"]), data=payload)

    print(response.text)

    dna_token = response.json()['Token']

    url = "https://{}/dna/intent/api/v1/network-device".format(dnac["addr"])
    
    dnac_sess.headers.update({'Content-Type': 'application/json', 'x-auth-token': dna_token})
    
    response = dnac_sess.request("GET", url, data=payload)

    devices = response.json()['response']
    
    db = sqlite3.connect(
        "instance/flaskr.sqlite", detect_types=sqlite3.PARSE_DECLTYPES
    )
    db.row_factory = sqlite3.Row

    for d in devices:
        exists = db.execute(
            "SELECT *"
            " FROM device"
            " WHERE dnac_id = ? AND uuid = ?",
            (dnac['id'],d["id"]),
        ).fetchone()
        if exists is None:
            db.execute(
                "INSERT INTO device (dnac_id, uuid, hostname) VALUES (?, ?, ?)",
                (dnac['id'], d["id"], d["hostname"]),
            )
        else:
            db.execute(
                "UPDATE device SET hostname = ? WHERE id = ?", (d["hostname"], exists["id"])
            )
    
    db.commit()
    db.close()


def job_prod(jobqueue, actionqueue):
    db = sqlite3.connect(
        "instance/flaskr.sqlite", detect_types=sqlite3.PARSE_DECLTYPES
    )
    db.row_factory = sqlite3.Row
    jobs = db.execute(
        "SELECT j.id, author_id, j.dnac_id, addr, dnac_user, dnac_pass, restconf_user, restconf_pass, created, title, frequency, activated"
        " FROM job j JOIN user_dnac ud ON j.author_id = ud.user_id AND j.dnac_id = ud.dnac_id"
        " JOIN dnac d ON j.dnac_id = d.id",
    ).fetchall()
    db.close()

    for j in jobs:
        schedule.every(j['frequency']).minutes.do(jobqueue.put, [j['activated'], j, True, False]).tag(j['id'])
    
    while True:
        schedule.run_pending()
        time.sleep(1)
        # print("Job service active! => {}".format(threading.get_ident()))
        if not actionqueue.empty():
            a = actionqueue.get()
            print(a)
            if a['action'] in ["update", "delete"]:
                schedule.clear(a['job'])
            if a['action'] in ["create", "update"]:
                schedule.every(a['frequency']).minutes.do(jobqueue.put, [a['activated'], a['dnac'], True, False]).tag(a['job'])


def job_cons(jobqueue):
    while True:
        b = jobqueue.get()
        if b[0]:
            backup(b[1], b[2], b[3])


def job_service(actionqueue):
    print("Job service active!")
    jobqueue = queue.Queue(maxsize=10)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        executor.submit(job_prod, jobqueue, actionqueue)
        for i in range(4):
            executor.submit(job_cons, jobqueue)
