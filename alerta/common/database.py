import sys
import datetime
import pytz
import pymongo

from alerta.common import log as logging
from alerta.common import config
from alerta.common.alert import AlertDocument
from alerta.common import severity_code, status_code

LOG = logging.getLogger(__name__)
CONF = config.CONF


class Mongo(object):

    mongo_opts = {
        'mongo_host': 'localhost',
        'mongo_port': 27017,
        'mongo_database': 'monitoring',
        'mongo_collection': 'alerts',
        'mongo_username': 'admin',
        'mongo_password': '',
    }

    def __init__(self):

        config.register_opts(Mongo.mongo_opts)

        # Connect to MongoDB
        try:
            self.conn = pymongo.MongoClient(CONF.mongo_host, CONF.mongo_port)  # version >= 2.4
        except AttributeError:
            self.conn = pymongo.Connection(CONF.mongo_host, CONF.mongo_port)  # version < 2.4
        except Exception, e:
            LOG.error('MongoDB Client connection error : %s', e)
            sys.exit(1)

        try:
            self.db = self.conn[CONF.mongo_database]
        except Exception, e:
            LOG.error('MongoDB database error : %s', e)
            sys.exit(1)

        if CONF.mongo_password:
            try:
                self.db.authenticate(CONF.mongo_username, password=CONF.mongo_password)
            except Exception, e:
                LOG.error('MongoDB authentication failed: %s', e)
                sys.exit(1)

        LOG.info('Connected to MongoDB server %s:%s', CONF.mongo_host, CONF.mongo_port)

        self.create_indexes()

    def create_indexes(self):

        self.db.alerts.create_index([('environment', pymongo.ASCENDING), ('resource', pymongo.ASCENDING),
                                     ('event', pymongo.ASCENDING), ('severity', pymongo.ASCENDING)])
        self.db.alerts.create_index([('status', pymongo.ASCENDING), ('lastReceiveTime', pymongo.ASCENDING)])
        self.db.alerts.create_index([('status', pymongo.ASCENDING), ('lastReceiveTime', pymongo.ASCENDING),
                                     ('environment', pymongo.ASCENDING)])
        self.db.alerts.create_index([('status', pymongo.ASCENDING), ('service', pymongo.ASCENDING)])
        self.db.alerts.create_index([('status', pymongo.ASCENDING), ('environment', pymongo.ASCENDING)])
        self.db.alerts.create_index([('status', pymongo.ASCENDING), ('expireTime', pymongo.ASCENDING)])
        self.db.alerts.create_index([('status', pymongo.ASCENDING)])

    # def get_severity(self, alert):
    #
    #     return self.db.alerts.find_one({"environment": alert.environment, "resource": alert.resource,
    #                                     '$or': [{"event": alert.event}, {"correlate": alert.event}]},
    #                                    {"severity": 1, "_id": 0})['severity']
    #
    def get_count(self, query=None):

        return self.db.alerts.find(query).count()

    def get_counts(self, query=None):

        query = query or dict()

        found = 0
        severity_count = dict.fromkeys(severity_code.ALL, 0)
        status_count = dict.fromkeys(status_code.ALL, 0)

        responses = self.db.alerts.find(query, {"severity": 1, "status": 1})
        if not responses:
            LOG.warning('No alerts found with query = %s', query)
            return None

        for response in responses:
            severity_count[response['severity']] += 1
            status_count[response['status']] += 1
            found += 1

        return found, severity_count, status_count

    def get_alerts(self, query=None, fields=None, sort=None, limit=0):

        query = query or dict()
        fields = fields or list()
        sort = sort or dict()

        responses = self.db.alerts.find(query, fields=fields, sort=sort).limit(limit)
        if not responses:
            LOG.warning('Alert not found with query = %s, sort = %s, limit = %s', query, sort, limit)
            return None

        alerts = list()
        for response in responses:
            alerts.append(
                AlertDocument(
                    id=response['_id'],
                    resource=response['resource'],
                    event=response['event'],
                    environment=response['environment'],
                    severity=response['severity'],
                    correlate=response['correlate'],
                    status=response['status'],
                    service=response['service'],
                    group=response['group'],
                    value=response['value'],
                    text=response['text'],
                    tags=response['tags'],
                    attributes=response['attributes'],
                    origin=response['origin'],
                    event_type=response['type'],
                    create_time=response['createTime'],
                    timeout=response['timeout'],
                    raw_data=response['rawData'],
                    duplicate_count=response['duplicateCount'],
                    repeat=response['repeat'],
                    previous_severity=response['previousSeverity'],
                    trend_indication=response['trendIndication'],
                    receive_time=response['receiveTime'],
                    last_receive_id=response['lastReceiveId'],
                    last_receive_time=response['lastReceiveTime'],
                    history=response['history']
                )
            )
        return alerts

    def get_alert(self, id=None, environment=None, resource=None, event=None, severity=None):

        if id:
            query = {'$or': [{'_id': {'$regex': '^' + id}},
                    {'lastReceiveId': {'$regex': '^' + id}}]}
        elif severity:
            query = {"environment": environment, "resource": resource, "event": event, "severity": severity}
        else:
            query = {"environment": environment, "resource": resource, "event": event}

        response = self.db.alerts.find_one(query)
        LOG.debug('db.alerts.findOne(query=%s)', query)

        if not response:
            LOG.warning('Alert not found with environment, resource, event, severity = %s %s %s %s', environment, resource, event, severity)
            return None

        return AlertDocument(
            id=response['_id'],
            resource=response['resource'],
            event=response['event'],
            environment=response['environment'],
            severity=response['severity'],
            correlate=response['correlate'],
            status=response['status'],
            service=response['service'],
            group=response['group'],
            value=response['value'],
            text=response['text'],
            tags=response['tags'],
            attributes=response['attributes'],
            origin=response['origin'],
            event_type=response['type'],
            create_time=response['createTime'],
            timeout=response['timeout'],
            raw_data=response['rawData'],
            duplicate_count=response['duplicateCount'],
            repeat=response['repeat'],
            previous_severity=response['previousSeverity'],
            trend_indication=response['trendIndication'],
            receive_time=response['receiveTime'],
            last_receive_id=response['lastReceiveId'],
            last_receive_time=response['lastReceiveTime'],
            history=response['history']
        )

    def is_duplicate(self, alert, severity=None):

        if severity:
            found = self.db.alerts.find_one({"environment": alert.environment, "resource": alert.resource, "event": alert.event, "severity": severity})
        else:
            found = self.db.alerts.find_one({"environment": alert.environment, "resource": alert.resource, "event": alert.event})

        return found is not None

    def is_correlated(self, alert):

        found = self.db.alerts.find_one({"environment": alert.environment, "resource": alert.resource,
                                         '$or': [{"event": alert.event}, {"correlate": alert.event}]})
        return found is not None

    def save_duplicate(self, alert):
        """
        Update alert value, text and rawData, increment duplicate count and set repeat=True
        but don't append to history. Minimal changes.
        *** MUST RETURN DOCUMENT SO CAN PUT IT ON NOTIFY TOPIC ***
        """

        now = datetime.datetime.utcnow()
        update = {
            "value": alert.value,
            "text": alert.text,
            "rawData": alert.raw_data,
            "repeat": True,
            "lastReceiveId": alert.id,
            "lastReceiveTime": now,

        }

        LOG.debug('Update duplicate alert in database: %s', update)

        no_obj_error = "No matching object found"
        response = self.db.command("findAndModify", CONF.mongo_collection,
                                   allowable_errors=[no_obj_error],
                                   query={
                                       "environment": alert.environment,
                                       "resource": alert.resource,
                                       "event": alert.event
                                   },
                                   update={
                                       '$set': update,
                                       '$inc': {"duplicateCount": 1}
                                   },
                                   new=True,
                                   fields={"history": 0}
                                   )["value"]

        return AlertDocument(
            id=response['_id'],
            resource=response['resource'],
            event=response['event'],
            environment=response['environment'],
            severity=response['severity'],
            correlate=response['correlate'],
            status=response['status'],
            service=response['service'],
            group=response['group'],
            value=response['value'],
            text=response['text'],
            tags=response['tags'],
            attributes=response['attributes'],
            origin=response['origin'],
            event_type=response['type'],
            create_time=response['createTime'],
            timeout=response['timeout'],
            raw_data=response['rawData'],
            duplicate_count=response['duplicateCount'],
            repeat=response['repeat'],
            previous_severity=response['previousSeverity'],
            trend_indication=response['trendIndication'],
            receive_time=response['receiveTime'],
            last_receive_id=response['lastReceiveId'],
            last_receive_time=response['lastReceiveTime'],
            history=list()
        )

    def save_correlated(self, alert):
        """
        Update alert value, text and rawData, increment duplicate count and set repeat=True
        but don't append to history. Minimal changes.
        *** MUST RETURN DOCUMENT SO CAN PUT IT ON NOTIFY TOPIC ***
        """

        now = datetime.datetime.utcnow()
        update = [{
            "event": alert.event,
            "severity": alert.severity,
            "value": alert.value,
            "text": alert.text,
            "rawData": alert.raw_data,
            "duplicateCount": 0,
            "repeat": False,
            "previousSeverity": "",  # FIXME
            "lastReceiveId": alert.id,
            "lastReceiveTime": now,

        }]

        history = {
            "id": alert.id,
            "event": alert.event,
            "value": alert.value,
            "text": alert.text,
            "createTime": alert.create_time,
            "receiveTime": now
        }

        LOG.debug('Update correlated alert in database: %s', update)

        no_obj_error = "No matching object found"
        response = self.db.command("findAndModify", CONF.mongo_collection,
                                   allowable_errors=[no_obj_error],
                                   query={
                                       "environment": alert.environment,
                                       "resource": alert.resource,
                                       '$or': [
                                           {"event": alert.event},
                                           {"correlate": alert.event}
                                       ]
                                   },
                                   update={
                                       '$set': update,
                                       '$push': {"history": history}
                                   },
                                   new=True,
                                   fields={"history": 0}
                                   )["value"]

        return AlertDocument(
            id=response['_id'],
            resource=response['resource'],
            event=response['event'],
            environment=response['environment'],
            severity=response['severity'],
            correlate=response['correlate'],
            status=response['status'],
            service=response['service'],
            group=response['group'],
            value=response['value'],
            text=response['text'],
            tags=response['tags'],
            attributes=response['attributes'],
            origin=response['origin'],
            event_type=response['type'],
            create_time=response['createTime'],
            timeout=response['timeout'],
            raw_data=response['rawData'],
            duplicate_count=response['duplicateCount'],
            repeat=response['repeat'],
            previous_severity=response['previousSeverity'],
            trend_indication=response['trendIndication'],
            receive_time=response['receiveTime'],
            last_receive_id=response['lastReceiveId'],
            last_receive_time=response['lastReceiveTime'],
            history=list()
        )

    def save_new(self, alert):

        now = datetime.datetime.utcnow()
        history = [{
            "id": alert.id,
            "event": alert.event,
            "severity": alert.severity,
            "value": alert.value,
            "text": alert.text,
            "createTime": alert.create_time,
            "receiveTime": now
        }]

        document = AlertDocument(
            id=alert.id,
            resource=alert.resource,
            event=alert.event,
            environment=alert.environment,
            severity=alert.severity,
            correlate=alert.correlate,
            status=alert.status,
            service=alert.service,
            group=alert.group,
            value=alert.value,
            text=alert.text,
            tags=alert.tags,
            attributes=alert.attributes,
            origin=alert.origin,
            event_type=alert.event_type,
            create_time=alert.create_time,
            timeout=alert.timeout,
            raw_data=alert.raw_data,
            duplicate_count=0,
            repeat=False,
            previous_severity=severity_code.UNKNOWN,
            trend_indication=severity_code.trend(severity_code.UNKNOWN, alert.severity),
            receive_time=now,
            last_receive_id=alert.id,
            last_receive_time=now,
            history=history
        ).get_body()

        LOG.debug('Save new alert to database: %s', document)

        return self.db.alerts.insert(document)

    def disconnect(self):

        if self.conn.alive():
            self.conn.disconnect()

        LOG.info('Mongo disconnected.')