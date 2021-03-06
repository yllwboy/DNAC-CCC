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

            if os.path.exists(os.path.join(folder, response.headers['fileName'])):
                os.remove(os.path.join(folder, response.headers['fileName']))

            if restconf_sess:
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

    if dnac['restconf_user'] and dnac['restconf_pass']:
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
    dnac_sess.headers.update({'Content-Type': 'application/json', 'x-auth-token': dna_token})
    
    # print(response.text)

    devices = []
    all_devs = update_devices(dnac, dnac)
    if target == True:
        devices = all_devs
    else:
        for d in all_devs:
            if d['id'] in target:
                devices.append(d)

    # print(devices)

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
    p = p.upper()
    s = s.upper()
    
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

    if 'Token' not in response.json():
        return None

    dna_token = response.json()['Token']

    url = "https://{}/dna/intent/api/v1/network-device".format(dnac["addr"])
    
    dnac_sess.headers.update({'Content-Type': 'application/json', 'x-auth-token': dna_token})
    
    response = dnac_sess.request("GET", url, data=payload)

    devices = response.json()['response']
    
    db = sqlite3.connect(
        "instance/flaskr.sqlite", detect_types=sqlite3.PARSE_DECLTYPES
    )
    db.row_factory = sqlite3.Row

    db.execute(
        "UPDATE device SET connected = 0 WHERE dnac_id = ?", (dnac['id'],)
    )

    for d in devices:
        exists = db.execute(
            "SELECT *"
            " FROM device"
            " WHERE dnac_id = ? AND uuid = ?",
            (dnac['id'],d["id"]),
        ).fetchone()
        if exists is None:
            db.execute(
                "INSERT INTO device (dnac_id, uuid, hostname, addr) VALUES (?, ?, ?, ?)",
                (dnac['id'], d["id"], d["hostname"], d["managementIpAddress"]),
            )
        else:
            db.execute(
                "UPDATE device SET hostname = ?, addr = ?, connected = 1 WHERE id = ?", (d["hostname"], d["managementIpAddress"], exists["id"])
            )
    
    db.commit()
    db.close()

    return devices


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


def restconf_restore(addr, payload, user, pubkey):
    restconf_sess = requests.Session()
    
    url = "https://{}/restconf/data/Cisco-IOS-XE-native:native".format(addr)

    restconf_sess.headers.update({
        'Content-Type': 'application/yang-data+json',
        'Accept': 'application/yang-data+json'
    })
    restconf_sess.verify=pubkey
    restconf_sess.auth=HTTPBasicAuth(user['restconf_user'], user['restconf_pass'])

    response = restconf_sess.request("PUT", url, data=payload)

    return response.status_code
